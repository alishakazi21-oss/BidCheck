"""
BidCheck - Tender Parser.

Parses tender documents into structured checklists.
Ensures criteria start in unconfirmed status until the procurement officer reviews
and explicitly confirms the extracted criteria.
"""

from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.extraction.base import BaseExtractor
from app.extraction.factory import get_extractor
from app.extraction.schema import ParsedTenderSchema
from app.models.database import Tender, Criterion


def parse_tender_document(
    pdf_path: str,
    sidecar_path: Optional[str] = None,
    extractor: Optional[BaseExtractor] = None,
) -> ParsedTenderSchema:
    """
    Extract structured checklist from a tender PDF.
    """
    ext = extractor or get_extractor()
    return ext.extract_tender(pdf_path=pdf_path, sidecar_path=sidecar_path)


def save_parsed_tender_to_db(
    session: Session,
    parsed: ParsedTenderSchema,
    pdf_path: Optional[str] = None,
) -> Tender:
    """
    Persist or update parsed tender and criteria in the database.
    Initially marks criteria_confirmed=False so the officer must review them.
    """
    # Check if tender already exists by gem_id
    tender = session.query(Tender).filter(Tender.gem_id == parsed.gem_id).first()
    deadline = None
    if parsed.bid_submission_deadline:
        try:
            deadline = datetime.strptime(parsed.bid_submission_deadline, "%Y-%m-%d").date()
        except Exception:
            deadline = None

    if not tender:
        tender = Tender(
            gem_id=parsed.gem_id,
            title=parsed.title,
            category=parsed.category,
            description=parsed.description,
            bid_submission_deadline=deadline,
            criteria_confirmed=False,
            criteria_json=parsed.model_dump(),
            tender_pdf_path=pdf_path,
        )
        session.add(tender)
        session.flush()
    else:
        tender.title = parsed.title
        tender.category = parsed.category
        tender.description = parsed.description
        tender.bid_submission_deadline = deadline
        tender.criteria_json = parsed.model_dump()
        if pdf_path:
            tender.tender_pdf_path = pdf_path
        session.flush()

    # Clear existing unconfirmed criteria to refresh
    session.query(Criterion).filter(Criterion.tender_id == tender.id).delete()

    for rule_id, crit_data in parsed.criteria.items():
        criterion = Criterion(
            tender_id=tender.id,
            rule_id=rule_id,
            label=crit_data.label,
            mandatory=crit_data.mandatory,
            threshold_value=crit_data.threshold_value,
            threshold_unit=crit_data.threshold_unit,
            exemption_categories=crit_data.exemption_categories,
            confirmed=False,  # Officer must confirm
        )
        session.add(criterion)

    session.commit()
    session.refresh(tender)
    return tender


def confirm_tender_criteria(
    session: Session,
    tender_id: int,
    criteria_updates: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tender:
    """
    Officer reviews, optionally edits thresholds/exemptions, and confirms the criteria.
    """
    tender = session.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise ValueError(f"Tender {tender_id} not found")

    if criteria_updates:
        for rule_id, updates in criteria_updates.items():
            crit = (
                session.query(Criterion)
                .filter(Criterion.tender_id == tender_id, Criterion.rule_id == rule_id)
                .first()
            )
            if crit:
                if "threshold_value" in updates:
                    crit.threshold_value = str(updates["threshold_value"]) if updates["threshold_value"] is not None else None
                if "mandatory" in updates:
                    crit.mandatory = bool(updates["mandatory"])
                if "exemption_categories" in updates:
                    crit.exemption_categories = updates["exemption_categories"]
                crit.confirmed = True

    # Mark all criteria and the tender confirmed
    for crit in tender.criteria:
        crit.confirmed = True
    tender.criteria_confirmed = True

    session.commit()
    session.refresh(tender)
    return tender
