"""
Tests for Phase 5: Cross-Verification & Mock Registry Service.

Verifies:
1. Mock registry responses (is_mock=True, active/expired/not found).
2. Fuzzy company name matching using rapidfuzz across documents.
3. Detection of planted GSTIN vs PAN name discrepancy for Bidder B.
4. Embedded PAN cross-verification against GSTIN.
5. Udyam expiration and invalid status detection.
"""

from rapidfuzz import fuzz

from app.models.database import FlagType
from app.verification.cross_check import (
    normalize_company_name,
    verify_bidder_cross_documents,
)
from app.verification.mock_registry import MockRegistryService


def test_mock_registry_always_flags_is_mock():
    res = MockRegistryService.verify_gstin("27AABCT1234A1Z5")
    assert res.is_mock is True
    assert "MOCK REGISTRY" in res.disclaimer
    assert res.status == "ACTIVE"
    assert res.legal_name == "TECHSERVE SOLUTIONS PRIVATE LIMITED"


def test_mock_registry_udyam_expired_for_bidder_d():
    res = MockRegistryService.verify_udyam("UDYAM-TN-07-0089012")
    assert res.is_mock is True
    assert res.status == "EXPIRED"
    assert res.expiry_date == "2023-09-30"


def test_mock_registry_udyam_not_found_for_bidder_c():
    res = MockRegistryService.verify_udyam("UDYAM-HR-02-0034567")
    assert res.is_mock is True
    assert res.status == "NOT_FOUND"


def test_company_name_normalization():
    assert normalize_company_name("TechServe Solutions Pvt. Ltd.") == "TECHSERVE SOLUTIONS PRIVATE LIMITED"
    assert normalize_company_name("DataPrime Enterprises LLP") == "DATAPRIME ENTERPRISES LLP"


def test_planted_bidder_b_name_mismatch():
    # Bidder B has LLP in GST but not in PAN
    name_gst = "DATAPRIME ENTERPRISES LLP"
    name_pan = "DATAPRIME ENTERPRISES"

    evidence = {
        "company_name_gst": name_gst,
        "company_name_pan": name_pan,
        "gstin": "29BBBDE5678B1Z9",
        "pan": "BBBDE5678B",
    }
    discrepancies = verify_bidder_cross_documents(
        bidder_name="DataPrime Enterprises",
        evidence_map=evidence,
        fuzzy_threshold=85,
    )

    mismatch_flags = [d for d in discrepancies if d.flag_type == FlagType.MISMATCH]
    assert len(mismatch_flags) >= 1
    assert any("mismatch" in d.title.lower() for d in mismatch_flags)


def test_planted_bidder_d_udyam_expired_cross_check():
    evidence = {
        "udyam_number": "UDYAM-TN-07-0089012",
        "gstin": "33DDDGE3456D1Z7",
        "pan": "DDDGE3456D",
    }
    discrepancies = verify_bidder_cross_documents(
        bidder_name="GlobalEdge IT Private Limited",
        evidence_map=evidence,
    )

    expired_flags = [d for d in discrepancies if d.flag_type == FlagType.EXPIRED]
    assert len(expired_flags) == 1
    assert "expired" in expired_flags[0].title.lower()
