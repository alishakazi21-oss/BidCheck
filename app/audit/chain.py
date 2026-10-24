"""
BidCheck - Tamper-Evident SHA-256 Hash-Chained Audit Log.

Ensures non-repudiation and transparency for government procurement:
- Every action (upload, extraction, rule evaluation, flag, officer override, decision)
  appends a row with a cryptographic hash link to the previous row.
- Genesis row has prev_hash = "0" * 64.
- row_hash = SHA-256(prev_hash + canonical_json(payload)).
- A verification procedure walks the chain from genesis and detects any tampering,
  deletion, or unauthorized modification.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session
from app.models.database import ActionType, AuditLog

GENESIS_PREV_HASH = "0" * 64


def canonical_json(data: Dict[str, Any]) -> str:
    """
    Produce canonical JSON string: sorted keys, compact separators, deterministic.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_row_hash(prev_hash: str, canonical_payload: str) -> str:
    """
    Compute cryptographic SHA-256 hash chaining the previous row hash with canonical payload.
    """
    message = (prev_hash + canonical_payload).encode("utf-8")
    return hashlib.sha256(message).hexdigest()


def record_audit_action(
    session: Session,
    action_type: ActionType | str,
    actor: str,
    payload: Dict[str, Any],
    tender_id: Optional[int] = None,
    bidder_id: Optional[int] = None,
    document_id: Optional[int] = None,
) -> AuditLog:
    """
    Append an immutable, hash-chained record to the audit_log table.
    """
    act_str = action_type.value if hasattr(action_type, "value") else str(action_type)

    # Find the latest audit row to get the previous hash
    last_row = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = last_row.row_hash if last_row else GENESIS_PREV_HASH

    canon_str = canonical_json(payload)
    row_hash = compute_row_hash(prev_hash, canon_str)

    log_entry = AuditLog(
        action_type=act_str,
        actor=actor,
        payload=payload,
        tender_id=tender_id,
        bidder_id=bidder_id,
        document_id=document_id,
        prev_hash=prev_hash,
        row_hash=row_hash,
        timestamp=datetime.utcnow(),
    )
    session.add(log_entry)
    session.commit()
    session.refresh(log_entry)
    return log_entry


def verify_audit_chain(session: Session) -> Tuple[bool, Optional[int], str]:
    """
    Recompute and verify the entire SHA-256 hash chain from genesis block to current.
    Returns:
        (is_valid, broken_row_id, message)
    """
    rows = session.query(AuditLog).order_by(AuditLog.id.asc()).all()
    if not rows:
        return True, None, "Audit log is empty (valid genesis state)."

    expected_prev = GENESIS_PREV_HASH

    for row in rows:
        # 1. Verify link to previous row
        if row.prev_hash != expected_prev:
            return (
                False,
                row.id,
                f"Broken chain link at row {row.id}: expected prev_hash '{expected_prev[:12]}...', but found '{row.prev_hash[:12]}...'.",
            )

        # 2. Recompute row_hash from canonical JSON payload
        canon_payload = canonical_json(row.payload)
        recalculated_hash = compute_row_hash(row.prev_hash, canon_payload)

        if row.row_hash != recalculated_hash:
            return (
                False,
                row.id,
                f"Tampered row payload detected at row {row.id}: stored hash '{row.row_hash[:12]}...' does not match recomputed hash '{recalculated_hash[:12]}...'.",
            )

        expected_prev = row.row_hash

    return True, None, f"Audit log verified successfully. All {len(rows)} chained records are authentic and untampered."
