"""
BidCheck - PDF Analyzer & Document Inspection.

Inspects PDF files:
- Computes SHA-256 integrity hash.
- Reads document metadata (Producer, CreationDate, etc.).
- Distinguishes digital text PDFs vs scanned image pages.
- Renders page images with optional evidence bounding box highlight for evidence viewing.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# fitz (PyMuPDF) is imported lazily inside each function so this module
# loads cleanly in slim environments (Vercel) where PyMuPDF is not installed.


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def inspect_pdf(file_path: str) -> Dict[str, Any]:
    """
    Inspect PDF document structure, page count, metadata, and digital vs scanned status.
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256_hash = compute_sha256(file_path)
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF inspection but is not installed.") from exc
    doc = fitz.open(file_path)
    page_count = len(doc)
    metadata = doc.metadata or {}

    scanned_pages = []
    for page_idx in range(page_count):
        page = doc[page_idx]
        text = page.get_text().strip()
        images = page.get_images()
        # Page is considered scanned if it has very little text (<30 chars) but has images
        is_scanned = len(text) < 30 and len(images) > 0
        if is_scanned:
            scanned_pages.append(page_idx + 1)

    has_scanned = len(scanned_pages) > 0
    doc.close()

    return {
        "file_path": str(p.resolve()),
        "filename": p.name,
        "sha256": sha256_hash,
        "page_count": page_count,
        "metadata": metadata,
        "has_scanned_pages": has_scanned,
        "scanned_page_numbers": scanned_pages,
    }


def render_pdf_page_with_highlight(
    file_path: str,
    page_number: int = 1,
    bbox: Optional[List[float]] = None,
    zoom: float = 2.0,
) -> bytes:
    """
    Render a specific PDF page to PNG image bytes.
    If bbox [x0, y0, x1, y1] is provided, highlights the bounding box region in yellow/orange.
    """
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF rendering but is not installed.") from exc
    doc = fitz.open(file_path)
    zero_based_page = max(0, min(page_number - 1, len(doc) - 1))
    page = doc[zero_based_page]

    if bbox and len(bbox) == 4:
        rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])  # fitz already imported above
        # Add highlight annotation with yellow fill and transparent border
        highlight = page.add_rect_annot(rect)
        highlight.set_colors(stroke=(1.0, 0.7, 0.0), fill=(1.0, 0.9, 0.2))
        highlight.set_opacity(0.4)
        highlight.update()

    matrix = fitz.Matrix(zoom, zoom)  # fitz already imported above
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes
