"""
Deterministic Rule Engine for GeM Bid Compliance Verification.

CORE PRINCIPLE:
Deterministic, tested rule logic decides. LLMs NEVER decide a number, date,
or eligibility verdict. Every outcome carries a human-readable explanation
and exact evidence references.

OUTCOMES:
  • PASS: Meets or exceeds requirements.
  • FAIL: Does not meet requirements and no valid exemption applies.
  • EXEMPT: Statutory exemption applies (layered: claimed + allowed + proof valid + non-expired).
  • NEEDS_REVIEW: Missing data, low confidence (<0.7), or unreadable evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from dateutil import parser as date_parser

from app.config import settings
from app.models.database import RuleOutcome, FlagType


@dataclass
class FieldEvidence:
    """Represents extracted field evidence used during rule evaluation."""
    field_name: str
    value: Any
    confidence: float = 1.0
    page_number: Optional[int] = None
    snippet: Optional[str] = None
    bounding_box: Optional[List[float]] = None
    source_document: Optional[str] = None

    @classmethod
    def from_raw(cls, field_name: str, raw: Any) -> "FieldEvidence":
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, dict) and "value" in raw:
            return cls(
                field_name=field_name,
                value=raw.get("value"),
                confidence=float(raw.get("confidence", 1.0)),
                page_number=raw.get("page"),
                snippet=raw.get("snippet"),
                bounding_box=raw.get("bbox"),
            )
        # Plain primitive
        return cls(field_name=field_name, value=raw, confidence=1.0)


@dataclass
class RuleEvaluationResult:
    """The structured, deterministic verdict for a single rule."""
    rule_id: str
    label: str
    mandatory: bool
    outcome: RuleOutcome
    reason: str
    evidence_fields: List[str] = field(default_factory=list)
    flag_type: Optional[str] = None
    flag_detail: Optional[str] = None
    checked_value: Any = None
    required_value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "mandatory": self.mandatory,
            "outcome": self.outcome.value if hasattr(self.outcome, "value") else str(self.outcome),
            "reason": self.reason,
            "evidence_fields": self.evidence_fields,
            "flag_type": self.flag_type,
            "flag_detail": self.flag_detail,
            "checked_value": self.checked_value,
            "required_value": self.required_value,
        }


class RuleEngine:
    """
    Evaluates tender criteria rules against bidder extracted evidence.
    Loads rules from JSON definitions or accepts runtime-customised rules.
    """

    def __init__(self, rules_dir: Optional[Path] = None):
        self.rules_dir = rules_dir or settings.rules_dir
        self.rules: Dict[str, Dict[str, Any]] = {}
        self.load_rule_definitions()

    def load_rule_definitions(self) -> None:
        """Load all rule JSON files from definitions directory."""
        if not self.rules_dir.exists():
            return
        for rule_file in self.rules_dir.glob("*.json"):
            try:
                data = json.loads(rule_file.read_text(encoding="utf-8"))
                rule_id = data.get("id") or rule_file.stem
                self.rules[rule_id] = data
            except Exception as e:
                print(f"[!] Warning: Failed to load rule {rule_file}: {e}")

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        return self.rules.get(rule_id)

    def register_rule(self, rule_def: Dict[str, Any]) -> None:
        """Register or override a rule definition dynamically."""
        rule_id = rule_def["id"]
        self.rules[rule_id] = rule_def

    # -----------------------------------------------------------------------
    # Helper coercion methods
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_date(val: Any) -> Optional[date]:
        if val is None:
            return None
        if isinstance(val, (date, datetime)):
            return val.date() if isinstance(val, datetime) else val
        try:
            return date_parser.parse(str(val)).date()
        except Exception:
            return None

    @staticmethod
    def _parse_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace(",", "").replace("₹", "").replace("Rs.", "").strip()
        try:
            return float(s)
        except Exception:
            return None

    # -----------------------------------------------------------------------
    # Exemption Evaluation (Layered Logic)
    # -----------------------------------------------------------------------

    def evaluate_exemption(
        self,
        exemption_rule: Dict[str, Any],
        claimed_categories: List[str],
        evidence_map: Dict[str, FieldEvidence],
        bid_date: Optional[date] = None,
        allowed_categories: Optional[List[str]] = None,
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Evaluate layered exemption requirements:
          1. Category must be in claimed categories AND allowed by tender.
          2. Proof field must exist and be valid (e.g. mse_proof_valid == True).
          3. Validity date must exist and NOT be expired on bid submission date.

        Returns:
          (is_exempt, reason, flag_type, flag_detail)
        """
        target_cats = set(exemption_rule.get("category_in", []))
        claimed_set = set(claimed_categories or [])

        # Check intersection
        matching_cats = claimed_set.intersection(target_cats)
        if not matching_cats:
            return False, None, None, None

        matched_cat = next(iter(matching_cats))

        # Check if tender explicitly restricts allowed exemption categories
        if allowed_categories is not None and matched_cat not in allowed_categories:
            return (
                False,
                f"Exemption for '{matched_cat}' is not permitted by this tender's terms.",
                None,
                None,
            )

        proof_field = exemption_rule.get("proof_field")
        validity_field = exemption_rule.get("validity_field")

        # 1. Verify Proof Document Validity
        proof_ev = evidence_map.get(proof_field) if proof_field else None
        if proof_field:
            if not proof_ev or proof_ev.value is None:
                return (
                    False,
                    f"Claimed {matched_cat} exemption, but required proof document is missing.",
                    FlagType.EXEMPTION_WITHOUT_PROOF.value,
                    f"Bidder claimed {matched_cat} status but provided no verifiable proof document.",
                )
            if bool(proof_ev.value) is not True:
                return (
                    False,
                    f"Claimed {matched_cat} exemption, but uploaded certificate is marked INVALID.",
                    FlagType.EXEMPTION_WITHOUT_PROOF.value,
                    f"The submitted {matched_cat} certificate was verified as invalid or rejected.",
                )

        # 2. Verify Expiry Date on Bid Submission Date
        if validity_field:
            val_ev = evidence_map.get(validity_field)
            if not val_ev or val_ev.value is None:
                return (
                    False,
                    f"Claimed {matched_cat} exemption, but certificate expiry date is missing.",
                    FlagType.LOW_CONFIDENCE.value,
                    f"Could not extract validity/expiry date for {matched_cat} certificate.",
                )
            cert_expiry = self._parse_date(val_ev.value)
            if not cert_expiry:
                return (
                    False,
                    f"Unreadable expiry date '{val_ev.value}' on {matched_cat} certificate.",
                    FlagType.LOW_CONFIDENCE.value,
                    "Expiry date format could not be verified deterministically.",
                )
            effective_bid_date = bid_date or date(2024, 12, 31)
            if cert_expiry < effective_bid_date:
                return (
                    False,
                    f"{matched_cat} certificate expired on {cert_expiry} (prior to bid date {effective_bid_date}).",
                    FlagType.EXPIRED.value,
                    f"{matched_cat} certificate expired on {cert_expiry}, before the bid submission deadline {effective_bid_date}.",
                )

        # Exemption Fully Granted!
        reason = exemption_rule.get(
            "reason",
            f"Exempt from requirement as a verified {matched_cat} entity with valid non-expired certificate."
        )
        return True, reason, None, None

    # -----------------------------------------------------------------------
    # Single Rule Evaluation
    # -----------------------------------------------------------------------

    def evaluate_rule(
        self,
        rule_def: Dict[str, Any],
        raw_evidence: Dict[str, Any],
        claimed_categories: Optional[List[str]] = None,
        bid_date: Optional[date] = None,
        allowed_exemption_categories: Optional[List[str]] = None,
        threshold_override: Optional[Any] = None,
    ) -> RuleEvaluationResult:
        """
        Deterministically evaluate a single rule against extracted evidence.
        """
        rule_id = rule_def["id"]
        label = rule_def.get("label", rule_id)
        mandatory = bool(rule_def.get("mandatory", True))
        claimed_cats = claimed_categories or []

        # Convert raw evidence dictionary to FieldEvidence objects
        evidence_map: Dict[str, FieldEvidence] = {}
        for k, v in raw_evidence.items():
            evidence_map[k] = FieldEvidence.from_raw(k, v)

        # -------------------------------------------------------------------
        # Step 1: Layered Exemption Evaluation
        # -------------------------------------------------------------------
        exemptions = rule_def.get("exemptions", [])
        denied_flags: List[tuple[str, str]] = []

        for ex_rule in exemptions:
            is_exempt, ex_reason, ex_flag, ex_detail = self.evaluate_exemption(
                ex_rule,
                claimed_cats,
                evidence_map,
                bid_date=bid_date,
                allowed_categories=allowed_exemption_categories,
            )
            if is_exempt:
                used_fields = []
                if ex_rule.get("proof_field"):
                    used_fields.append(ex_rule["proof_field"])
                if ex_rule.get("validity_field"):
                    used_fields.append(ex_rule["validity_field"])
                return RuleEvaluationResult(
                    rule_id=rule_id,
                    label=label,
                    mandatory=mandatory,
                    outcome=RuleOutcome.EXEMPT,
                    reason=ex_reason or "Statutory exemption granted.",
                    evidence_fields=used_fields,
                    checked_value="EXEMPT",
                    required_value="EXEMPT",
                )
            if ex_flag:
                denied_flags.append((ex_flag, ex_detail or ex_reason or ""))

        # -------------------------------------------------------------------
        # Step 2: Extract primary field and check missing / confidence
        # -------------------------------------------------------------------
        check_spec = rule_def.get("check", {})
        primary_field = check_spec.get("field")
        op = check_spec.get("op", "==")
        target_value = threshold_override if threshold_override is not None else check_spec.get("value")
        unit = check_spec.get("unit", "")

        if not primary_field or primary_field not in evidence_map:
            on_missing_str = rule_def.get("on_missing", "NEEDS_REVIEW")
            outcome = RuleOutcome.FAIL if on_missing_str == "FAIL" else RuleOutcome.NEEDS_REVIEW
            reason = rule_def.get(
                "missing_reason",
                f"Required field '{primary_field}' was not found in submitted documents."
            )
            flag_type = FlagType.MISSING_DOCUMENT.value if outcome == RuleOutcome.FAIL else FlagType.LOW_CONFIDENCE.value
            return RuleEvaluationResult(
                rule_id=rule_id,
                label=label,
                mandatory=mandatory,
                outcome=outcome,
                reason=reason,
                evidence_fields=[],
                flag_type=flag_type,
                flag_detail=reason,
                checked_value=None,
                required_value=target_value,
            )

        ev = evidence_map[primary_field]
        val = ev.value

        # Value is null or empty
        if val is None or val == "":
            on_missing_str = rule_def.get("on_missing", "NEEDS_REVIEW")
            outcome = RuleOutcome.FAIL if on_missing_str == "FAIL" else RuleOutcome.NEEDS_REVIEW
            reason = f"Field '{primary_field}' is null or empty in extracted documents."
            return RuleEvaluationResult(
                rule_id=rule_id,
                label=label,
                mandatory=mandatory,
                outcome=outcome,
                reason=reason,
                evidence_fields=[primary_field],
                flag_type=FlagType.MISSING_DOCUMENT.value,
                flag_detail=reason,
                checked_value=None,
                required_value=target_value,
            )

        # CRITICAL HARD CONSTRAINT: Low confidence (<0.7) MUST produce NEEDS_REVIEW, never PASS or FAIL
        if ev.confidence < settings.confidence_threshold:
            reason = (
                f"Field '{primary_field}' extraction confidence is low "
                f"({ev.confidence:.2f} < {settings.confidence_threshold:.2f}). "
                f"Manual inspection required before deciding."
            )
            return RuleEvaluationResult(
                rule_id=rule_id,
                label=label,
                mandatory=mandatory,
                outcome=RuleOutcome.NEEDS_REVIEW,
                reason=reason,
                evidence_fields=[primary_field],
                flag_type=FlagType.LOW_CONFIDENCE.value,
                flag_detail=reason,
                checked_value=val,
                required_value=target_value,
            )

        # -------------------------------------------------------------------
        # Step 3: Evaluate Deterministic Operator Condition
        # -------------------------------------------------------------------
        passed = False
        reason = ""
        flag_type = None
        flag_detail = None

        if op in [">=", "<=", ">", "<"]:
            checked_num = self._parse_float(val)
            target_num = self._parse_float(target_value)
            if checked_num is None or target_num is None:
                return RuleEvaluationResult(
                    rule_id=rule_id,
                    label=label,
                    mandatory=mandatory,
                    outcome=RuleOutcome.NEEDS_REVIEW,
                    reason=f"Could not convert field '{primary_field}' value ({val}) or target ({target_value}) to numeric.",
                    evidence_fields=[primary_field],
                    flag_type=FlagType.LOW_CONFIDENCE.value,
                    flag_detail=f"Non-numeric value '{val}' encountered for comparison {op} {target_value}.",
                    checked_value=val,
                    required_value=target_value,
                )

            if op == ">=":
                passed = checked_num >= target_num
            elif op == "<=":
                passed = checked_num <= target_num
            elif op == ">":
                passed = checked_num > target_num
            elif op == "<":
                passed = checked_num < target_num

            unit_str = f" {unit}".rstrip()
            if passed:
                reason = f"Extracted value of {checked_num:,.2f}{unit_str} satisfies requirement {op} {target_num:,.2f}{unit_str}."
            else:
                reason = f"Extracted value of {checked_num:,.2f}{unit_str} fails requirement {op} {target_num:,.2f}{unit_str}."
                flag_type = FlagType.MISMATCH.value
                flag_detail = f"Threshold not met: {checked_num:,.2f}{unit_str} < required {target_num:,.2f}{unit_str}."

        elif op == "==":
            # Type-aware boolean or literal equality
            if isinstance(target_value, bool):
                val_bool = bool(val) and str(val).lower() not in ["false", "0", "no"]
                passed = val_bool == target_value
            else:
                passed = str(val).strip().lower() == str(target_value).strip().lower()

            if passed:
                reason = f"Requirement verified: '{primary_field}' matches required condition ({target_value})."
            else:
                reason = f"Requirement not satisfied: '{primary_field}' ({val}) does not match required condition ({target_value})."
                flag_type = FlagType.MISMATCH.value
                flag_detail = reason

        elif op == "date_gte":
            checked_date = self._parse_date(val)
            target_date = self._parse_date(target_value)
            if not checked_date or not target_date:
                return RuleEvaluationResult(
                    rule_id=rule_id,
                    label=label,
                    mandatory=mandatory,
                    outcome=RuleOutcome.NEEDS_REVIEW,
                    reason=f"Date parsing failed for '{primary_field}' ({val}) or deadline ({target_value}).",
                    evidence_fields=[primary_field],
                    flag_type=FlagType.LOW_CONFIDENCE.value,
                    flag_detail="Date format could not be verified deterministically.",
                    checked_value=val,
                    required_value=target_value,
                )

            passed = checked_date >= target_date
            if passed:
                reason = f"Certificate valid until {checked_date}, which meets/exceeds the required date {target_date}."
            else:
                reason = f"Certificate expired on {checked_date}, prior to required date {target_date}."
                flag_type = FlagType.EXPIRED.value
                flag_detail = f"Certificate is expired: {checked_date} < {target_date}."

        elif op == "in":
            target_list = target_value if isinstance(target_value, list) else [target_value]
            passed = val in target_list
            reason = f"Value '{val}' {'is present' if passed else 'is not present'} in permitted set."
            if not passed:
                flag_type = FlagType.MISMATCH.value
                flag_detail = reason

        else:
            return RuleEvaluationResult(
                rule_id=rule_id,
                label=label,
                mandatory=mandatory,
                outcome=RuleOutcome.NEEDS_REVIEW,
                reason=f"Unsupported operator '{op}'.",
                evidence_fields=[primary_field],
            )

        # If exemption was claimed but denied and rule failed, attach the exemption denial flag
        if not passed and denied_flags:
            flag_type, flag_detail = denied_flags[0]
            reason += f" (Exemption claim was reviewed and denied: {flag_detail})"

        return RuleEvaluationResult(
            rule_id=rule_id,
            label=label,
            mandatory=mandatory,
            outcome=RuleOutcome.PASS if passed else RuleOutcome.FAIL,
            reason=reason,
            evidence_fields=[primary_field],
            flag_type=flag_type,
            flag_detail=flag_detail,
            checked_value=val,
            required_value=target_value,
        )

    # -----------------------------------------------------------------------
    # Evaluate All Tender Rules for a Bidder
    # -----------------------------------------------------------------------

    def evaluate_all(
        self,
        tender_criteria: List[Dict[str, Any]],
        bidder_evidence: Dict[str, Any],
        claimed_categories: Optional[List[str]] = None,
        bid_date: Optional[date] = None,
    ) -> List[RuleEvaluationResult]:
        """
        Evaluate all tender criteria against a bidder's evidence.
        """
        results: List[RuleEvaluationResult] = []

        for crit in tender_criteria:
            rule_id = crit.get("rule_id") or crit.get("id")
            rule_def = self.get_rule(rule_id)
            if not rule_def:
                # Build inline rule definition from criterion
                rule_def = {
                    "id": rule_id,
                    "label": crit.get("label", rule_id),
                    "mandatory": crit.get("mandatory", True),
                    "check": {
                        "field": crit.get("field", rule_id.lower()),
                        "op": crit.get("op", ">="),
                        "value": crit.get("threshold_value"),
                        "unit": crit.get("threshold_unit"),
                    },
                    "exemptions": [],
                    "on_missing": "NEEDS_REVIEW",
                }

            # If criterion specifies custom threshold or allowed exemptions, pass them
            threshold_override = crit.get("threshold_value")
            allowed_exemptions = crit.get("exemption_categories")

            res = self.evaluate_rule(
                rule_def=rule_def,
                raw_evidence=bidder_evidence,
                claimed_categories=claimed_categories,
                bid_date=bid_date,
                allowed_exemption_categories=allowed_exemptions,
                threshold_override=threshold_override if threshold_override is not None else None,
            )
            results.append(res)

        return results
