#!/usr/bin/env python3
"""
scripts/load_kaggle_data.py
===========================
Loads procurement benchmark data from CSV files into the `benchmarks` table.

FOREIGN PROXY DATA NOTICE:
Kaggle dataset records represent foreign/historical public procurement proxy data
(e.g., World Bank / international public contract notices), used exclusively for
market price and competition benchmarks. They are NEVER treated as Indian GeM ground truth.

Features:
  • Inspects input CSV columns dynamically without hardcoding assumptions.
  • Detects column mappings for: amount, currency, category, description, supplier, year, country.
  • Cleans missing values and converts currency to INR.
  • Normalises noisy category strings into a concise taxonomy:
      ['IT Hardware', 'Office Equipment', 'Network Infrastructure', 'Software & Cloud', 'General Supplies']
  • Loads into the `benchmarks` SQLite/PostgreSQL table via SQLAlchemy.
  • Falls back to `data/kaggle_sample/` if `data/kaggle/` has no CSV files.

Usage:
    python scripts/load_kaggle_data.py
    python scripts/load_kaggle_data.py --data-dir data/kaggle
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Safe stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.database import Benchmark, create_tables, get_engine
from app.models.session import SessionLocal

# Exchange rates to INR (standard conversion rates for proxy benchmark normalisation)
EXCHANGE_RATES_TO_INR: Dict[str, float] = {
    "INR": 1.0,
    "RS": 1.0,
    "RUPEES": 1.0,
    "USD": 84.0,
    "EUR": 91.0,
    "GBP": 108.0,
    "CAD": 61.5,
    "AUD": 55.0,
    "JPY": 0.56,
}

# Standard category taxonomy
TAXONOMY_MAP = {
    "IT Hardware": [
        "laptop", "computer", "notebook", "desktop", "hardware", "pc",
        "server", "workstation", "processor", "monitors", "it hardware"
    ],
    "Office Equipment": [
        "office", "furniture", "chair", "desk", "printer", "copier",
        "stationery", "paper", "supplies"
    ],
    "Network Infrastructure": [
        "network", "switch", "router", "cabling", "cable", "lan", "wan",
        "telecom", "firewall", "rack", "fiber"
    ],
    "Software & Cloud": [
        "software", "cloud", "saas", "license", "licence", "application",
        "erp", "hosting", "security"
    ],
}


def map_category(raw_category: str, description: str = "") -> str:
    """Map arbitrary category/description text to standard taxonomy."""
    text = f"{raw_category} {description}".lower()
    for standard_cat, keywords in TAXONOMY_MAP.items():
        if any(kw in text for kw in keywords):
            return standard_cat
    return "General Supplies"


def inspect_csv_columns(csv_path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Inspect CSV header and first 5 rows to understand column layout."""
    with open(csv_path, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        sample_rows = []
        for i, row in enumerate(reader):
            if i >= 5:
                break
            sample_rows.append(row)
    return fieldnames, sample_rows


def infer_column_mapping(columns: List[str]) -> Dict[str, Optional[str]]:
    """
    Dynamically identify relevant columns by matching candidate names.
    Does NOT assume strict column names.
    """
    col_lower = {c.lower().strip().replace(" ", "_"): c for c in columns}

    def find_best(candidates: List[str]) -> Optional[str]:
        for cand in candidates:
            for k, original in col_lower.items():
                if cand in k:
                    return original
        return None

    mapping = {
        "amount": find_best(["amount", "price", "award_val", "contract_val", "value", "total", "cost"]),
        "currency": find_best(["currency", "curr"]),
        "category": find_best(["category", "sector", "type", "commodity", "item_group"]),
        "description": find_best(["desc", "title", "item", "product", "detail", "subject", "name"]),
        "supplier": find_best(["supplier", "vendor", "contractor", "bidder", "company"]),
        "year": find_best(["year", "date", "contract_date", "award_date"]),
        "country": find_best(["country", "nation", "state", "location"]),
    }
    return mapping


def parse_numeric(val: Any) -> Optional[float]:
    """Parse numeric values with currency symbols, commas or scientific notation."""
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace("$", "").replace("₹", "").replace("€", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_year(val: Any) -> Optional[int]:
    """Extract 4-digit year from date or year field."""
    if not val:
        return None
    import re
    m = re.search(r"\b(20\d\d|19\d\d)\b", str(val))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def load_file(csv_path: Path, source_name: str) -> List[Benchmark]:
    """Inspect and load a single CSV file into Benchmark ORM instances."""
    columns, sample_rows = inspect_csv_columns(csv_path)

    print(f"\n========================================================")
    print(f"  Inspecting: {csv_path.name}")
    print(f"  Detected Columns ({len(columns)}): {', '.join(columns)}")
    print(f"========================================================")

    mapping = infer_column_mapping(columns)
    print("  Inferred Column Mapping:")
    for role, col in mapping.items():
        print(f"    - {role:12s} -> {col or '[NOT FOUND]'}")

    benchmarks: List[Benchmark] = []

    with open(csv_path, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 1. Extract and convert amount
            raw_amt_str = row.get(mapping["amount"], "") if mapping["amount"] else None
            raw_amt = parse_numeric(raw_amt_str)
            if raw_amt is None or raw_amt <= 0:
                continue  # Clean out missing or zero values

            # 2. Extract and normalise currency
            curr_str = (row.get(mapping["currency"], "") if mapping["currency"] else "INR").upper().strip()
            rate = EXCHANGE_RATES_TO_INR.get(curr_str, 1.0)
            award_inr = round(raw_amt * rate, 2)

            # 3. Category & Description
            raw_cat = (row.get(mapping["category"], "") if mapping["category"] else "General Supplies").strip()
            desc = (row.get(mapping["description"], "") if mapping["description"] else "").strip()
            standard_cat = map_category(raw_cat, desc)

            # 4. Year, Supplier, Country
            year_val = parse_year(row.get(mapping["year"], "")) if mapping["year"] else None
            supplier = (row.get(mapping["supplier"], "") if mapping["supplier"] else "").strip() or None
            country = (row.get(mapping["country"], "") if mapping["country"] else "India").strip() or None

            b = Benchmark(
                source_dataset=source_name,
                category=standard_cat,
                item_description=desc or raw_cat,
                award_value_inr=award_inr,
                raw_amount=raw_amt,
                raw_currency=curr_str or "INR",
                year=year_val,
                supplier_name=supplier,
                country=country,
            )
            benchmarks.append(b)

    print(f"  [+] Loaded {len(benchmarks)} valid records from {csv_path.name}")
    return benchmarks


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Kaggle procurement benchmark data into SQLite")
    parser.add_argument("--data-dir", default=None, help="Directory containing Kaggle CSVs")
    parser.add_argument("--append", action="store_true", help="Append instead of clearing benchmarks table")
    args = parser.parse_args()

    # Determine input directory
    target_dir = Path(args.data_dir) if args.data_dir else PROJECT_ROOT / "data" / "kaggle"
    sample_dir = PROJECT_ROOT / "data" / "kaggle_sample"

    # Fallback to sample directory if kaggle directory is missing or has no CSVs
    csv_files = list(target_dir.glob("*.csv")) if target_dir.exists() else []
    if not csv_files:
        print(f"[!] No CSV files found in '{target_dir}'. Falling back to sample directory '{sample_dir}'...")
        target_dir = sample_dir
        csv_files = list(target_dir.glob("*.csv"))

    if not csv_files:
        print(f"[X] No CSV files found in '{target_dir}'. Exiting.")
        sys.exit(1)

    print(f"[+] Found {len(csv_files)} CSV file(s) in: {target_dir}")

    engine = get_engine()
    create_tables(engine)

    session = SessionLocal()
    try:
        if not args.append:
            deleted_count = session.query(Benchmark).delete()
            session.commit()
            if deleted_count > 0:
                print(f"[+] Cleared {deleted_count} existing records from benchmarks table.")

        total_loaded = 0
        for csv_path in csv_files:
            source_dataset = f"Kaggle Proxy: {csv_path.stem}"
            records = load_file(csv_path, source_dataset)
            if records:
                session.add_all(records)
                session.commit()
                total_loaded += len(records)

        # Print category distribution
        from sqlalchemy import func
        dist = session.query(Benchmark.category, func.count(Benchmark.id)).group_by(Benchmark.category).all()
        print("\n========================================================")
        print("  Benchmark Data Distribution (Proxy Data):")
        print("========================================================")
        for cat, count in dist:
            print(f"    - {cat:25s}: {count:4d} records")
        print(f"  Total records in benchmarks table: {total_loaded}")
        print("========================================================\n")

    finally:
        session.close()


if __name__ == "__main__":
    main()
