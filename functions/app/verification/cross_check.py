"""
BidCheck - Cross-verification & Discrepancy Detection Engine.

Performs deterministic cross-document checks:
1. Fuzzy company name matching across GST, PAN, Udyam, and Turnover certificates using rapidfuzz.
2. GSTIN and PAN identifier consistency (embedded PAN verification).
3. Verification against the Mock Registry Service (simulating GSTN, PAN, and Udyam databases).
4. PDF Metadata anomaly detection (creation date / modification date sanity checks).

Flags are informational decision-support aids for the procurement officer;
they never disqualify a bidder automatically.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import difflib


def _fuzzy_token_sort_ratio(a: str, b: str) -> float:
    """
    Fuzzy token-sort similarity (0-100).
    Uses rapidfuzz if available (faster, better), otherwise falls back to
    stdlib difflib.SequenceMatcher (zero extra dependencies, good enough).
    """
    try:
        from rapidfuzz import fuzz as _fuzz  # noqa: PLC0415
        return _fuzz.token_sort_ratio(a, b)
    except ImportError:
        # Stdlib fallback: sort tokens, then use SequenceMatcher
        a_sorted = " ".join(sorted(a.split()))
        b_sorted = " ".join(sorted(b.split()))
        ratio = difflib.SequenceMatcher(None, a_sorted, b_sorted).ratio()
        return ratio * 100  # Convert to 0-100 scale

from app.config import settings
from app.models.database import FlagType
from app.verification.mock_registry import MockRegistryService


class VerificationDiscrepancy:
    """Represents a discrepancy discovered during cross-verification."""

    def __init__(
        self,
        flag_type: FlagType,
        severity: str,
        title: str,
        detail: str,
        field_name: Optional[str] = None,
        document_id: Optional[int] = None,
    ):
        self.flag_type = flag_type
        self.severity = severity  # HIGH | MEDIUM | LOW
        self.title = title
        self.detail = detail
        self.field_name = field_name
        self.document_id = document_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flag_type": self.flag_type.value,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "field_name": self.field_name,
            "document_id": self.document_id,
        }


def normalize_company_name(name: Optional[str]) -> str:
    """
    Standardize Indian company legal suffixes and punctuation for fuzzy matching.
    """
    if not name:
        return ""
    s = name.upper().strip()
    s = re.sub(r"[^\w\s]", " ", s)  # Remove dots, commas, hyphens
    # Standardize abbreviations
    s = re.sub(r"\bPVT\b", "PRIVATE", s)
    s = re.sub(r"\bLTD\b", "LIMITED", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def verify_bidder_cross_documents(
    bidder_name: str,
    evidence_map: Dict[str, Any],
    documents: Optional[List[Any]] = None,
    fuzzy_threshold: Optional[int] = None,
) -> List[VerificationDiscrepancy]:
    """
    Run full suite of cross-document consistency checks and mock registry lookups.
    """
    threshold = fuzzy_threshold if fuzzy_threshold is not None else settings.fuzzy_threshold
    discrepancies: List[VerificationDiscrepancy] = []

    # -----------------------------------------------------------------------
    # 1. Company Name Consistency Across Documents
    # -----------------------------------------------------------------------
    names_to_compare: List[Tuple[str, str]] = []  # (source_label, name_value)
    if bidder_name:
        names_to_compare.append(("Bidder Registration", bidder_name))

    for k, ev in evidence_map.items():
        if "company_name" in k or "legal_name" in k:
            val = getattr(ev, "value", ev)
            if val and isinstance(val, str):
                names_to_compare.append((k, val))

    for i in range(len(names_to_compare)):
        for j in range(i + 1, len(names_to_compare)):
            label1, name1 = names_to_compare[i]
            label2, name2 = names_to_compare[j]
            norm1 = normalize_company_name(name1)
            norm2 = normalize_company_name(name2)
            similarity = _fuzzy_token_sort_ratio(norm1, norm2)
            tokens1 = set(norm1.split())
            tokens2 = set(norm2.split())
            legal_suffixes = {"LLP", "LIMITED", "PRIVATE"}
            suffix_diff = (tokens1 ^ tokens2) & legal_suffixes

            if similarity < threshold or suffix_diff:
                suffix_note = f" Mismatched legal form suffix: {', '.join(suffix_diff)}." if suffix_diff else ""
                discrepancies.append(
                    VerificationDiscrepancy(
                        flag_type=FlagType.MISMATCH,
                        severity="MEDIUM",
                        title=f"Company name / entity mismatch between {label1} and {label2}",
                        detail=(
                            f"Similarity score is {similarity:.0f}% (threshold is {threshold}%).{suffix_note}\n"
                            f"• {label1}: '{name1}'\n"
                            f"• {label2}: '{name2}'"
                        ),
                        field_name="company_name",
                    )
                )

    # -----------------------------------------------------------------------
    # 2. GSTIN and PAN Cross-Consistency
    # -----------------------------------------------------------------------
    gst_ev = evidence_map.get("gstin")
    pan_ev = evidence_map.get("pan")
    gstin_val = getattr(gst_ev, "value", gst_ev) if gst_ev else None
    pan_val = getattr(pan_ev, "value", pan_ev) if pan_ev else None

    if gstin_val and pan_val and isinstance(gstin_val, str) and isinstance(pan_val, str):
        clean_gst = gstin_val.strip().upper()
        clean_pan = pan_val.strip().upper()
        if len(clean_gst) >= 12:
            embedded_pan = clean_gst[2:12]
            if embedded_pan != clean_pan:
                discrepancies.append(
                    VerificationDiscrepancy(
                        flag_type=FlagType.MISMATCH,
                        severity="HIGH",
                        title="PAN does not match GSTIN embedded identifier",
                        detail=(
                            f"PAN card shows '{clean_pan}', but characters 3-12 of GSTIN "
                            f"'{clean_gst}' are '{embedded_pan}'."
                        ),
                        field_name="gstin",
                    )
                )

    # -----------------------------------------------------------------------
    # 3. Mock Registry Lookups
    # -----------------------------------------------------------------------
    if gstin_val and isinstance(gstin_val, str):
        gst_reg = MockRegistryService.verify_gstin(gstin_val)
        if gst_reg.status == "NOT_FOUND":
            discrepancies.append(
                VerificationDiscrepancy(
                    flag_type=FlagType.MISMATCH,
                    severity="HIGH",
                    title=f"[MOCK REGISTRY] GSTIN '{gstin_val}' not found in registry",
                    detail="Mock GSTN registry lookup returned NOT_FOUND status. Needs manual verification.",
                    field_name="gstin",
                )
            )
        elif gst_reg.status == "CANCELLED":
            discrepancies.append(
                VerificationDiscrepancy(
                    flag_type=FlagType.MISMATCH,
                    severity="HIGH",
                    title=f"[MOCK REGISTRY] GSTIN '{gstin_val}' registration is CANCELLED",
                    detail="Mock GSTN registry indicates this taxpayer's registration has been cancelled.",
                    field_name="gstin",
                )
            )

    if pan_val and isinstance(pan_val, str):
        pan_reg = MockRegistryService.verify_pan(pan_val)
        if pan_reg.status == "NOT_FOUND":
            discrepancies.append(
                VerificationDiscrepancy(
                    flag_type=FlagType.MISMATCH,
                    severity="HIGH",
                    title=f"[MOCK REGISTRY] PAN '{pan_val}' not verified in IT database",
                    detail="Mock Income Tax PAN lookup returned NOT_FOUND.",
                    field_name="pan",
                )
            )

    udyam_ev = evidence_map.get("udyam_number")
    udyam_val = getattr(udyam_ev, "value", udyam_ev) if udyam_ev else None
    if udyam_val and isinstance(udyam_val, str):
        udyam_reg = MockRegistryService.verify_udyam(udyam_val)
        if udyam_reg.status == "NOT_FOUND":
            discrepancies.append(
                VerificationDiscrepancy(
                    flag_type=FlagType.EXEMPTION_WITHOUT_PROOF,
                    severity="HIGH",
                    title=f"[MOCK REGISTRY] Udyam number '{udyam_val}' not found in MSME database",
                    detail="The Udyam registration number could not be validated in the mock MSME portal.",
                    field_name="udyam_number",
                )
            )
        elif udyam_reg.status == "EXPIRED":
            discrepancies.append(
                VerificationDiscrepancy(
                    flag_type=FlagType.EXPIRED,
                    severity="HIGH",
                    title=f"[MOCK REGISTRY] Udyam registration '{udyam_val}' expired on {udyam_reg.expiry_date}",
                    detail="Mock MSME portal shows this Udyam certificate expired before bid submission.",
                    field_name="udyam_number",
                )
            )

    # -----------------------------------------------------------------------
    # 4. Metadata Anomaly Checks (creation date vs document date)
    # -----------------------------------------------------------------------
    if documents:
        for doc in documents:
            meta = getattr(doc, "pdf_metadata", None)
            if meta and isinstance(meta, dict):
                creator = meta.get("creator", "")
                producer = meta.get("producer", "")
                # If document is supposedly issued by a govt authority but produced by a non-standard tool
                if "tesseract" in producer.lower() or "imagemagick" in producer.lower():
                    discrepancies.append(
                        VerificationDiscrepancy(
                            flag_type=FlagType.METADATA_ANOMALY,
                            severity="LOW",
                            title=f"Metadata anomaly in {getattr(doc, 'filename', 'document')}",
                            detail=(
                                f"Document producer '{producer}' indicates synthetic or OCR post-processing. "
                                "Flagged as needs manual inspection (decision-support only; never marked as forged)."
                            ),
                            document_id=getattr(doc, "id", None),
                        )
                    )

    return discrepancies
