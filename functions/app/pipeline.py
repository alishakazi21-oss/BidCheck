"""
BidCheck - End-to-End Pipeline Orchestrator.

Initializes demo database, ingests tender and bidder documents,
executes deterministic rule evaluation, and synchronizes scores and audit logs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.audit.chain import record_audit_action
from app.extraction.intake import ingest_bidder_document
from app.extraction.tender_parser import parse_tender_document, save_parsed_tender_to_db
from app.models.database import (
    ActionType,
    Base,
    Benchmark,
    Bidder,
    Criterion,
    Document,
    ExtractedField,
    Flag,
    RuleResult,
    Tender,
    create_tables,
    get_engine,
)
from app.models.session import SessionLocal
from app.rules.assessment import evaluate_bidder
from app.rules.engine import RuleEngine

logger = logging.getLogger(__name__)

BIDDER_CONFIGS = [
    {
        "label": "Bidder A",
        "name": "TechServe Solutions Pvt. Ltd.",
        "claimed_categories": ["MSE"],
        "quoted_price": 5800000.0,
        "dir": "bidder_a",
    },
    {
        "label": "Bidder B",
        "name": "DataPrime Enterprises",
        "claimed_categories": [],
        "quoted_price": 6200000.0,
        "dir": "bidder_b",
    },
    {
        "label": "Bidder C",
        "name": "QuickByte Systems",
        "claimed_categories": ["MSE"],
        "quoted_price": 5400000.0,
        "dir": "bidder_c",
    },
    {
        "label": "Bidder D",
        "name": "GlobalEdge IT Private Limited",
        "claimed_categories": ["MSE"],
        "quoted_price": 7100000.0,
        "dir": "bidder_d",
    },
    {
        "label": "Bidder E",
        "name": "NanoTech Components Pvt. Ltd.",
        "claimed_categories": ["MSE"],
        "quoted_price": 5950000.0,
        "dir": "bidder_e",
    },
]


def setup_demo_environment(session: Session, force_reset: bool = False) -> Tender:
    """
    Ensure tender, bidders, and dummy documents are loaded into the database.
    """
    tender_pdf = Path("data/dummy/tender/tender_GeM_2024_B_1234567.pdf")
    tender_json = Path("data/dummy/tender/tender_GeM_2024_B_1234567.json")

    existing_tender = session.query(Tender).filter(Tender.gem_id == "GeM/2024/B/1234567").first()

    if force_reset or not existing_tender:
        if force_reset and existing_tender:
            session.delete(existing_tender)
            session.commit()

        # 1. Parse and save tender
        parsed = parse_tender_document(str(tender_pdf), str(tender_json))
        tender = save_parsed_tender_to_db(session, parsed, str(tender_pdf))

        # Officer confirms criteria for demo baseline
        tender.criteria_confirmed = True
        for c in tender.criteria:
            c.confirmed = True
        session.commit()

        # 2. Ingest bidders and documents
        for b_cfg in BIDDER_CONFIGS:
            bidder = Bidder(
                tender_id=tender.id,
                name=b_cfg["name"],
                label=b_cfg["label"],
                claimed_categories=b_cfg["claimed_categories"],
                quoted_price=b_cfg["quoted_price"],
            )
            session.add(bidder)
            session.flush()

            # Ingest all PDF documents in bidder directory
            bidder_dir = Path("data/dummy") / b_cfg["dir"]
            if bidder_dir.is_dir():
                for pdf_file in sorted(bidder_dir.glob("*.pdf")):
                    ingest_bidder_document(
                        session=session,
                        bidder=bidder,
                        pdf_path=str(pdf_file),
                        sidecar_path=str(pdf_file.with_suffix(".json")),
                    )

        session.commit()

        # 3. Load benchmarks if empty
        if session.query(Benchmark).count() == 0:
            sample_csv = Path("data/kaggle_sample/procurement_benchmarks_sample.csv")
            if sample_csv.is_file():
                from scripts.load_kaggle_data import load_file
                benchmarks = load_file(sample_csv, "Kaggle Proxy: Sample")
                if benchmarks:
                    session.add_all(benchmarks)
                    session.commit()

        # 4. Run initial evaluation across all bidders
        for b in tender.bidders:
            evaluate_bidder(session, b.id, actor="SystemInitialization")

        record_audit_action(
            session=session,
            action_type=ActionType.UPLOAD,
            actor="SystemSetup",
            payload={"action": "demo_environment_initialized", "bidders_count": len(tender.bidders)},
            tender_id=tender.id,
        )

        session.refresh(tender)
        return tender

    return existing_tender
