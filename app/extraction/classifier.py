"""
BidCheck - Document Classifier.

Classifies uploaded bidder documents into standard DocumentType categories
based on file name heuristics and document text content.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# fitz (PyMuPDF) is imported lazily inside classify_document so this module
# loads cleanly in slim environments (Vercel) where PyMuPDF is not installed.
from app.models.database import DocumentType


KEYWORDS_MAP = {
    DocumentType.GST_CERTIFICATE: [
        r"goods and services tax",
        r"gstin",
        r"form gst reg-06",
        r"registration certificate",
    ],
    DocumentType.PAN_CARD: [
        r"income tax department",
        r"permanent account number",
        r"pan card",
    ],
    DocumentType.UDYAM_CERTIFICATE: [
        r"udyam registration",
        r"ministry of micro",
        r"udyam-",
        r"msme",
    ],
    DocumentType.TURNOVER_CERT: [
        r"turnover certificate",
        r"chartered accountant",
        r"udin",
        r"annual turnover",
    ],
    DocumentType.EXPERIENCE_LETTER: [
        r"experience certificate",
        r"work order",
        r"completion certificate",
        r"satisfactory performance",
        r"years in business",
    ],
    DocumentType.OEM_AUTHORIZATION: [
        r"manufacturer authorization",
        r"oem authorization",
        r"authorized partner",
        r"authorization letter",
    ],
    DocumentType.EMD_DOCUMENT: [
        r"earnest money deposit",
        r"emd",
        r"bank guarantee",
        r"demand draft",
        r"exemption",
    ],
}


def classify_document(file_path: str, hint_name: Optional[str] = None) -> DocumentType:
    """
    Classify a document into DocumentType based on filename and page text.
    """
    filename_lower = (hint_name or Path(file_path).name).lower()

    if "gst" in filename_lower:
        return DocumentType.GST_CERTIFICATE
    if "pan" in filename_lower:
        return DocumentType.PAN_CARD
    if "udyam" in filename_lower:
        return DocumentType.UDYAM_CERTIFICATE
    if "turnover" in filename_lower:
        return DocumentType.TURNOVER_CERT
    if "experience" in filename_lower:
        return DocumentType.EXPERIENCE_LETTER
    if "oem" in filename_lower or "auth" in filename_lower:
        return DocumentType.OEM_AUTHORIZATION
    if "emd" in filename_lower or "deposit" in filename_lower:
        return DocumentType.EMD_DOCUMENT

    # Fallback to inspecting text content
    try:
        import fitz  # PyMuPDF — lazy import, only for text-content fallback  # noqa: PLC0415
        doc = fitz.open(file_path)
        first_page_text = doc[0].get_text().lower() if len(doc) > 0 else ""
        doc.close()

        for doc_type, patterns in KEYWORDS_MAP.items():
            for pattern in patterns:
                if re.search(pattern, first_page_text, re.IGNORECASE):
                    return doc_type
    except Exception:
        pass

    return DocumentType.OTHER
