"""
BidCheck - SQLAlchemy ORM models.

All tables are defined here. Uses SQLite by default (Postgres-ready via
DATABASE_URL env var). Relationships are declared explicitly so that the
rule engine and API layers can navigate them without raw SQL.
"""

from __future__ import annotations

import enum
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, create_engine,
    event
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

from app.config import settings


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RuleOutcome(str, enum.Enum):
    """Possible outcomes from the deterministic rule engine."""
    PASS          = "PASS"
    FAIL          = "FAIL"
    EXEMPT        = "EXEMPT"
    NEEDS_REVIEW  = "NEEDS_REVIEW"


class FlagType(str, enum.Enum):
    """Types of compliance flags raised during verification."""
    MISSING_DOCUMENT        = "MISSING_DOCUMENT"
    EXPIRED                 = "EXPIRED"
    MISMATCH                = "MISMATCH"
    LOW_CONFIDENCE          = "LOW_CONFIDENCE"
    EXEMPTION_WITHOUT_PROOF = "EXEMPTION_WITHOUT_PROOF"
    METADATA_ANOMALY        = "METADATA_ANOMALY"
    PRICE_OUTLIER           = "PRICE_OUTLIER"


class RiskLevel(str, enum.Enum):
    """Overall risk level assigned to a bidder's submission."""
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class DocumentType(str, enum.Enum):
    """Recognised document types in a bidder's submission."""
    GST_CERTIFICATE    = "GST_CERTIFICATE"
    PAN_CARD           = "PAN_CARD"
    UDYAM_CERTIFICATE  = "UDYAM_CERTIFICATE"
    TURNOVER_CERT      = "TURNOVER_CERT"
    EXPERIENCE_LETTER  = "EXPERIENCE_LETTER"
    OEM_AUTHORIZATION  = "OEM_AUTHORIZATION"
    EMD_DOCUMENT       = "EMD_DOCUMENT"
    MSE_PROOF          = "MSE_PROOF"
    TENDER_DOCUMENT    = "TENDER_DOCUMENT"
    OTHER              = "OTHER"


class ActionType(str, enum.Enum):
    """Action types recorded in the audit log."""
    UPLOAD      = "UPLOAD"
    EXTRACT     = "EXTRACT"
    RULE_RUN    = "RULE_RUN"
    FLAG        = "FLAG"
    OVERRIDE    = "OVERRIDE"
    DECISION    = "DECISION"
    VERIFY_LOG  = "VERIFY_LOG"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Common base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class Tender(Base):
    """
    Represents a GeM tender (procurement opportunity).
    One tender can have many bidders responding to it.
    """
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gem_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False,
                                         comment="GeM tender reference number")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(64), default="IT Hardware",
                                                     comment="Tender item category for benchmark comparison")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bid_submission_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    criteria_confirmed: Mapped[bool] = mapped_column(Boolean, default=False,
                                                      comment="Officer has reviewed and confirmed criteria")
    # Raw criteria JSON as parsed from the tender document (officer may edit)
    criteria_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Path to the uploaded tender PDF
    tender_pdf_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                   onupdate=datetime.utcnow)

    # Relationships
    criteria: Mapped[list[Criterion]] = relationship("Criterion", back_populates="tender",
                                                      cascade="all, delete-orphan")
    bidders: Mapped[list[Bidder]] = relationship("Bidder", back_populates="tender",
                                                   cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Tender id={self.id} gem_id={self.gem_id!r}>"


class Criterion(Base):
    """
    A single compliance criterion extracted from a tender document.
    Stored as a structured row so the rule engine can query it directly.
    """
    __tablename__ = "criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenders.id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False,
                                          comment="References rules/<rule_id>.json")
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    # The threshold value (numeric, date, or string) as parsed from the tender
    threshold_value: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    threshold_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True,
                                                            comment="e.g. INR, years, %")
    # Any exemption categories allowed by this tender (stored as JSON list)
    exemption_categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False,
                                             comment="Officer has confirmed this threshold")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    tender: Mapped[Tender] = relationship("Tender", back_populates="criteria")
    rule_results: Mapped[list[RuleResult]] = relationship("RuleResult", back_populates="criterion",
                                                            cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Criterion id={self.id} rule_id={self.rule_id!r}>"


class Bidder(Base):
    """
    A company that has submitted a bid for a tender.
    Bidder data is always dummy/synthetic in this prototype.
    """
    __tablename__ = "bidders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenders.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    label: Mapped[str] = mapped_column(String(16), nullable=True,
                                        comment="Short label e.g. Bidder A, used in demo")
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    pan: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    udyam_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Categories: MSE, STARTUP, etc. (from claimed documents)
    claimed_categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Quoted bid price in INR (used for price anomaly check against benchmark data)
    quoted_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True,
                                                          comment="Quoted bid amount in INR")
    # Computed compliance score (0-100) after rule engine runs
    compliance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    tender: Mapped[Tender] = relationship("Tender", back_populates="bidders")
    documents: Mapped[list[Document]] = relationship("Document", back_populates="bidder",
                                                       cascade="all, delete-orphan")
    rule_results: Mapped[list[RuleResult]] = relationship("RuleResult", back_populates="bidder",
                                                            cascade="all, delete-orphan")
    flags: Mapped[list[Flag]] = relationship("Flag", back_populates="bidder",
                                              cascade="all, delete-orphan")
    decisions: Mapped[list[Decision]] = relationship("Decision", back_populates="bidder",
                                                      cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Bidder id={self.id} label={self.label!r} name={self.name!r}>"


class Document(Base):
    """
    A single document uploaded by a bidder (PDF or image).
    Tracks file path, SHA-256 hash for integrity, and processing status.
    """
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidder_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidders.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)  # DocumentType enum value
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # Sidecar JSON path (ground-truth fields for FakeExtractor)
    sidecar_json_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sha256_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # True if any page required OCR
    has_scanned_pages: Mapped[bool] = mapped_column(Boolean, default=False)
    # PDF metadata dict (creation date, producer, etc.)
    pdf_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    bidder: Mapped[Bidder] = relationship("Bidder", back_populates="documents")
    extracted_fields: Mapped[list[ExtractedField]] = relationship("ExtractedField",
                                                                    back_populates="document",
                                                                    cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document id={self.id} doc_type={self.doc_type!r} filename={self.filename!r}>"


class ExtractedField(Base):
    """
    A single field extracted from a document (e.g. gstin, avg_turnover_3y).
    Every value carries confidence, source location, and a text snippet for
    evidence highlighting. This is the canonical evidence record.

    IMPORTANT: The rule engine reads these fields; it never trusts an LLM
    to make a pass/fail decision.
    """
    __tablename__ = "extracted_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id"), nullable=False)
    bidder_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidders.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False,
                                             comment="Canonical field name e.g. avg_turnover_3y")
    # Stored as string; type coercion happens at rule-engine time
    raw_value: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # Python-typed value (after normalisation); stored as JSON for flexibility
    typed_value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True,
                                                          comment='{"type":"float","value":3200000}')
    confidence: Mapped[float] = mapped_column(Float, nullable=False,
                                               comment="0.0 to 1.0; <0.7 triggers NEEDS_REVIEW")
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Bounding box [x0, y0, x1, y1] in PDF points, or None for text-only
    bounding_box: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Text snippet for evidence display
    text_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Which extractor produced this (llm | fake)
    extractor: Mapped[str] = mapped_column(String(16), default="fake")
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="extracted_fields")

    def __repr__(self) -> str:
        return (f"<ExtractedField id={self.id} field={self.field_name!r} "
                f"value={self.raw_value!r} conf={self.confidence:.2f}>")


class RuleResult(Base):
    """
    The outcome of applying ONE rule to ONE bidder's extracted fields.
    Every result is deterministic - computed by the rule engine, never an LLM.
    """
    __tablename__ = "rule_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenders.id"), nullable=False)
    criterion_id: Mapped[int] = mapped_column(Integer, ForeignKey("criteria.id"), nullable=False)
    bidder_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidders.id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)  # RuleOutcome enum value
    # Human-readable reason text (must always be present)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # IDs of ExtractedField rows used as evidence
    evidence_field_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Officer can override the outcome; override reason is mandatory
    officer_override: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    override_reason: Mapped[str] = mapped_column(Text, nullable=True)
    override_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    override_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    criterion: Mapped[Criterion] = relationship("Criterion", back_populates="rule_results")
    bidder: Mapped[Bidder] = relationship("Bidder", back_populates="rule_results")

    def __repr__(self) -> str:
        return f"<RuleResult id={self.id} rule={self.rule_id!r} outcome={self.outcome!r}>"


class Flag(Base):
    """
    A compliance flag raised during cross-verification or document inspection.
    Flags are informational - they never automatically disqualify a bidder.
    """
    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidder_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidders.id"), nullable=False)
    flag_type: Mapped[str] = mapped_column(String(32), nullable=False)  # FlagType enum value
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM",
                                           comment="HIGH | MEDIUM | LOW")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Reference to the document or field that triggered the flag
    document_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("documents.id"),
                                                         nullable=True)
    field_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    bidder: Mapped[Bidder] = relationship("Bidder", back_populates="flags")

    def __repr__(self) -> str:
        return f"<Flag id={self.id} type={self.flag_type!r} bidder_id={self.bidder_id}>"


class Decision(Base):
    """
    The officer's final evaluation decision for a bidder.
    This is ALWAYS the officer's decision, never automatic. The system
    provides a recommendation, but the officer records the final verdict.
    """
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidder_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidders.id"), nullable=False)
    tender_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenders.id"), nullable=False)
    # System recommendation (not binding)
    system_recommendation: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Officer's final decision
    officer_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True,
                                                              comment="SHORTLIST | REJECT | REFER")
    officer_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    officer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Path to the exported evaluation report
    report_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Relationships
    bidder: Mapped[Bidder] = relationship("Bidder", back_populates="decisions")

    def __repr__(self) -> str:
        return (f"<Decision id={self.id} bidder_id={self.bidder_id} "
                f"officer_decision={self.officer_decision!r}>")


class AuditLog(Base):
    """
    Tamper-evident, hash-chained audit log.
    Every action (upload, extraction, rule run, flag, override, decision)
    appends a row. The hash column is SHA-256(prev_hash + canonical JSON).
    A broken chain indicates tampering.
    """
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)  # ActionType enum value
    actor: Mapped[str] = mapped_column(String(128), nullable=False,
                                        comment="User or system component performing action")
    # Payload is stored as canonical JSON (sorted keys, no whitespace variation)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Reference IDs (nullable; for human navigation)
    tender_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bidder_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    document_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # SHA-256 of (previous row's hash || canonical_json(this row's payload))
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False,
                                            comment="Hash of previous row; genesis='0'*64")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (f"<AuditLog id={self.id} action={self.action_type!r} "
                f"hash={self.row_hash[:8]}...>")


class Benchmark(Base):
    """
    Historical procurement benchmark record.
    Foreign proxy data (e.g. from Kaggle public procurement datasets)
    used strictly for price and competition benchmarks.
    Clearly marked as proxy data for demo and decision-support.
    """
    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    item_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    award_value_inr: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    raw_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_currency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (f"<Benchmark id={self.id} category={self.category!r} "
                f"award_inr={self.award_value_inr:,.0f}>")


# ---------------------------------------------------------------------------
# Engine / Session factory
# ---------------------------------------------------------------------------

def get_engine(database_url: str | None = None):
    """Create and return a SQLAlchemy engine."""
    url = database_url or settings.database_url
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        echo=settings.db_echo,
    )
    # Enable WAL mode for SQLite (better concurrent read performance)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def create_tables(engine) -> None:
    """Create all tables (idempotent)."""
    Base.metadata.create_all(engine)
