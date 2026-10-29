"""
BidCheck Extraction Package.
"""

from app.extraction.base import BaseExtractor
from app.extraction.fake_extractor import FakeExtractor
from app.extraction.llm_extractor import LLMExtractor
from app.extraction.factory import get_extractor
from app.extraction.schema import (
    ExtractedFieldValue,
    ExtractedDocumentData,
    CriterionSchema,
    ParsedTenderSchema,
)
from app.extraction.tender_parser import (
    parse_tender_document,
    save_parsed_tender_to_db,
    confirm_tender_criteria,
)
from app.extraction.normalizer import (
    normalize_currency,
    normalize_date,
    validate_gstin,
    validate_pan,
    check_gstin_pan_match,
)
from app.extraction.pdf_analyzer import (
    inspect_pdf,
    compute_sha256,
    render_pdf_page_with_highlight,
)
from app.extraction.classifier import classify_document
from app.extraction.intake import (
    ingest_bidder_document,
    load_bidder_evidence_map,
)

__all__ = [
    "BaseExtractor",
    "FakeExtractor",
    "LLMExtractor",
    "get_extractor",
    "ExtractedFieldValue",
    "ExtractedDocumentData",
    "CriterionSchema",
    "ParsedTenderSchema",
    "parse_tender_document",
    "save_parsed_tender_to_db",
    "confirm_tender_criteria",
    "normalize_currency",
    "normalize_date",
    "validate_gstin",
    "validate_pan",
    "check_gstin_pan_match",
    "inspect_pdf",
    "compute_sha256",
    "render_pdf_page_with_highlight",
    "classify_document",
    "ingest_bidder_document",
    "load_bidder_evidence_map",
]
