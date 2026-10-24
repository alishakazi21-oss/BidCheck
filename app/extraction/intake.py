"""
BidCheck - Document Intake & Evidence Ingestion.

Coordinates document inspection, classification, extraction, normalization,
and database persistence. Produces normalized evidence maps for the deterministic rule engine.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session

from app.extraction.base import BaseExtractor
from app.extraction.classifier import classify_document
from app.extraction.factory import get_extractor
from app.extraction.normalizer import check_gstin_pan_match, normalize_currency, normalize_date
from app.extraction.pdf_analyzer import inspect_pdf
from app.models.database import Bidder, Document, DocumentType, ExtractedField
from app.rules.engine import FieldEvidence

logger = logging.getLogger(__name__)


def ingest_bidder_document(
    session: Session,
    bidder: Bidder,
    pdf_path: str,
    doc_type: Optional[str] = None,
    sidecar_path: Optional[str] = None,
    extractor: Optional[BaseExtractor] = None,
) -> Document:
    """
    Ingest a single bidder document:
    1. Inspects PDF for page count, metadata, scanned pages, and SHA-256 hash.
    2. Classifies document type if not explicitly supplied.
    3. Runs extractor (fake or llm) to retrieve fields with confidence & snippet.
    4. Normalizes field values (dates, currency).
    5. Persists Document and ExtractedField rows in SQLite/Postgres.
    """
    ext = extractor or get_extractor()
    p = Path(pdf_path)

    # 1. PDF Inspection
    pdf_info = inspect_pdf(pdf_path)

    # 2. Document Classification
    if not doc_type:
        dt_enum = classify_document(pdf_path)
        doc_type_str = dt_enum.value
    else:
        doc_type_str = doc_type

    # 3. Create or update Document record
    existing_doc = (
        session.query(Document)
        .filter(Document.bidder_id == bidder.id, Document.doc_type == doc_type_str)
        .first()
    )
    if existing_doc:
        doc_record = existing_doc
        doc_record.filename = p.name
        doc_record.file_path = str(p.resolve())
        doc_record.sidecar_json_path = sidecar_path or str(p.with_suffix(".json"))
        doc_record.sha256_hash = pdf_info["sha256"]
        doc_record.page_count = pdf_info["page_count"]
        doc_record.has_scanned_pages = pdf_info["has_scanned_pages"]
        doc_record.pdf_metadata = pdf_info["metadata"]
        doc_record.processed_at = datetime.utcnow()
        # Remove old extracted fields to refresh
        session.query(ExtractedField).filter(ExtractedField.document_id == doc_record.id).delete()
    else:
        doc_record = Document(
            bidder_id=bidder.id,
            doc_type=doc_type_str,
            filename=p.name,
            file_path=str(p.resolve()),
            sidecar_json_path=sidecar_path or (str(p.with_suffix(".json")) if p.with_suffix(".json").exists() else None),
            sha256_hash=pdf_info["sha256"],
            page_count=pdf_info["page_count"],
            has_scanned_pages=pdf_info["has_scanned_pages"],
            pdf_metadata=pdf_info["metadata"],
            processed_at=datetime.utcnow(),
        )
        session.add(doc_record)
        session.flush()

    # 4. Extract fields
    try:
        extracted_data = ext.extract_document(
            pdf_path=pdf_path,
            doc_type=doc_type_str,
            sidecar_path=sidecar_path,
        )
    except Exception as e:
        logger.warning("Extraction error on %s: %s", pdf_path, e)
        extracted_data = None

    # 5. Normalize and persist ExtractedField records
    if extracted_data and extracted_data.fields:
        for fname, fval in extracted_data.fields.items():
            raw_v = str(fval.value) if fval.value is not None else None
            typed_dict = None

            # Normalization heuristics
            if "turnover" in fname or "amount" in fname or "emd" in fname:
                num = normalize_currency(fval.value)
                if num is not None:
                    typed_dict = {"type": "float", "value": num}
            elif "date" in fname or "validity" in fname or "expiry" in fname:
                d = normalize_date(fval.value)
                if d is not None:
                    typed_dict = {"type": "date", "value": d.isoformat()}
            elif isinstance(fval.value, bool):
                typed_dict = {"type": "bool", "value": fval.value}
            elif isinstance(fval.value, (int, float)):
                typed_dict = {"type": "number", "value": fval.value}

            ef = ExtractedField(
                document_id=doc_record.id,
                bidder_id=bidder.id,
                field_name=fname,
                raw_value=raw_v,
                typed_value=typed_dict,
                confidence=fval.confidence,
                page_number=fval.page,
                bounding_box=fval.bbox,
                text_snippet=fval.snippet,
                extractor=ext.name,
            )
            session.add(ef)

    session.commit()
    session.refresh(doc_record)
    return doc_record


def load_bidder_evidence_map(session: Session, bidder_id: int) -> Dict[str, FieldEvidence]:
    """
    Load all extracted fields for a bidder into a dictionary of FieldEvidence objects
    consumed directly by the rule engine.
    """
    fields = (
        session.query(ExtractedField)
        .filter(ExtractedField.bidder_id == bidder_id)
        .all()
    )

    evidence_map: Dict[str, FieldEvidence] = {}
    for f in fields:
        # Determine typed or raw value
        val = f.raw_value
        if f.typed_value and "value" in f.typed_value:
            val = f.typed_value["value"]

        evidence_map[f.field_name] = FieldEvidence(
            field_name=f.field_name,
            value=val,
            confidence=f.confidence,
            source_document=f.document.filename if f.document else "",
            page_number=f.page_number or 1,
            snippet=f.text_snippet or "",
            bounding_box=f.bounding_box,
        )

    # Deterministically derive composite gst_pan_match if both gstin and pan exist
    if "gst_pan_match" not in evidence_map and "gstin" in evidence_map and "pan" in evidence_map:
        gst_ev = evidence_map["gstin"]
        pan_ev = evidence_map["pan"]
        is_consistent, _ = check_gstin_pan_match(str(gst_ev.value), str(pan_ev.value))

        name_gst = evidence_map.get("company_name_gst")
        name_pan = evidence_map.get("company_name_pan")
        if name_gst and name_pan and name_gst.value and name_pan.value:
            from app.verification.cross_check import normalize_company_name
            from rapidfuzz import fuzz

            norm_gst = normalize_company_name(str(name_gst.value))
            norm_pan = normalize_company_name(str(name_pan.value))
            sim = fuzz.token_sort_ratio(norm_gst, norm_pan)
            tokens_gst = set(norm_gst.split())
            tokens_pan = set(norm_pan.split())
            legal_diff = (tokens_gst ^ tokens_pan) & {"LLP", "LIMITED", "PRIVATE"}
            if sim < 85 or legal_diff:
                is_consistent = False

        evidence_map["gst_pan_match"] = FieldEvidence(
            field_name="gst_pan_match",
            value=is_consistent,
            confidence=min(gst_ev.confidence, pan_ev.confidence),
            snippet=f"GSTIN: {gst_ev.value}, PAN: {pan_ev.value}",
        )

    return evidence_map
