"""
BidCheck - Bidder Assessment, Compliance Scoring & Risk Assessment.

Combines:
1. Deterministic Rule Engine evaluations on confirmed tender criteria.
2. Cross-document and mock registry verification discrepancies.
3. Price anomaly checks against historical benchmark proxies.
4. Compliance score calculation and risk level assignment.
5. Recording audit trail entries for non-repudiation.
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.audit.chain import record_audit_action
from app.models.database import (
    ActionType,
    Benchmark,
    Bidder,
    Criterion,
    Flag,
    FlagType,
    RiskLevel,
    RuleOutcome,
    RuleResult,
    Tender,
)
from app.rules.engine import RuleEngine, RuleEvaluationResult
from app.verification.cross_check import verify_bidder_cross_documents

logger = logging.getLogger(__name__)


def calculate_risk_level(
    rule_results: List[RuleEvaluationResult],
    flag_count: int,
) -> RiskLevel:
    """
    Deterministically computes risk level based on rule verdicts and flags.

    Logic:
    - HIGH: If ANY mandatory criterion produced outcome FAIL.
    - MEDIUM: If no mandatory criteria failed, but there are NEEDS_REVIEW items
              or unresolved flags.
    - LOW: If all mandatory criteria produced PASS or EXEMPT, and zero flags exist.
    """
    has_mandatory_fail = any(
        r.mandatory and r.outcome == RuleOutcome.FAIL
        for r in rule_results
    )
    if has_mandatory_fail:
        return RiskLevel.HIGH

    has_needs_review = any(
        r.outcome == RuleOutcome.NEEDS_REVIEW
        for r in rule_results
    )
    if has_needs_review or flag_count > 0:
        return RiskLevel.MEDIUM

    return RiskLevel.LOW


def check_price_benchmark_anomaly(
    session: Session,
    category: str,
    quoted_price: Optional[float],
) -> Optional[Tuple[str, str]]:
    """
    Compares quoted bid price against historical benchmark proxy dataset.
    Returns (title, detail) flag if anomalous, else None.
    """
    if not quoted_price or quoted_price <= 0:
        return None

    # Query benchmarks for this category
    benchmarks = (
        session.query(Benchmark)
        .filter(Benchmark.category.ilike(f"%{category}%"))
        .all()
    )
    if not benchmarks or len(benchmarks) < 3:
        return None

    values = [b.award_value_inr for b in benchmarks]
    avg_bench = sum(values) / len(values)

    # Flag as price outlier if > 3x average or < 0.2x average
    if quoted_price > avg_bench * 3.0:
        return (
            f"Quoted price (₹{quoted_price:,.0f}) is significantly above benchmark average (₹{avg_bench:,.0f})",
            f"The bid price is {quoted_price/avg_bench:.1f}x higher than the reference proxy average for {category}.",
        )
    if quoted_price < avg_bench * 0.2:
        return (
            f"Abnormally low bid price (₹{quoted_price:,.0f}) compared to benchmark (₹{avg_bench:,.0f})",
            f"The bid price is below 20% of historical average for {category}. Verify unviable predatory pricing risk.",
        )

    return None


def evaluate_bidder(
    session: Session,
    bidder_id: int,
    engine: Optional[RuleEngine] = None,
    actor: str = "RuleEngine",
) -> Dict[str, Any]:
    """
    Run full deterministic compliance evaluation for a single bidder:
    1. Loads extracted evidence map and tender criteria.
    2. Runs each rule through the deterministic RuleEngine.
    3. Runs cross-document verification and mock registry lookups.
    4. Computes compliance score and risk level.
    5. Persists RuleResult and Flag rows.
    6. Writes an audit log record.
    """
    rule_engine = engine or RuleEngine()

    bidder = session.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not bidder:
        raise ValueError(f"Bidder {bidder_id} not found")

    tender = session.query(Tender).filter(Tender.id == bidder.tender_id).first()
    if not tender:
        raise ValueError(f"Tender for bidder {bidder_id} not found")

    from app.extraction.intake import load_bidder_evidence_map
    evidence_map = load_bidder_evidence_map(session, bidder.id)
    claimed_categories = bidder.claimed_categories or []

    # Clear previous evaluation results and flags to ensure idempotent re-run
    session.query(RuleResult).filter(RuleResult.bidder_id == bidder.id).delete()
    session.query(Flag).filter(Flag.bidder_id == bidder.id).delete()
    session.flush()

    # 1. Evaluate Tender Criteria
    criteria = session.query(Criterion).filter(Criterion.tender_id == tender.id).all()
    results: List[RuleEvaluationResult] = []

    for criterion in criteria:
        try:
            rule_def = rule_engine.get_rule(criterion.rule_id)
        except Exception:
            # Synthetic default definition if file not found
            rule_def = {
                "id": criterion.rule_id,
                "label": criterion.label,
                "mandatory": criterion.mandatory,
                "check": {
                    "field": criterion.rule_id.lower(),
                    "op": ">=" if criterion.threshold_value else "==",
                    "value": float(criterion.threshold_value) if criterion.threshold_value and criterion.threshold_value.isdigit() else criterion.threshold_value,
                },
                "exemptions": [],
                "on_missing": "NEEDS_REVIEW",
            }

        # Override threshold if criterion specifies one
        t_override = None
        if criterion.threshold_value:
            try:
                t_override = float(criterion.threshold_value)
            except ValueError:
                t_override = criterion.threshold_value

        res = rule_engine.evaluate_rule(
            rule_def=rule_def,
            raw_evidence=evidence_map,
            claimed_categories=claimed_categories,
            bid_date=tender.bid_submission_deadline,
            allowed_exemption_categories=criterion.exemption_categories,
            threshold_override=t_override,
        )
        results.append(res)

        # Map evidence field IDs
        rr = RuleResult(
            tender_id=tender.id,
            criterion_id=criterion.id,
            bidder_id=bidder.id,
            rule_id=res.rule_id,
            outcome=res.outcome.value,
            reason=res.reason,
            evidence_field_ids=res.evidence_fields,
            evaluated_at=datetime.utcnow(),
        )
        session.add(rr)

        # If rule evaluation generated a flag, persist it
        if res.flag_type:
            flag = Flag(
                bidder_id=bidder.id,
                flag_type=res.flag_type,
                severity="HIGH" if res.outcome == RuleOutcome.FAIL else "MEDIUM",
                title=f"{res.label}: {res.flag_type}",
                detail=res.flag_detail or res.reason,
                field_name=res.evidence_fields[0] if res.evidence_fields else None,
            )
            session.add(flag)

    # 2. Run Cross-verification & Mock Registry Checks
    discrepancies = verify_bidder_cross_documents(
        bidder_name=bidder.name,
        evidence_map=evidence_map,
        documents=bidder.documents,
    )
    for disc in discrepancies:
        flag = Flag(
            bidder_id=bidder.id,
            flag_type=disc.flag_type.value,
            severity=disc.severity,
            title=disc.title,
            detail=disc.detail,
            document_id=disc.document_id,
            field_name=disc.field_name,
        )
        session.add(flag)

    # 3. Check Price Benchmark Anomaly
    if bidder.quoted_price and tender.category:
        price_anomaly = check_price_benchmark_anomaly(session, tender.category, bidder.quoted_price)
        if price_anomaly:
            p_title, p_detail = price_anomaly
            session.add(
                Flag(
                    bidder_id=bidder.id,
                    flag_type=FlagType.PRICE_OUTLIER.value,
                    severity="LOW",
                    title=p_title,
                    detail=p_detail,
                )
            )

    session.flush()

    # 4. Compute Scores & Risk Level
    mandatory_criteria = [c for c in criteria if c.mandatory]
    mandatory_count = len(mandatory_criteria) or 1

    mandatory_pass_or_exempt = 0
    breakdown = {
        RuleOutcome.PASS.value: 0,
        RuleOutcome.FAIL.value: 0,
        RuleOutcome.EXEMPT.value: 0,
        RuleOutcome.NEEDS_REVIEW.value: 0,
    }

    for res in results:
        breakdown[res.outcome.value] = breakdown.get(res.outcome.value, 0) + 1
        if res.mandatory and res.outcome in (RuleOutcome.PASS, RuleOutcome.EXEMPT):
            mandatory_pass_or_exempt += 1

    compliance_score = round(100.0 * (mandatory_pass_or_exempt / mandatory_count), 1)

    total_flags = session.query(Flag).filter(Flag.bidder_id == bidder.id).count()
    risk_level = calculate_risk_level(results, total_flags)

    bidder.compliance_score = compliance_score
    bidder.risk_level = risk_level.value

    session.commit()
    session.refresh(bidder)

    # 5. Record Audit Log Action
    record_audit_action(
        session=session,
        action_type=ActionType.RULE_RUN,
        actor=actor,
        payload={
            "bidder_id": bidder.id,
            "bidder_label": bidder.label,
            "compliance_score": compliance_score,
            "risk_level": risk_level.value,
            "criteria_evaluated": len(results),
            "breakdown": breakdown,
            "total_flags": total_flags,
        },
        tender_id=tender.id,
        bidder_id=bidder.id,
    )

    return {
        "bidder_id": bidder.id,
        "bidder_label": bidder.label,
        "bidder_name": bidder.name,
        "compliance_score": compliance_score,
        "risk_level": risk_level.value,
        "breakdown": breakdown,
        "total_flags": total_flags,
        "results": [r.to_dict() for r in results],
    }
