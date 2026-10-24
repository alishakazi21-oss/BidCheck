"""
BidCheck - FastAPI Backend Service.

Exposes REST APIs for bid evaluation, officer decisions, criteria confirmation,
mock registry inspection, and cryptographic audit log verification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.audit.chain import record_audit_action, verify_audit_chain
from app.models.database import (
    ActionType,
    Bidder,
    Criterion,
    Decision,
    RuleResult,
    Tender,
    get_engine,
    create_tables,
)
from app.models.session import SessionLocal
from app.pipeline import setup_demo_environment
from app.rules.assessment import evaluate_bidder
from app.verification.mock_api import router as mock_registry_router

app = FastAPI(
    title="BidCheck API",
    description=(
        "AI-assisted GeM bid compliance verification backend. "
        "DECISION SUPPORT ONLY: Never disqualifies bidders automatically. "
        "All government registries are MOCK services for hackathon demonstration."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mock_registry_router)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    engine = get_engine()
    create_tables(engine)
    session = SessionLocal()
    setup_demo_environment(session, force_reset=False)
    session.close()


# Pydantic Request/Response models
class OverrideRequest(BaseModel):
    rule_id: str
    new_outcome: str = Field(description="PASS | FAIL | EXEMPT | NEEDS_REVIEW")
    reason: str = Field(description="Mandatory officer justification")
    officer_name: str = "Procurement Officer"


class DecisionRequest(BaseModel):
    officer_decision: str = Field(description="SHORTLIST | REJECT | REFER")
    officer_name: str = "Procurement Officer"
    notes: Optional[str] = None


@app.get("/")
def root():
    return {
        "service": "BidCheck API",
        "status": "online",
        "mode": "offline-first (FakeExtractor active)",
        "disclaimer": "DECISION SUPPORT ONLY. Mock government registries (GSTN/MCA/Udyam). Officer holds final decision authority.",
    }


@app.get("/tenders")
def list_tenders(db: Session = Depends(get_db)):
    tenders = db.query(Tender).all()
    return [
        {
            "id": t.id,
            "gem_id": t.gem_id,
            "title": t.title,
            "category": t.category,
            "criteria_confirmed": t.criteria_confirmed,
            "bid_deadline": str(t.bid_submission_deadline),
            "bidders_count": len(t.bidders),
        }
        for t in tenders
    ]


@app.get("/bidders")
def list_bidders(db: Session = Depends(get_db)):
    bidders = db.query(Bidder).all()
    return [
        {
            "id": b.id,
            "label": b.label,
            "name": b.name,
            "compliance_score": b.compliance_score,
            "risk_level": b.risk_level,
            "quoted_price": b.quoted_price,
            "flags_count": len(b.flags),
        }
        for b in bidders
    ]


@app.get("/bidders/{bidder_id}")
def get_bidder_details(bidder_id: int, db: Session = Depends(get_db)):
    b = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Bidder not found")

    return {
        "id": b.id,
        "label": b.label,
        "name": b.name,
        "compliance_score": b.compliance_score,
        "risk_level": b.risk_level,
        "quoted_price": b.quoted_price,
        "rule_results": [
            {
                "rule_id": rr.rule_id,
                "label": rr.criterion.label,
                "mandatory": rr.criterion.mandatory,
                "outcome": rr.outcome,
                "reason": rr.reason,
                "officer_override": rr.officer_override,
                "override_reason": rr.override_reason,
            }
            for rr in b.rule_results
        ],
        "flags": [
            {
                "type": f.flag_type,
                "severity": f.severity,
                "title": f.title,
                "detail": f.detail,
            }
            for f in b.flags
        ],
    }


@app.post("/bidders/{bidder_id}/evaluate")
def trigger_evaluation(bidder_id: int, db: Session = Depends(get_db)):
    res = evaluate_bidder(db, bidder_id, actor="API_User")
    return res


@app.post("/bidders/{bidder_id}/override")
def apply_override(bidder_id: int, req: OverrideRequest, db: Session = Depends(get_db)):
    rr = db.query(RuleResult).filter(RuleResult.bidder_id == bidder_id, RuleResult.rule_id == req.rule_id).first()
    if not rr:
        raise HTTPException(status_code=404, detail="Rule result not found")

    rr.officer_override = req.new_outcome
    rr.override_reason = req.reason
    rr.override_by = req.officer_name
    rr.override_at = datetime.utcnow()
    db.commit()

    record_audit_action(
        db,
        action_type=ActionType.OVERRIDE,
        actor=req.officer_name,
        payload={"rule_id": req.rule_id, "bidder_id": bidder_id, "new_outcome": req.new_outcome, "reason": req.reason},
        bidder_id=bidder_id,
    )
    return {"status": "success", "override_recorded": True}


@app.get("/audit/verify")
def verify_audit(db: Session = Depends(get_db)):
    is_valid, broken_row_id, message = verify_audit_chain(db)
    return {
        "is_valid": is_valid,
        "broken_row_id": broken_row_id,
        "message": message,
    }
