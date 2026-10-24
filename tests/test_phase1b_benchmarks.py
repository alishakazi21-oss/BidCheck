"""
Unit tests for Phase 1b: Kaggle benchmark data loading and normalisation.
"""

from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, Benchmark, create_tables
from scripts.load_kaggle_data import (
    inspect_csv_columns, infer_column_mapping,
    map_category, parse_numeric, parse_year, load_file
)
from app.config import BASE_DIR


def test_schema_inspection():
    """Test dynamic CSV header and row inspection."""
    sample_csv = BASE_DIR / "data" / "kaggle_sample" / "procurement_benchmarks_sample.csv"
    assert sample_csv.exists()

    columns, sample_rows = inspect_csv_columns(sample_csv)
    assert len(columns) == 8
    assert len(sample_rows) == 5

    mapping = infer_column_mapping(columns)
    assert mapping["amount"] == "award_amount"
    assert mapping["currency"] == "currency"
    assert mapping["category"] == "category_raw"


def test_category_mapping():
    """Verify category mapping converts freeform text into standard taxonomy."""
    assert map_category("IT Equipment", "Laptops 200 units") == "IT Hardware"
    assert map_category("Hardware - IT", "Standard notebook computers") == "IT Hardware"
    assert map_category("Office Supplies", "Chairs and desks") == "Office Equipment"
    assert map_category("Network Infrastructure", "Switches and routers") == "Network Infrastructure"
    assert map_category("Misc Services", "Consulting and advice") == "General Supplies"


def test_currency_and_numeric_parsing():
    """Verify numeric extraction handles formatted currency strings."""
    assert parse_numeric("1,250,000.50") == 1250000.5
    assert parse_numeric("₹ 75,00,000") == 7500000.0
    assert parse_numeric("$5000") == 5000.0
    assert parse_numeric("invalid") is None


def test_year_parsing():
    """Verify 4-digit year extraction from various date formats."""
    assert parse_year("2023-05-12") == 2023
    assert parse_year("2024") == 2024
    assert parse_year("Awarded on 15/10/2022") == 2022
    assert parse_year("N/A") is None


def test_load_sample_csv_into_database():
    """Verify full loading pipeline into an in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    sample_csv = BASE_DIR / "data" / "kaggle_sample" / "procurement_benchmarks_sample.csv"
    benchmarks = load_file(sample_csv, "Sample Test")

    assert len(benchmarks) >= 35
    session.add_all(benchmarks)
    session.commit()

    it_hardware_count = session.query(Benchmark).filter_by(category="IT Hardware").count()
    assert it_hardware_count >= 30, "Must have at least 30 IT Hardware records for IQR test"

    session.close()
