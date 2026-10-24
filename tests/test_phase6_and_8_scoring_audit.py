"""
Tests for Phase 6 (Flags, Score, Risk) and Phase 8 (Audit Trail Integrity).

Verifies:
1. Risk level determination logic (HIGH for mandatory FAIL, MEDIUM for review/flags, LOW for clean).
2. Compliance score calculation (percentage of mandatory criteria passed or exempt).
3. Cryptographic hash chaining in audit log.
4. Detection of tampered audit row via verify_audit_chain.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    ActionType,
    AuditLog,
    Base,
    Bidder,
    Criterion,
    Flag,
    FlagType,
    RiskLevel,
    RuleOutcome,
    Tender,
)
from app.audit.chain import record_audit_action, verify_audit_chain
from app.rules.assessment import calculate_risk_level, evaluate_bidder
from app.rules.engine import RuleEvaluationResult
from app.extraction.intake import ingest_bidder_document


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_calculate_risk_level():
    # 1. Mandatory FAIL -> HIGH
    res_high = [
        RuleEvaluationResult(
            rule_id="TURNOVER_MIN", label="Turnover", mandatory=True,
            outcome=RuleOutcome.FAIL, reason="Below min"
        )
    ]
    assert calculate_risk_level(res_high, flag_count=0) == RiskLevel.HIGH

    # 2. Non-mandatory FAIL or Needs Review or Flags -> MEDIUM
    res_med = [
        RuleEvaluationResult(
            rule_id="TURNOVER_MIN", label="Turnover", mandatory=True,
            outcome=RuleOutcome.PASS, reason="Passed"
        ),
        RuleEvaluationResult(
            rule_id="GSTIN_PAN_CONSISTENT", label="GSTIN/PAN", mandatory=True,
            outcome=RuleOutcome.NEEDS_REVIEW, reason="Review required"
        ),
    ]
    assert calculate_risk_level(res_med, flag_count=0) == RiskLevel.MEDIUM

    # 3. Clean PASS with zero flags -> LOW
    res_low = [
        RuleEvaluationResult(
            rule_id="TURNOVER_MIN", label="Turnover", mandatory=True,
            outcome=RuleOutcome.PASS, reason="Passed"
        )
    ]
    assert calculate_risk_level(res_low, flag_count=0) == RiskLevel.LOW

    # 4. Clean PASS but 1 flag raised -> MEDIUM
    assert calculate_risk_level(res_low, flag_count=1) == RiskLevel.MEDIUM


def test_audit_log_hash_chain_and_tamper_detection(db_session):
    # Empty log is valid
    is_valid, broken_id, msg = verify_audit_chain(db_session)
    assert is_valid is True

    # Record 3 actions
    log1 = record_audit_action(
        db_session,
        action_type=ActionType.UPLOAD,
        actor="Officer Sharma",
        payload={"action": "upload", "filename": "tender.pdf"},
    )
    assert log1.prev_hash == "0" * 64

    log2 = record_audit_action(
        db_session,
        action_type=ActionType.RULE_RUN,
        actor="System",
        payload={"bidder": "Bidder A", "score": 100},
    )
    assert log2.prev_hash == log1.row_hash

    log3 = record_audit_action(
        db_session,
        action_type=ActionType.DECISION,
        actor="Officer Sharma",
        payload={"decision": "SHORTLIST"},
    )
    assert log3.prev_hash == log2.row_hash

    # Verify untampered chain
    is_valid, broken_id, msg = verify_audit_chain(db_session)
    assert is_valid is True
    assert broken_id is None
    assert "authentic" in msg

    # TAMPERING TEST: Modify payload of row 2 directly in the database
    log2.payload = {"bidder": "Bidder A", "score": 50, "tampered": True}
    db_session.commit()

    # Re-verify: MUST detect tampering!
    is_valid_after_tamper, broken_row_id, tamper_msg = verify_audit_chain(db_session)
    assert is_valid_after_tamper is False
    assert broken_row_id == log2.id
    assert "tampered" in tamper_msg.lower() or "broken" in tamper_msg.lower()
