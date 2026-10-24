"""
Unit tests for Phase 1: Data model and dummy data generator.
"""

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect

from app.models.database import (
    Base, Tender, Criterion, Bidder, Document,
    ExtractedField, RuleResult, Flag, Decision,
    AuditLog, Benchmark, get_engine, create_tables
)
from app.config import BASE_DIR


@pytest.fixture(scope="module")
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    yield engine
    Base.metadata.drop_all(engine)


def test_all_tables_created(memory_db):
    """Verify that all 10 required database tables are declared and created."""
    inspector = inspect(memory_db)
    table_names = set(inspector.get_table_names())
    expected_tables = {
        "tenders", "criteria", "bidders", "documents",
        "extracted_fields", "rule_results", "flags",
        "decisions", "audit_log", "benchmarks"
    }
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"


def test_dummy_data_files_exist():
    """Verify that make_dummy_data.py generated all expected files and manifest."""
    dummy_dir = BASE_DIR / "data" / "dummy"
    manifest_path = dummy_dir / "manifest.json"
    assert manifest_path.exists(), "Manifest file does not exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    tender_pdf = Path(manifest["tender"]["pdf"])
    tender_json = Path(manifest["tender"]["sidecar"])
    assert tender_pdf.exists(), "Tender PDF does not exist"
    assert tender_json.exists(), "Tender sidecar JSON does not exist"

    bidders = manifest["bidders"]
    assert len(bidders) == 5, f"Expected 5 bidders, got {len(bidders)}"

    labels = {b["label"] for b in bidders}
    assert labels == {"Bidder A", "Bidder B", "Bidder C", "Bidder D", "Bidder E"}


def test_planted_issues_in_sidecars():
    """Verify all planted problems are correctly represented in sidecar JSONs."""
    dummy_dir = BASE_DIR / "data" / "dummy"

    # Bidder A: Compliant
    bidder_a_turnover = dummy_dir / "bidder_a" / "turnover_certificate.json"
    assert bidder_a_turnover.exists()
    with open(bidder_a_turnover, "r", encoding="utf-8") as f:
        data_a = json.load(f)
    assert data_a["fields"]["avg_turnover_3y"]["value"] == 4500000.0

    # Bidder B: GSTIN/PAN Name Mismatch (LLP vs non-LLP)
    bidder_b_gst = dummy_dir / "bidder_b" / "gst_certificate.json"
    bidder_b_pan = dummy_dir / "bidder_b" / "pan_card.json"
    with open(bidder_b_gst, "r", encoding="utf-8") as f:
        data_b_gst = json.load(f)
    with open(bidder_b_pan, "r", encoding="utf-8") as f:
        data_b_pan = json.load(f)
    gst_name = data_b_gst["fields"]["company_name_gst"]["value"]
    pan_name = data_b_pan["fields"]["company_name_pan"]["value"]
    assert "LLP" in gst_name
    assert "LLP" not in pan_name

    # Bidder C: Turnover < 32L and invalid MSE proof
    bidder_c_turnover = dummy_dir / "bidder_c" / "turnover_certificate.json"
    bidder_c_udyam = dummy_dir / "bidder_c" / "udyam_certificate.json"
    with open(bidder_c_turnover, "r", encoding="utf-8") as f:
        data_c_to = json.load(f)
    with open(bidder_c_udyam, "r", encoding="utf-8") as f:
        data_c_ud = json.load(f)
    assert data_c_to["fields"]["avg_turnover_3y"]["value"] == 1800000.0 < 3200000.0
    assert data_c_ud["fields"]["mse_proof_valid"]["value"] is False

    # Bidder D: Expired Udyam (2023-09-30) and missing OEM auth
    bidder_d_udyam = dummy_dir / "bidder_d" / "udyam_certificate.json"
    bidder_d_oem = dummy_dir / "bidder_d" / "oem_authorization.pdf"
    with open(bidder_d_udyam, "r", encoding="utf-8") as f:
        data_d_ud = json.load(f)
    assert data_d_ud["fields"]["udyam_valid_until"]["value"] == "2023-09-30"
    assert not bidder_d_oem.exists(), "Bidder D should NOT have an OEM authorization PDF"

    # Bidder E: Turnover < 32L, but MSE proof valid (Positive Control)
    bidder_e_turnover = dummy_dir / "bidder_e" / "turnover_certificate.json"
    bidder_e_udyam = dummy_dir / "bidder_e" / "udyam_certificate.json"
    with open(bidder_e_turnover, "r", encoding="utf-8") as f:
        data_e_to = json.load(f)
    with open(bidder_e_udyam, "r", encoding="utf-8") as f:
        data_e_ud = json.load(f)
    assert data_e_to["fields"]["avg_turnover_3y"]["value"] == 1200000.0 < 3200000.0
    assert data_e_ud["fields"]["mse_proof_valid"]["value"] is True
