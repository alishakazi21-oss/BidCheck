"""
Tests for Phase 3: Tender Parser & Extractor Interface.

Verifies:
1. Extraction of tender criteria via Extractor interface (FakeExtractor).
2. Schema validation against ParsedTenderSchema.
3. Unconfirmed state until officer review.
4. Officer editing and confirmation workflow.
5. Graceful fallback in LLMExtractor when no API key is present.
"""

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, Tender, Criterion
from app.extraction.fake_extractor import FakeExtractor
from app.extraction.llm_extractor import LLMExtractor
from app.extraction.factory import get_extractor
from app.extraction.tender_parser import (
    parse_tender_document,
    save_parsed_tender_to_db,
    confirm_tender_criteria,
)
from app.extraction.schema import ParsedTenderSchema

TENDER_PDF = Path("data/dummy/tender/tender_GeM_2024_B_1234567.pdf")
TENDER_JSON = Path("data/dummy/tender/tender_GeM_2024_B_1234567.json")


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_fake_extractor_extracts_tender():
    extractor = FakeExtractor()
    parsed = extractor.extract_tender(str(TENDER_PDF), str(TENDER_JSON))

    assert isinstance(parsed, ParsedTenderSchema)
    assert parsed.gem_id == "GeM/2024/B/1234567"
    assert "TURNOVER_MIN" in parsed.criteria
    assert parsed.criteria["TURNOVER_MIN"].threshold_value == "3200000"
    assert parsed.criteria["TURNOVER_MIN"].threshold_unit == "INR"
    assert "MSE" in parsed.criteria["TURNOVER_MIN"].exemption_categories
    assert "STARTUP" in parsed.criteria["TURNOVER_MIN"].exemption_categories


def test_tender_saved_as_unconfirmed_initially(db_session):
    parsed = parse_tender_document(str(TENDER_PDF), str(TENDER_JSON))
    tender = save_parsed_tender_to_db(db_session, parsed, str(TENDER_PDF))

    assert tender.id is not None
    assert tender.criteria_confirmed is False
    assert len(tender.criteria) == 6

    for crit in tender.criteria:
        assert crit.confirmed is False


def test_officer_review_and_confirm_criteria(db_session):
    parsed = parse_tender_document(str(TENDER_PDF), str(TENDER_JSON))
    tender = save_parsed_tender_to_db(db_session, parsed, str(TENDER_PDF))

    # Officer modifies turnover threshold from 32,00,000 to 35,00,000
    updates = {
        "TURNOVER_MIN": {
            "threshold_value": 3500000,
            "mandatory": True,
        }
    }
    confirmed_tender = confirm_tender_criteria(db_session, tender.id, updates)

    assert confirmed_tender.criteria_confirmed is True
    turnover_crit = next(c for c in confirmed_tender.criteria if c.rule_id == "TURNOVER_MIN")
    assert turnover_crit.threshold_value == "3500000"
    assert turnover_crit.confirmed is True


def test_llm_extractor_graceful_fallback_without_api_key():
    llm_ext = LLMExtractor(api_key="")
    parsed = llm_ext.extract_tender(str(TENDER_PDF), str(TENDER_JSON))

    assert isinstance(parsed, ParsedTenderSchema)
    assert parsed.gem_id == "GeM/2024/B/1234567"
    assert "TURNOVER_MIN" in parsed.criteria


def test_factory_extractor_selection(monkeypatch):
    monkeypatch.setenv("EXTRACTOR", "fake")
    ext = get_extractor("fake")
    assert isinstance(ext, FakeExtractor)

    ext_llm = get_extractor("llm")
    assert isinstance(ext_llm, LLMExtractor)
