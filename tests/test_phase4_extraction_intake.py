"""
Tests for Phase 4: Document Intake, Classification, and Normalization.

Verifies:
1. Currency normalization for Indian crore, lakh, formatted commas.
2. Date parsing for various formats to ISO dates.
3. GSTIN and PAN syntax validation and cross-consistency check.
4. Document classification heuristics.
5. Ingestion of bidder documents into database and evidence map generation.
"""

from datetime import date
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, Bidder, Document, DocumentType, Tender
from app.extraction.normalizer import (
    normalize_currency,
    normalize_date,
    validate_gstin,
    validate_pan,
    check_gstin_pan_match,
)
from app.extraction.classifier import classify_document
from app.extraction.pdf_analyzer import inspect_pdf
from app.extraction.intake import ingest_bidder_document, load_bidder_evidence_map


def test_currency_normalization():
    assert normalize_currency("Rs. 45,00,000") == 4500000.0
    assert normalize_currency("45 Lakh") == 4500000.0
    assert normalize_currency("45 Lakhs") == 4500000.0
    assert normalize_currency("1.5 Crore") == 15000000.0
    assert normalize_currency("₹50,000") == 50000.0
    assert normalize_currency(3200000) == 3200000.0


def test_date_normalization():
    assert normalize_date("2024-12-31") == date(2024, 12, 31)
    assert normalize_date("31/12/2024") == date(2024, 12, 31)
    assert normalize_date("31-12-2024") == date(2024, 12, 31)
    assert normalize_date("31-Dec-2024") == date(2024, 12, 31)


def test_pan_and_gstin_validation():
    # Valid PAN & GSTIN
    valid_pan = "AAACT1234A"
    valid_gstin = "07AAACT1234A1Z5"

    is_pan_ok, _ = validate_pan(valid_pan)
    assert is_pan_ok is True

    is_gst_ok, _ = validate_gstin(valid_gstin)
    assert is_gst_ok is True

    match_ok, _ = check_gstin_pan_match(valid_gstin, valid_pan)
    assert match_ok is True

    # Inconsistent PAN & GSTIN (Bidder B planted problem)
    diff_pan = "BBBCT9999B"
    match_fail, err_msg = check_gstin_pan_match(valid_gstin, diff_pan)
    assert match_fail is False
    assert "mismatch" in err_msg.lower()


def test_document_classification():
    assert classify_document("data/dummy/bidder_a/gst_certificate.pdf") == DocumentType.GST_CERTIFICATE
    assert classify_document("data/dummy/bidder_a/pan_card.pdf") == DocumentType.PAN_CARD
    assert classify_document("data/dummy/bidder_a/turnover_certificate.pdf") == DocumentType.TURNOVER_CERT
    assert classify_document("data/dummy/bidder_a/experience_letter.pdf") == DocumentType.EXPERIENCE_LETTER


def test_pdf_inspection():
    pdf_path = "data/dummy/bidder_a/gst_certificate.pdf"
    info = inspect_pdf(pdf_path)
    assert info["page_count"] >= 1
    assert len(info["sha256"]) == 64
    assert "metadata" in info


def test_bidder_document_ingestion():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    tender = Tender(gem_id="GeM/2024/B/TEST", title="Test Tender")
    session.add(tender)
    session.flush()

    bidder = Bidder(tender_id=tender.id, name="TechServe Solutions Pvt. Ltd.", label="Bidder A")
    session.add(bidder)
    session.flush()

    # Ingest turnover certificate
    turnover_pdf = "data/dummy/bidder_a/turnover_certificate.pdf"
    doc = ingest_bidder_document(session, bidder, turnover_pdf)

    assert doc.id is not None
    assert doc.doc_type == DocumentType.TURNOVER_CERT.value

    # Ingest GST certificate
    gst_pdf = "data/dummy/bidder_a/gst_certificate.pdf"
    ingest_bidder_document(session, bidder, gst_pdf)

    evidence_map = load_bidder_evidence_map(session, bidder.id)
    assert "avg_turnover_3y" in evidence_map
    assert evidence_map["avg_turnover_3y"].value == 4500000.0
    assert evidence_map["avg_turnover_3y"].confidence > 0.8
    assert "gstin" in evidence_map

    session.close()
