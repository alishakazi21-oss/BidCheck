"""
BidCheck - Pydantic schemas for document extraction and tender parsing.

Strict schemas ensure that neither the LLM nor the mock extractor can inject
untyped, unvalidated or hallucinated structures into the database or rule engine.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ExtractedFieldValue(BaseModel):
    """
    Standard canonical representation of an extracted evidence value.
    Every extracted value carries confidence, page number, and evidence location.
    """
    value: Any = Field(default=None, description="The extracted data value (number, string, date, boolean)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score between 0.0 and 1.0")
    page: int = Field(default=1, ge=1, description="1-indexed document page number where evidence was located")
    snippet: Optional[str] = Field(default=None, description="Verbatim text snippet surrounding the extracted evidence")
    bbox: Optional[List[float]] = Field(default=None, description="Bounding box [x0, y0, x1, y1] on the PDF page")


class ExtractedDocumentData(BaseModel):
    """
    Structured fields extracted from a single bidder document.
    """
    bidder_label: Optional[str] = Field(default=None, description="Bidder label e.g. Bidder A")
    bidder_name: Optional[str] = Field(default=None, description="Legal company name stated on the document")
    doc_type: str = Field(description="Document type identifier, e.g. GST_CERTIFICATE, TURNOVER_CERT")
    filename: Optional[str] = Field(default=None, description="Document filename")
    sha256: Optional[str] = Field(default=None, description="SHA-256 integrity hash of document")
    fields: Dict[str, ExtractedFieldValue] = Field(default_factory=dict, description="Dictionary of canonical fields")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata such as creation date, producer")


class CriterionSchema(BaseModel):
    """
    A single criteria requirement parsed from a tender document.
    """
    rule_id: str = Field(description="Unique rule ID matching standard rules, e.g. TURNOVER_MIN")
    label: str = Field(description="Human readable title for the requirement")
    mandatory: bool = Field(default=True, description="Whether this criterion is mandatory for qualification")
    threshold_value: Optional[str] = Field(default=None, description="Threshold value as string, e.g. 3200000 or 3")
    threshold_unit: Optional[str] = Field(default=None, description="Unit e.g. INR, years, date")
    exemption_categories: List[str] = Field(default_factory=list, description="Categories entitled to exemption e.g. ['MSE', 'STARTUP']")


class ParsedTenderSchema(BaseModel):
    """
    Structured checklist parsed from a tender document.
    MUST be presented to the procurement officer for review and confirmation.
    """
    gem_id: str = Field(description="GeM tender reference identifier e.g. GeM/2024/B/1234567")
    title: str = Field(description="Tender subject / procurement title")
    category: str = Field(default="IT Hardware", description="GeM product/service category")
    description: Optional[str] = Field(default=None, description="Brief tender scope description")
    bid_submission_deadline: Optional[str] = Field(default=None, description="Deadline in YYYY-MM-DD format")
    criteria: Dict[str, CriterionSchema] = Field(default_factory=dict, description="Map of rule_id to CriterionSchema")
