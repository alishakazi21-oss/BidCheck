"""
Unit and integration tests for Phase 2: Deterministic Rule Engine.

Validates:
  • Each rule: TURNOVER_MIN, EXPERIENCE_YEARS_MIN, OEM_AUTH_PRESENT,
    EMD_OR_EXEMPTION_PROOF, CERT_VALIDITY, GSTIN_PAN_CONSISTENT.
  • Layered exemption paths (allowed + claimed + valid proof + non-expired).
  • Exemption denial paths (missing proof, invalid proof, expired certificate).
  • Missing data handling (produces on_missing outcome, default NEEDS_REVIEW).
  • Low-confidence handling (<0.7 MUST produce NEEDS_REVIEW, never PASS or FAIL).
  • Boundary values (exact matches, 1 unit below/above).
  • RULE-PERTURBATION test: changing thresholds or removing rules changes verdict.
"""

from datetime import date
import pytest

from app.models.database import RuleOutcome, FlagType
from app.rules.engine import RuleEngine, RuleEvaluationResult


@pytest.fixture
def engine():
    """Initialise RuleEngine with default JSON definitions."""
    return RuleEngine()


# ---------------------------------------------------------------------------
# 1. Individual Rule Tests
# ---------------------------------------------------------------------------

def test_turnover_min_pass(engine):
    """Bidder with turnover >= 32L passes TURNOVER_MIN."""
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {"avg_turnover_3y": {"value": 4500000.0, "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.PASS
    assert "satisfies requirement" in result.reason
    assert result.evidence_fields == ["avg_turnover_3y"]


def test_turnover_min_fail(engine):
    """Bidder with turnover < 32L fails TURNOVER_MIN."""
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {"avg_turnover_3y": {"value": 1800000.0, "confidence": 0.92}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.FAIL
    assert "fails requirement" in result.reason
    assert result.flag_type == FlagType.MISMATCH.value


def test_experience_years_min_pass(engine):
    """Bidder with experience >= 3 years passes."""
    rule_def = engine.get_rule("EXPERIENCE_YEARS_MIN")
    evidence = {"experience_years": {"value": 5.0, "confidence": 0.90}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.PASS
    assert result.evidence_fields == ["experience_years"]


def test_experience_years_min_fail(engine):
    """Bidder with experience < 3 years fails."""
    rule_def = engine.get_rule("EXPERIENCE_YEARS_MIN")
    evidence = {"experience_years": {"value": 2.0, "confidence": 0.88}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.FAIL


def test_oem_auth_present_pass(engine):
    """Bidder with valid OEM authorization passes."""
    rule_def = engine.get_rule("OEM_AUTH_PRESENT")
    evidence = {"oem_auth_present": {"value": True, "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.PASS


def test_oem_auth_present_fail_when_false(engine):
    """Bidder with oem_auth_present == False fails."""
    rule_def = engine.get_rule("OEM_AUTH_PRESENT")
    evidence = {"oem_auth_present": {"value": False, "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.FAIL


def test_emd_or_exemption_proof_pass(engine):
    """Bidder with EMD present passes."""
    rule_def = engine.get_rule("EMD_OR_EXEMPTION_PROOF")
    evidence = {"emd_or_exemption_present": {"value": True, "confidence": 0.92}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.PASS


def test_cert_validity_pass(engine):
    """Certificate valid beyond bid submission deadline passes."""
    rule_def = engine.get_rule("CERT_VALIDITY")
    evidence = {"udyam_valid_until": {"value": "2026-03-31", "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence, bid_date=date(2024, 12, 31))

    assert result.outcome == RuleOutcome.PASS
    assert "meets/exceeds" in result.reason


def test_cert_validity_fail_expired(engine):
    """Certificate expired before bid deadline fails with EXPIRED flag."""
    rule_def = engine.get_rule("CERT_VALIDITY")
    evidence = {"udyam_valid_until": {"value": "2023-09-30", "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence, bid_date=date(2024, 12, 31))

    assert result.outcome == RuleOutcome.FAIL
    assert result.flag_type == FlagType.EXPIRED.value
    assert "expired on 2023-09-30" in result.reason


def test_gstin_pan_consistent_pass(engine):
    """Consistent entity details pass."""
    rule_def = engine.get_rule("GSTIN_PAN_CONSISTENT")
    evidence = {"gst_pan_match": {"value": True, "confidence": 0.98}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.PASS


def test_gstin_pan_consistent_fail(engine):
    """Mismatched legal entities fail."""
    rule_def = engine.get_rule("GSTIN_PAN_CONSISTENT")
    evidence = {"gst_pan_match": {"value": False, "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.FAIL
    assert result.flag_type == FlagType.MISMATCH.value


# ---------------------------------------------------------------------------
# 2. Layered Exemption Logic Tests
# ---------------------------------------------------------------------------

def test_mse_turnover_exemption_granted(engine):
    """
    MSE bidder with turnover below minimum (12L < 32L) but valid,
    non-expired Udyam certificate MUST be evaluated as EXEMPT.
    """
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {
        "avg_turnover_3y": {"value": 1200000.0, "confidence": 0.92},
        "mse_proof_valid": {"value": True, "confidence": 0.95},
        "udyam_valid_until": {"value": "2026-12-31", "confidence": 0.94},
    }
    result = engine.evaluate_rule(
        rule_def,
        evidence,
        claimed_categories=["MSE"],
        bid_date=date(2024, 12, 31),
        allowed_exemption_categories=["MSE", "STARTUP"],
    )

    assert result.outcome == RuleOutcome.EXEMPT
    assert "Exempt from minimum turnover as a verified MSE" in result.reason
    assert "mse_proof_valid" in result.evidence_fields


def test_startup_turnover_exemption_granted(engine):
    """Startup bidder with valid proof is EXEMPT from turnover."""
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {
        "avg_turnover_3y": {"value": 500000.0, "confidence": 0.90},
        "mse_proof_valid": {"value": True, "confidence": 0.95},
        "udyam_valid_until": {"value": "2027-01-01", "confidence": 0.95},
    }
    result = engine.evaluate_rule(
        rule_def,
        evidence,
        claimed_categories=["STARTUP"],
        bid_date=date(2024, 12, 31),
        allowed_exemption_categories=["MSE", "STARTUP"],
    )

    assert result.outcome == RuleOutcome.EXEMPT


def test_oem_itself_exemption_granted(engine):
    """Bidder claiming OEM_ITSELF is EXEMPT from third-party OEM authorization."""
    rule_def = engine.get_rule("OEM_AUTH_PRESENT")
    evidence = {
        "is_oem_manufacturer": {"value": True, "confidence": 0.96},
        "oem_auth_present": {"value": False, "confidence": 1.0},
    }
    result = engine.evaluate_rule(
        rule_def,
        evidence,
        claimed_categories=["OEM_ITSELF"],
    )

    assert result.outcome == RuleOutcome.EXEMPT
    assert "Original Equipment Manufacturer" in result.reason


def test_mse_turnover_exemption_denied_invalid_proof(engine):
    """
    Bidder C case: claims MSE exemption, but proof is INVALID (mse_proof_valid = False).
    Exemption must be denied, and turnover (18L < 32L) evaluated as FAIL
    with EXEMPTION_WITHOUT_PROOF flag.
    """
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {
        "avg_turnover_3y": {"value": 1800000.0, "confidence": 0.92},
        "mse_proof_valid": {"value": False, "confidence": 0.85},
        "udyam_valid_until": {"value": "2025-12-31", "confidence": 0.94},
    }
    result = engine.evaluate_rule(
        rule_def,
        evidence,
        claimed_categories=["MSE"],
        bid_date=date(2024, 12, 31),
        allowed_exemption_categories=["MSE", "STARTUP"],
    )

    assert result.outcome == RuleOutcome.FAIL
    assert result.flag_type == FlagType.EXEMPTION_WITHOUT_PROOF.value
    assert "Exemption claim was reviewed and denied" in result.reason


def test_mse_turnover_exemption_denied_expired_certificate(engine):
    """
    Exemption claim with expired certificate must be denied with EXPIRED flag.
    """
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {
        "avg_turnover_3y": {"value": 1500000.0, "confidence": 0.92},
        "mse_proof_valid": {"value": True, "confidence": 0.95},
        "udyam_valid_until": {"value": "2023-09-30", "confidence": 0.95},
    }
    result = engine.evaluate_rule(
        rule_def,
        evidence,
        claimed_categories=["MSE"],
        bid_date=date(2024, 12, 31),
        allowed_exemption_categories=["MSE", "STARTUP"],
    )

    assert result.outcome == RuleOutcome.FAIL
    assert result.flag_type == FlagType.EXPIRED.value
    assert "expired on 2023-09-30" in result.reason


def test_exemption_not_allowed_by_tender(engine):
    """
    If tender disallows the category, exemption is not granted.
    """
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {
        "avg_turnover_3y": {"value": 1500000.0, "confidence": 0.92},
        "mse_proof_valid": {"value": True, "confidence": 0.95},
        "udyam_valid_until": {"value": "2026-12-31", "confidence": 0.95},
    }
    result = engine.evaluate_rule(
        rule_def,
        evidence,
        claimed_categories=["MSE"],
        allowed_exemption_categories=["STARTUP"],  # Tender only permits STARTUP, not MSE
    )

    assert result.outcome == RuleOutcome.FAIL


# ---------------------------------------------------------------------------
# 3. Missing and Low Confidence Handling
# ---------------------------------------------------------------------------

def test_missing_data_routes_to_needs_review(engine):
    """
    Missing field with on_missing='NEEDS_REVIEW' must NEVER produce PASS or FAIL.
    """
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {}  # Empty evidence
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.NEEDS_REVIEW
    assert "not found" in result.reason.lower() or "not available" in result.reason.lower()


def test_missing_mandatory_oem_auth_fails(engine):
    """
    OEM_AUTH_PRESENT declares on_missing='FAIL', so missing doc triggers FAIL.
    """
    rule_def = engine.get_rule("OEM_AUTH_PRESENT")
    evidence = {}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.FAIL
    assert result.flag_type == FlagType.MISSING_DOCUMENT.value


def test_low_confidence_strictly_routes_to_needs_review(engine):
    """
    CRITICAL CONSTRAINT: Extracted value with confidence < 0.70 MUST produce
    NEEDS_REVIEW, never PASS or FAIL, even if the value numerically meets threshold.
    """
    rule_def = engine.get_rule("TURNOVER_MIN")
    # Turnover is 50L (well above 32L), but confidence is 0.65 (< 0.70)
    evidence = {"avg_turnover_3y": {"value": 5000000.0, "confidence": 0.65}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.NEEDS_REVIEW
    assert result.flag_type == FlagType.LOW_CONFIDENCE.value
    assert "confidence is low" in result.reason
    assert "Manual inspection required" in result.reason


# ---------------------------------------------------------------------------
# 4. Boundary Value Testing
# ---------------------------------------------------------------------------

def test_turnover_exact_boundary_passes(engine):
    """Exactly meeting the threshold 3,200,000.0 must PASS."""
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {"avg_turnover_3y": {"value": 3200000.0, "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.PASS


def test_turnover_one_rupee_below_boundary_fails(engine):
    """One rupee below threshold (3,199,999.0) must FAIL."""
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {"avg_turnover_3y": {"value": 3199999.0, "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.FAIL


def test_experience_exact_boundary_passes(engine):
    """Exactly 3.0 years of experience must PASS."""
    rule_def = engine.get_rule("EXPERIENCE_YEARS_MIN")
    evidence = {"experience_years": {"value": 3.0, "confidence": 0.90}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.PASS


def test_experience_just_below_boundary_fails(engine):
    """2.99 years must FAIL."""
    rule_def = engine.get_rule("EXPERIENCE_YEARS_MIN")
    evidence = {"experience_years": {"value": 2.99, "confidence": 0.90}}
    result = engine.evaluate_rule(rule_def, evidence)

    assert result.outcome == RuleOutcome.FAIL


def test_cert_validity_exact_bid_date_passes(engine):
    """Certificate expiring exactly on bid deadline date (2024-12-31) passes."""
    rule_def = engine.get_rule("CERT_VALIDITY")
    evidence = {"udyam_valid_until": {"value": "2024-12-31", "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence, bid_date=date(2024, 12, 31))

    assert result.outcome == RuleOutcome.PASS


def test_cert_validity_one_day_before_bid_date_fails(engine):
    """Certificate expiring one day before bid deadline fails."""
    rule_def = engine.get_rule("CERT_VALIDITY")
    evidence = {"udyam_valid_until": {"value": "2024-12-30", "confidence": 0.95}}
    result = engine.evaluate_rule(rule_def, evidence, bid_date=date(2024, 12, 31))

    assert result.outcome == RuleOutcome.FAIL


# ---------------------------------------------------------------------------
# 5. Rule Perturbation Testing
# ---------------------------------------------------------------------------

def test_rule_perturbation_threshold_change(engine):
    """
    Perturbation test: Changing the threshold of TURNOVER_MIN from 32L to 50L
    must change the verdict for a bidder with 45L turnover from PASS to FAIL.
    """
    rule_def = engine.get_rule("TURNOVER_MIN")
    evidence = {"avg_turnover_3y": {"value": 4500000.0, "confidence": 0.95}}

    # Base case: threshold 32L -> PASS
    base_result = engine.evaluate_rule(rule_def, evidence)
    assert base_result.outcome == RuleOutcome.PASS

    # Perturbed case: threshold increased to 50L -> MUST change verdict to FAIL
    perturbed_result = engine.evaluate_rule(
        rule_def,
        evidence,
        threshold_override=5000000.0,
    )
    assert perturbed_result.outcome == RuleOutcome.FAIL
    assert perturbed_result.outcome != base_result.outcome


def test_rule_perturbation_rule_removal_affects_tender_outcome(engine):
    """
    Perturbation test: Removing a rule from the evaluation list alters
    the set of criteria results.
    """
    criteria = [
        {"rule_id": "TURNOVER_MIN", "threshold_value": 3200000},
        {"rule_id": "EXPERIENCE_YEARS_MIN", "threshold_value": 3},
        {"rule_id": "OEM_AUTH_PRESENT"},
    ]
    evidence = {
        "avg_turnover_3y": {"value": 4500000.0, "confidence": 0.95},
        "experience_years": {"value": 1.0, "confidence": 0.90},  # Fails experience
        "oem_auth_present": {"value": True, "confidence": 0.95},
    }

    # With 3 rules, one rule FAILS
    full_results = engine.evaluate_all(criteria, evidence)
    fail_count_before = sum(1 for r in full_results if r.outcome == RuleOutcome.FAIL)
    assert fail_count_before == 1

    # Perturb: Remove the failing rule EXPERIENCE_YEARS_MIN
    perturbed_criteria = [c for c in criteria if c["rule_id"] != "EXPERIENCE_YEARS_MIN"]
    perturbed_results = engine.evaluate_all(perturbed_criteria, evidence)
    fail_count_after = sum(1 for r in perturbed_results if r.outcome == RuleOutcome.FAIL)

    assert fail_count_after == 0
    assert len(perturbed_results) == 2
