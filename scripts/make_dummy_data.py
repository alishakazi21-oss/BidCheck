#!/usr/bin/env python3
"""
scripts/make_dummy_data.py
==========================
Generates all synthetic demo data for BidCheck:

  • 1 dummy tender PDF + criteria JSON
  • 5 bidders (A-E) each with:
      - GST certificate PDF
      - PAN card PDF
      - Udyam certificate PDF
      - Turnover certificate PDF
      - Experience letter PDF
      - OEM authorization letter PDF
      (Bidder D deliberately lacks OEM auth)
  • A sidecar .json file next to every PDF with ground-truth fields
    used by the FakeExtractor (offline mode)

All planted issues are documented in data/PLANTED_ISSUES.md.
This script is idempotent: re-running it overwrites existing dummy data.

Usage:
    python scripts/make_dummy_data.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure project root is on the path when run directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Safe stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR   = PROJECT_ROOT / "data"
DUMMY_DIR  = DATA_DIR / "dummy"
TENDER_DIR = DUMMY_DIR / "tender"

DUMMY_DIR.mkdir(parents=True, exist_ok=True)
TENDER_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "BidTitle",
    parent=styles["Title"],
    fontSize=18,
    textColor=colors.HexColor("#1a237e"),
    spaceAfter=12,
)
HEADING_STYLE = ParagraphStyle(
    "BidHeading",
    parent=styles["Heading2"],
    fontSize=13,
    textColor=colors.HexColor("#283593"),
    spaceAfter=6,
)
BODY_STYLE = ParagraphStyle(
    "BidBody",
    parent=styles["Normal"],
    fontSize=10,
    leading=16,
    spaceAfter=4,
)
LABEL_STYLE = ParagraphStyle(
    "BidLabel",
    parent=styles["Normal"],
    fontSize=9,
    textColor=colors.HexColor("#757575"),
    spaceAfter=2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#bdbdbd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ])


def _make_pdf(path: Path, title: str, elements: list) -> str:
    """Build a PDF using ReportLab and return its SHA-256 hash."""
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story = [
        Paragraph("[DUMMY DATA - FOR DEMONSTRATION ONLY]", LABEL_STYLE),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e8eaf6")),
        Spacer(1, 0.3 * cm),
        Paragraph(title, TITLE_STYLE),
        Spacer(1, 0.3 * cm),
    ]
    story.extend(elements)
    doc.build(story)

    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return sha


def _write_sidecar(pdf_path: Path, fields: dict) -> None:
    """Write the ground-truth sidecar JSON next to a PDF."""
    sidecar_path = pdf_path.with_suffix(".json")
    sidecar_path.write_text(
        json.dumps(fields, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tender document
# ---------------------------------------------------------------------------

TENDER = {
    "gem_id": "GeM/2024/B/1234567",
    "title": "Supply of Laptop Computers (GeM Category: IT Hardware)",
    "description": (
        "Procurement of 200 laptop computers conforming to GeM specification "
        "LAPTOP/CORE_I5/16GB/512GB/WIN11. Bidders must comply with all eligibility "
        "criteria specified in this tender. This is a DUMMY tender for demonstration."
    ),
    "bid_submission_deadline": "2024-12-31",
    "criteria": {
        "TURNOVER_MIN": {
            "label": "Minimum Average Annual Turnover (3 years)",
            "mandatory": True,
            "threshold_value": "3200000",
            "threshold_unit": "INR",
            "exemption_categories": ["MSE", "STARTUP"],
        },
        "EXPERIENCE_YEARS_MIN": {
            "label": "Minimum Years in Business",
            "mandatory": True,
            "threshold_value": "3",
            "threshold_unit": "years",
            "exemption_categories": ["STARTUP"],
        },
        "OEM_AUTH_PRESENT": {
            "label": "OEM Authorization Letter Required",
            "mandatory": True,
            "threshold_value": None,
            "threshold_unit": None,
            "exemption_categories": ["OEM_ITSELF"],
        },
        "EMD_OR_EXEMPTION_PROOF": {
            "label": "EMD (₹50,000) or Valid Exemption Certificate",
            "mandatory": True,
            "threshold_value": "50000",
            "threshold_unit": "INR",
            "exemption_categories": ["MSE", "STARTUP"],
        },
        "CERT_VALIDITY": {
            "label": "All Certificates Valid on Bid Date",
            "mandatory": True,
            "threshold_value": "2024-12-31",
            "threshold_unit": "date",
            "exemption_categories": [],
        },
        "GSTIN_PAN_CONSISTENT": {
            "label": "GSTIN and PAN Company Name Match",
            "mandatory": True,
            "threshold_value": None,
            "threshold_unit": None,
            "exemption_categories": [],
        },
    },
}


def make_tender_pdf() -> Path:
    """Generate the dummy tender PDF and its sidecar JSON."""
    path = TENDER_DIR / "tender_GeM_2024_B_1234567.pdf"

    criteria_rows = [["Criterion", "Threshold", "Exemptions Allowed"]]
    for rule_id, c in TENDER["criteria"].items():
        thresh = c["threshold_value"] or "—"
        unit   = c["threshold_unit"] or ""
        exempt = ", ".join(c["exemption_categories"]) or "None"
        if unit == "INR" and thresh.isdigit():
            thresh = f"Rs. {int(thresh):,}"
        criteria_rows.append([c["label"], f"{thresh} {unit}".strip(), exempt])

    elements = [
        Paragraph("Government e-Marketplace (GeM) — Bid Document", HEADING_STYLE),
        Spacer(1, 0.2 * cm),
        Paragraph(f"<b>Tender ID:</b> {TENDER['gem_id']}", BODY_STYLE),
        Paragraph(f"<b>Category:</b> IT Hardware — Laptop Computers", BODY_STYLE),
        Paragraph(f"<b>Bid Submission Deadline:</b> {TENDER['bid_submission_deadline']}", BODY_STYLE),
        Spacer(1, 0.4 * cm),
        Paragraph("Description", HEADING_STYLE),
        Paragraph(TENDER["description"], BODY_STYLE),
        Spacer(1, 0.4 * cm),
        Paragraph("Eligibility Criteria", HEADING_STYLE),
        Table(criteria_rows, colWidths=[7 * cm, 4.5 * cm, 5 * cm], style=_table_style()),
        Spacer(1, 0.4 * cm),
        Paragraph("General Conditions", HEADING_STYLE),
        Paragraph(
            "1. All documents must be self-attested. "
            "2. MSE / Startup certificates must be valid on the bid submission date. "
            "3. GSTIN and PAN must belong to the same legal entity. "
            "4. OEM authorization must explicitly name this tender or category. "
            "5. All financial figures in Indian Rupees.",
            BODY_STYLE,
        ),
        Spacer(1, 0.6 * cm),
        Paragraph(
            "[NOTICE] THIS IS SYNTHETIC DUMMY DATA GENERATED FOR A HACKATHON PROTOTYPE. "
            "DO NOT USE FOR ACTUAL PROCUREMENT.",
            LABEL_STYLE,
        ),
    ]

    sha = _make_pdf(path, TENDER["title"], elements)
    _write_sidecar(path, {"tender": TENDER, "sha256": sha})
    print(f"  [+] Tender PDF   : {path.name}")
    return path


# ---------------------------------------------------------------------------
# Per-bidder document definitions
# ---------------------------------------------------------------------------

BIDDERS = [
    # ------------------------------------------------------------------
    # Bidder A — Fully compliant
    # ------------------------------------------------------------------
    {
        "label": "Bidder A",
        "name": "TechServe Solutions Pvt. Ltd.",
        "gstin": "27AABCT1234A1Z5",
        "pan": "AABCT1234A",
        "udyam_number": "UDYAM-MH-10-0012345",
        "claimed_categories": ["MSE"],
        "dir": "bidder_a",
        "docs": {
            "gst_certificate": {
                "doc_type": "GST_CERTIFICATE",
                "filename": "gst_certificate.pdf",
                "fields": {
                    "gstin": {
                        "value": "27AABCT1234A1Z5",
                        "confidence": 0.98,
                        "page": 1,
                        "snippet": "GSTIN: 27AABCT1234A1Z5",
                        "bbox": [72, 300, 300, 320],
                    },
                    "company_name_gst": {
                        "value": "TECHSERVE SOLUTIONS PRIVATE LIMITED",
                        "confidence": 0.97,
                        "page": 1,
                        "snippet": "Legal Name: TECHSERVE SOLUTIONS PRIVATE LIMITED",
                        "bbox": [72, 320, 400, 340],
                    },
                    "gst_registration_date": {
                        "value": "2017-04-01",
                        "confidence": 0.95,
                        "page": 1,
                        "snippet": "Date of Registration: 01/04/2017",
                        "bbox": [72, 340, 300, 360],
                    },
                },
            },
            "pan_card": {
                "doc_type": "PAN_CARD",
                "filename": "pan_card.pdf",
                "fields": {
                    "pan": {
                        "value": "AABCT1234A",
                        "confidence": 0.99,
                        "page": 1,
                        "snippet": "Permanent Account Number: AABCT1234A",
                        "bbox": [72, 200, 300, 220],
                    },
                    "company_name_pan": {
                        "value": "TECHSERVE SOLUTIONS PRIVATE LIMITED",
                        "confidence": 0.98,
                        "page": 1,
                        "snippet": "Name: TECHSERVE SOLUTIONS PRIVATE LIMITED",
                        "bbox": [72, 220, 400, 240],
                    },
                },
            },
            "udyam_certificate": {
                "doc_type": "UDYAM_CERTIFICATE",
                "filename": "udyam_certificate.pdf",
                "fields": {
                    "udyam_number": {
                        "value": "UDYAM-MH-10-0012345",
                        "confidence": 0.97,
                        "page": 1,
                        "snippet": "Udyam Registration Number: UDYAM-MH-10-0012345",
                        "bbox": [72, 280, 350, 300],
                    },
                    "enterprise_category": {
                        "value": "Small",
                        "confidence": 0.95,
                        "page": 1,
                        "snippet": "Category: Small Enterprise",
                        "bbox": [72, 300, 250, 320],
                    },
                    "udyam_valid_until": {
                        "value": "2026-03-31",
                        "confidence": 0.94,
                        "page": 1,
                        "snippet": "Valid Until: 31/03/2026",
                        "bbox": [72, 320, 250, 340],
                    },
                    "mse_proof_valid": {
                        "value": True,
                        "confidence": 0.95,
                        "page": 1,
                        "snippet": "Category: Small Enterprise — Valid",
                        "bbox": [72, 300, 350, 340],
                    },
                },
            },
            "turnover_certificate": {
                "doc_type": "TURNOVER_CERT",
                "filename": "turnover_certificate.pdf",
                "fields": {
                    "avg_turnover_3y": {
                        "value": 4500000.0,
                        "confidence": 0.92,
                        "page": 1,
                        "snippet": "Average Annual Turnover (FY 2021-22, 2022-23, 2023-24): Rs. 45,00,000",
                        "bbox": [72, 350, 500, 380],
                    },
                    "turnover_fy1": {"value": 4200000.0, "confidence": 0.91, "page": 1,
                                     "snippet": "FY 2021-22: Rs. 42,00,000", "bbox": [72, 390, 400, 410]},
                    "turnover_fy2": {"value": 4500000.0, "confidence": 0.91, "page": 1,
                                     "snippet": "FY 2022-23: Rs. 45,00,000", "bbox": [72, 410, 400, 430]},
                    "turnover_fy3": {"value": 4800000.0, "confidence": 0.91, "page": 1,
                                     "snippet": "FY 2023-24: Rs. 48,00,000", "bbox": [72, 430, 400, 450]},
                },
            },
            "experience_letter": {
                "doc_type": "EXPERIENCE_LETTER",
                "filename": "experience_letter.pdf",
                "fields": {
                    "experience_years": {
                        "value": 7.0,
                        "confidence": 0.90,
                        "page": 1,
                        "snippet": "In business since April 2017 (7 years of experience)",
                        "bbox": [72, 300, 450, 320],
                    },
                    "incorporation_date": {
                        "value": "2017-04-01",
                        "confidence": 0.88,
                        "page": 1,
                        "snippet": "Date of Incorporation: 01/04/2017",
                        "bbox": [72, 320, 350, 340],
                    },
                },
            },
            "oem_authorization": {
                "doc_type": "OEM_AUTHORIZATION",
                "filename": "oem_authorization.pdf",
                "fields": {
                    "oem_name": {
                        "value": "LaptopTech Global Inc.",
                        "confidence": 0.96,
                        "page": 1,
                        "snippet": "OEM Name: LaptopTech Global Inc.",
                        "bbox": [72, 200, 350, 220],
                    },
                    "oem_auth_valid_until": {
                        "value": "2025-12-31",
                        "confidence": 0.95,
                        "page": 1,
                        "snippet": "Authorization valid until: 31/12/2025",
                        "bbox": [72, 380, 350, 400],
                    },
                    "oem_auth_present": {
                        "value": True,
                        "confidence": 0.96,
                        "page": 1,
                        "snippet": "This letter certifies authorization to supply LaptopTech products",
                        "bbox": [72, 250, 500, 280],
                    },
                },
            },
        },
    },

    # ------------------------------------------------------------------
    # Bidder B — GSTIN/PAN name mismatch (LLP suffix)
    # ------------------------------------------------------------------
    {
        "label": "Bidder B",
        "name": "DataPrime Enterprises",
        "gstin": "29BBBDE5678B1Z9",
        "pan": "BBBDE5678B",
        "udyam_number": "UDYAM-KA-05-0067890",
        "claimed_categories": [],
        "dir": "bidder_b",
        "docs": {
            "gst_certificate": {
                "doc_type": "GST_CERTIFICATE",
                "filename": "gst_certificate.pdf",
                "fields": {
                    "gstin": {"value": "29BBBDE5678B1Z9", "confidence": 0.98, "page": 1,
                               "snippet": "GSTIN: 29BBBDE5678B1Z9", "bbox": [72, 300, 300, 320]},
                    # PLANTED: GST name has LLP
                    "company_name_gst": {"value": "DATAPRIME ENTERPRISES LLP", "confidence": 0.97,
                                          "page": 1, "snippet": "Legal Name: DATAPRIME ENTERPRISES LLP",
                                          "bbox": [72, 320, 420, 340]},
                    "gst_registration_date": {"value": "2019-07-15", "confidence": 0.93, "page": 1,
                                               "snippet": "Date of Registration: 15/07/2019",
                                               "bbox": [72, 340, 300, 360]},
                },
            },
            "pan_card": {
                "doc_type": "PAN_CARD",
                "filename": "pan_card.pdf",
                "fields": {
                    "pan": {"value": "BBBDE5678B", "confidence": 0.99, "page": 1,
                             "snippet": "Permanent Account Number: BBBDE5678B",
                             "bbox": [72, 200, 300, 220]},
                    # PLANTED: PAN name lacks LLP
                    "company_name_pan": {"value": "DATAPRIME ENTERPRISES", "confidence": 0.98,
                                          "page": 1, "snippet": "Name: DATAPRIME ENTERPRISES",
                                          "bbox": [72, 220, 400, 240]},
                },
            },
            "udyam_certificate": {
                "doc_type": "UDYAM_CERTIFICATE",
                "filename": "udyam_certificate.pdf",
                "fields": {
                    "udyam_number": {"value": "UDYAM-KA-05-0067890", "confidence": 0.97, "page": 1,
                                      "snippet": "Udyam Registration Number: UDYAM-KA-05-0067890",
                                      "bbox": [72, 280, 380, 300]},
                    "enterprise_category": {"value": "Small", "confidence": 0.95, "page": 1,
                                             "snippet": "Category: Small Enterprise",
                                             "bbox": [72, 300, 250, 320]},
                    "udyam_valid_until": {"value": "2025-06-30", "confidence": 0.94, "page": 1,
                                           "snippet": "Valid Until: 30/06/2025",
                                           "bbox": [72, 320, 250, 340]},
                    "mse_proof_valid": {"value": True, "confidence": 0.94, "page": 1,
                                        "snippet": "Category: Small Enterprise — Valid",
                                        "bbox": [72, 300, 350, 340]},
                },
            },
            "turnover_certificate": {
                "doc_type": "TURNOVER_CERT",
                "filename": "turnover_certificate.pdf",
                "fields": {
                    "avg_turnover_3y": {"value": 5500000.0, "confidence": 0.91, "page": 1,
                                         "snippet": "Average Annual Turnover: Rs. 55,00,000",
                                         "bbox": [72, 350, 500, 380]},
                    "turnover_fy1": {"value": 5200000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2021-22: Rs. 52,00,000", "bbox": [72, 390, 400, 410]},
                    "turnover_fy2": {"value": 5500000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2022-23: Rs. 55,00,000", "bbox": [72, 410, 400, 430]},
                    "turnover_fy3": {"value": 5800000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2023-24: Rs. 58,00,000", "bbox": [72, 430, 400, 450]},
                },
            },
            "experience_letter": {
                "doc_type": "EXPERIENCE_LETTER",
                "filename": "experience_letter.pdf",
                "fields": {
                    "experience_years": {"value": 5.0, "confidence": 0.89, "page": 1,
                                          "snippet": "In business since 2019 (5 years)",
                                          "bbox": [72, 300, 450, 320]},
                    "incorporation_date": {"value": "2019-07-15", "confidence": 0.87, "page": 1,
                                            "snippet": "Date of Incorporation: 15/07/2019",
                                            "bbox": [72, 320, 350, 340]},
                },
            },
            "oem_authorization": {
                "doc_type": "OEM_AUTHORIZATION",
                "filename": "oem_authorization.pdf",
                "fields": {
                    "oem_name": {"value": "LaptopTech Global Inc.", "confidence": 0.96, "page": 1,
                                  "snippet": "OEM Name: LaptopTech Global Inc.",
                                  "bbox": [72, 200, 350, 220]},
                    "oem_auth_valid_until": {"value": "2025-12-31", "confidence": 0.95, "page": 1,
                                              "snippet": "Authorization valid until: 31/12/2025",
                                              "bbox": [72, 380, 350, 400]},
                    "oem_auth_present": {"value": True, "confidence": 0.96, "page": 1,
                                          "snippet": "This letter certifies authorization",
                                          "bbox": [72, 250, 500, 280]},
                },
            },
        },
    },

    # ------------------------------------------------------------------
    # Bidder C — Turnover below min; invalid MSE claim
    # ------------------------------------------------------------------
    {
        "label": "Bidder C",
        "name": "QuickByte Systems",
        "gstin": "06CCCQS9012C1Z3",
        "pan": "CCCQS9012C",
        "udyam_number": "UDYAM-HR-02-0034567",
        "claimed_categories": ["MSE"],
        "dir": "bidder_c",
        "docs": {
            "gst_certificate": {
                "doc_type": "GST_CERTIFICATE",
                "filename": "gst_certificate.pdf",
                "fields": {
                    "gstin": {"value": "06CCCQS9012C1Z3", "confidence": 0.98, "page": 1,
                               "snippet": "GSTIN: 06CCCQS9012C1Z3", "bbox": [72, 300, 300, 320]},
                    "company_name_gst": {"value": "QUICKBYTE SYSTEMS", "confidence": 0.97, "page": 1,
                                          "snippet": "Legal Name: QUICKBYTE SYSTEMS",
                                          "bbox": [72, 320, 350, 340]},
                    "gst_registration_date": {"value": "2020-03-10", "confidence": 0.93, "page": 1,
                                               "snippet": "Date of Registration: 10/03/2020",
                                               "bbox": [72, 340, 300, 360]},
                },
            },
            "pan_card": {
                "doc_type": "PAN_CARD",
                "filename": "pan_card.pdf",
                "fields": {
                    "pan": {"value": "CCCQS9012C", "confidence": 0.99, "page": 1,
                             "snippet": "Permanent Account Number: CCCQS9012C",
                             "bbox": [72, 200, 300, 220]},
                    "company_name_pan": {"value": "QUICKBYTE SYSTEMS", "confidence": 0.98, "page": 1,
                                          "snippet": "Name: QUICKBYTE SYSTEMS",
                                          "bbox": [72, 220, 350, 240]},
                },
            },
            "udyam_certificate": {
                "doc_type": "UDYAM_CERTIFICATE",
                "filename": "udyam_certificate.pdf",
                "fields": {
                    "udyam_number": {"value": "UDYAM-HR-02-0034567", "confidence": 0.97, "page": 1,
                                      "snippet": "Udyam Registration Number: UDYAM-HR-02-0034567",
                                      "bbox": [72, 280, 380, 300]},
                    "enterprise_category": {"value": "Micro", "confidence": 0.95, "page": 1,
                                             "snippet": "Category: Micro Enterprise",
                                             "bbox": [72, 300, 250, 320]},
                    "udyam_valid_until": {"value": "2025-12-31", "confidence": 0.94, "page": 1,
                                           "snippet": "Valid Until: 31/12/2025",
                                           "bbox": [72, 320, 250, 340]},
                    # PLANTED: mse_proof_valid = false
                    "mse_proof_valid": {"value": False, "confidence": 0.85, "page": 1,
                                        "snippet": "CAUTION: Certificate status: INVALID — See remarks",
                                        "bbox": [72, 340, 450, 360]},
                },
            },
            "turnover_certificate": {
                "doc_type": "TURNOVER_CERT",
                "filename": "turnover_certificate.pdf",
                "fields": {
                    # PLANTED: turnover below minimum (18L < 32L)
                    "avg_turnover_3y": {"value": 1800000.0, "confidence": 0.92, "page": 1,
                                         "snippet": "Average Annual Turnover: Rs. 18,00,000",
                                         "bbox": [72, 350, 500, 380]},
                    "turnover_fy1": {"value": 1600000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2021-22: Rs. 16,00,000", "bbox": [72, 390, 400, 410]},
                    "turnover_fy2": {"value": 1800000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2022-23: Rs. 18,00,000", "bbox": [72, 410, 400, 430]},
                    "turnover_fy3": {"value": 2000000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2023-24: Rs. 20,00,000", "bbox": [72, 430, 400, 450]},
                },
            },
            "experience_letter": {
                "doc_type": "EXPERIENCE_LETTER",
                "filename": "experience_letter.pdf",
                "fields": {
                    "experience_years": {"value": 4.0, "confidence": 0.89, "page": 1,
                                          "snippet": "In business since 2020 (4 years)",
                                          "bbox": [72, 300, 450, 320]},
                    "incorporation_date": {"value": "2020-03-10", "confidence": 0.87, "page": 1,
                                            "snippet": "Date of Incorporation: 10/03/2020",
                                            "bbox": [72, 320, 350, 340]},
                },
            },
            "oem_authorization": {
                "doc_type": "OEM_AUTHORIZATION",
                "filename": "oem_authorization.pdf",
                "fields": {
                    "oem_name": {"value": "LaptopTech Global Inc.", "confidence": 0.96, "page": 1,
                                  "snippet": "OEM Name: LaptopTech Global Inc.",
                                  "bbox": [72, 200, 350, 220]},
                    "oem_auth_valid_until": {"value": "2025-12-31", "confidence": 0.95, "page": 1,
                                              "snippet": "Authorization valid until: 31/12/2025",
                                              "bbox": [72, 380, 350, 400]},
                    "oem_auth_present": {"value": True, "confidence": 0.95, "page": 1,
                                          "snippet": "This letter certifies authorization",
                                          "bbox": [72, 250, 500, 280]},
                },
            },
        },
    },

    # ------------------------------------------------------------------
    # Bidder D — Expired Udyam + missing OEM auth
    # ------------------------------------------------------------------
    {
        "label": "Bidder D",
        "name": "GlobalEdge IT Pvt. Ltd.",
        "gstin": "33DDDGE3456D1Z7",
        "pan": "DDDGE3456D",
        "udyam_number": "UDYAM-TN-07-0089012",
        "claimed_categories": [],
        "dir": "bidder_d",
        "docs": {
            "gst_certificate": {
                "doc_type": "GST_CERTIFICATE",
                "filename": "gst_certificate.pdf",
                "fields": {
                    "gstin": {"value": "33DDDGE3456D1Z7", "confidence": 0.98, "page": 1,
                               "snippet": "GSTIN: 33DDDGE3456D1Z7", "bbox": [72, 300, 300, 320]},
                    "company_name_gst": {"value": "GLOBALEDGE IT PRIVATE LIMITED", "confidence": 0.97,
                                          "page": 1, "snippet": "Legal Name: GLOBALEDGE IT PRIVATE LIMITED",
                                          "bbox": [72, 320, 420, 340]},
                    "gst_registration_date": {"value": "2018-01-20", "confidence": 0.93, "page": 1,
                                               "snippet": "Date of Registration: 20/01/2018",
                                               "bbox": [72, 340, 300, 360]},
                },
            },
            "pan_card": {
                "doc_type": "PAN_CARD",
                "filename": "pan_card.pdf",
                "fields": {
                    "pan": {"value": "DDDGE3456D", "confidence": 0.99, "page": 1,
                             "snippet": "Permanent Account Number: DDDGE3456D",
                             "bbox": [72, 200, 300, 220]},
                    "company_name_pan": {"value": "GLOBALEDGE IT PRIVATE LIMITED", "confidence": 0.98,
                                          "page": 1, "snippet": "Name: GLOBALEDGE IT PRIVATE LIMITED",
                                          "bbox": [72, 220, 420, 240]},
                },
            },
            "udyam_certificate": {
                "doc_type": "UDYAM_CERTIFICATE",
                "filename": "udyam_certificate.pdf",
                "fields": {
                    "udyam_number": {"value": "UDYAM-TN-07-0089012", "confidence": 0.97, "page": 1,
                                      "snippet": "Udyam Registration Number: UDYAM-TN-07-0089012",
                                      "bbox": [72, 280, 380, 300]},
                    "enterprise_category": {"value": "Small", "confidence": 0.95, "page": 1,
                                             "snippet": "Category: Small Enterprise",
                                             "bbox": [72, 300, 250, 320]},
                    # PLANTED: Udyam expired before bid date
                    "udyam_valid_until": {"value": "2023-09-30", "confidence": 0.96, "page": 1,
                                           "snippet": "Valid Until: 30/09/2023",
                                           "bbox": [72, 320, 250, 340]},
                    "mse_proof_valid": {"value": True, "confidence": 0.92, "page": 1,
                                        "snippet": "Category: Small Enterprise",
                                        "bbox": [72, 300, 350, 340]},
                },
            },
            "turnover_certificate": {
                "doc_type": "TURNOVER_CERT",
                "filename": "turnover_certificate.pdf",
                "fields": {
                    "avg_turnover_3y": {"value": 4800000.0, "confidence": 0.91, "page": 1,
                                         "snippet": "Average Annual Turnover: Rs. 48,00,000",
                                         "bbox": [72, 350, 500, 380]},
                    "turnover_fy1": {"value": 4500000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2021-22: Rs. 45,00,000", "bbox": [72, 390, 400, 410]},
                    "turnover_fy2": {"value": 4800000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2022-23: Rs. 48,00,000", "bbox": [72, 410, 400, 430]},
                    "turnover_fy3": {"value": 5100000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2023-24: Rs. 51,00,000", "bbox": [72, 430, 400, 450]},
                },
            },
            "experience_letter": {
                "doc_type": "EXPERIENCE_LETTER",
                "filename": "experience_letter.pdf",
                "fields": {
                    "experience_years": {"value": 6.0, "confidence": 0.89, "page": 1,
                                          "snippet": "In business since 2018 (6 years)",
                                          "bbox": [72, 300, 450, 320]},
                    "incorporation_date": {"value": "2018-01-20", "confidence": 0.87, "page": 1,
                                            "snippet": "Date of Incorporation: 20/01/2018",
                                            "bbox": [72, 320, 350, 340]},
                },
            },
            # PLANTED: OEM authorization is intentionally MISSING for Bidder D
            # (no oem_authorization key in docs dict)
        },
    },

    # ------------------------------------------------------------------
    # Bidder E — MSE with valid proof; turnover below min → EXEMPT
    # ------------------------------------------------------------------
    {
        "label": "Bidder E",
        "name": "NanoTech Components Pvt. Ltd.",
        "gstin": "24EEETN7890E1Z1",
        "pan": "EEETN7890E",
        "udyam_number": "UDYAM-GJ-08-0056789",
        "claimed_categories": ["MSE"],
        "dir": "bidder_e",
        "docs": {
            "gst_certificate": {
                "doc_type": "GST_CERTIFICATE",
                "filename": "gst_certificate.pdf",
                "fields": {
                    "gstin": {"value": "24EEETN7890E1Z1", "confidence": 0.98, "page": 1,
                               "snippet": "GSTIN: 24EEETN7890E1Z1", "bbox": [72, 300, 300, 320]},
                    "company_name_gst": {"value": "NANOTECH COMPONENTS PRIVATE LIMITED",
                                          "confidence": 0.97, "page": 1,
                                          "snippet": "Legal Name: NANOTECH COMPONENTS PRIVATE LIMITED",
                                          "bbox": [72, 320, 450, 340]},
                    "gst_registration_date": {"value": "2021-06-01", "confidence": 0.93, "page": 1,
                                               "snippet": "Date of Registration: 01/06/2021",
                                               "bbox": [72, 340, 300, 360]},
                },
            },
            "pan_card": {
                "doc_type": "PAN_CARD",
                "filename": "pan_card.pdf",
                "fields": {
                    "pan": {"value": "EEETN7890E", "confidence": 0.99, "page": 1,
                             "snippet": "Permanent Account Number: EEETN7890E",
                             "bbox": [72, 200, 300, 220]},
                    "company_name_pan": {"value": "NANOTECH COMPONENTS PRIVATE LIMITED",
                                          "confidence": 0.98, "page": 1,
                                          "snippet": "Name: NANOTECH COMPONENTS PRIVATE LIMITED",
                                          "bbox": [72, 220, 450, 240]},
                },
            },
            "udyam_certificate": {
                "doc_type": "UDYAM_CERTIFICATE",
                "filename": "udyam_certificate.pdf",
                "fields": {
                    "udyam_number": {"value": "UDYAM-GJ-08-0056789", "confidence": 0.97, "page": 1,
                                      "snippet": "Udyam Registration Number: UDYAM-GJ-08-0056789",
                                      "bbox": [72, 280, 380, 300]},
                    "enterprise_category": {"value": "Micro", "confidence": 0.96, "page": 1,
                                             "snippet": "Category: Micro Enterprise",
                                             "bbox": [72, 300, 250, 320]},
                    "udyam_valid_until": {"value": "2026-12-31", "confidence": 0.96, "page": 1,
                                           "snippet": "Valid Until: 31/12/2026",
                                           "bbox": [72, 320, 250, 340]},
                    # KEY: mse_proof_valid = True (positive control)
                    "mse_proof_valid": {"value": True, "confidence": 0.97, "page": 1,
                                        "snippet": "Category: Micro Enterprise — VALID",
                                        "bbox": [72, 300, 350, 340]},
                },
            },
            "turnover_certificate": {
                "doc_type": "TURNOVER_CERT",
                "filename": "turnover_certificate.pdf",
                "fields": {
                    # Turnover below minimum → MSE exemption makes this EXEMPT
                    "avg_turnover_3y": {"value": 1200000.0, "confidence": 0.92, "page": 1,
                                         "snippet": "Average Annual Turnover: Rs. 12,00,000",
                                         "bbox": [72, 350, 500, 380]},
                    "turnover_fy1": {"value": 1100000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2021-22: Rs. 11,00,000", "bbox": [72, 390, 400, 410]},
                    "turnover_fy2": {"value": 1200000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2022-23: Rs. 12,00,000", "bbox": [72, 410, 400, 430]},
                    "turnover_fy3": {"value": 1300000.0, "confidence": 0.90, "page": 1,
                                     "snippet": "FY 2023-24: Rs. 13,00,000", "bbox": [72, 430, 400, 450]},
                },
            },
            "experience_letter": {
                "doc_type": "EXPERIENCE_LETTER",
                "filename": "experience_letter.pdf",
                "fields": {
                    "experience_years": {"value": 3.0, "confidence": 0.89, "page": 1,
                                          "snippet": "In business since June 2021 (3 years)",
                                          "bbox": [72, 300, 450, 320]},
                    "incorporation_date": {"value": "2021-06-01", "confidence": 0.87, "page": 1,
                                            "snippet": "Date of Incorporation: 01/06/2021",
                                            "bbox": [72, 320, 350, 340]},
                },
            },
            "oem_authorization": {
                "doc_type": "OEM_AUTHORIZATION",
                "filename": "oem_authorization.pdf",
                "fields": {
                    "oem_name": {"value": "LaptopTech Global Inc.", "confidence": 0.96, "page": 1,
                                  "snippet": "OEM Name: LaptopTech Global Inc.",
                                  "bbox": [72, 200, 350, 220]},
                    "oem_auth_valid_until": {"value": "2025-12-31", "confidence": 0.95, "page": 1,
                                              "snippet": "Authorization valid until: 31/12/2025",
                                              "bbox": [72, 380, 350, 400]},
                    "oem_auth_present": {"value": True, "confidence": 0.96, "page": 1,
                                          "snippet": "This letter certifies authorization",
                                          "bbox": [72, 250, 500, 280]},
                },
            },
        },
    },
]

# Map doc key → EMD sidecar fields (injected into the mock EMD document)
EMD_FIELDS = {
    "bidder_a": {"emd_amount": 50000.0, "emd_type": "BG", "emd_valid_until": "2025-03-31",
                  "emd_or_exemption_present": True, "confidence": 0.94},
    "bidder_b": {"emd_amount": 50000.0, "emd_type": "BG", "emd_valid_until": "2025-03-31",
                  "emd_or_exemption_present": True, "confidence": 0.92},
    "bidder_c": {"emd_amount": 0.0,     "emd_type": "MSE_EXEMPT", "emd_valid_until": None,
                  "emd_or_exemption_present": True, "confidence": 0.88},
    "bidder_d": {"emd_amount": 50000.0, "emd_type": "DD", "emd_valid_until": "2025-03-31",
                  "emd_or_exemption_present": True, "confidence": 0.91},
    "bidder_e": {"emd_amount": 0.0,     "emd_type": "MSE_EXEMPT", "emd_valid_until": None,
                  "emd_or_exemption_present": True, "confidence": 0.95},
}


# ---------------------------------------------------------------------------
# PDF generators for each document type
# ---------------------------------------------------------------------------

def _gst_elements(bidder: dict, fields: dict) -> list:
    f = fields
    rows = [
        ["GSTIN", f["gstin"]["value"]],
        ["Legal Name", f["company_name_gst"]["value"]],
        ["Registration Date", f["gst_registration_date"]["value"]],
        ["State", "As per GSTIN prefix"],
        ["Status", "Active"],
    ]
    return [
        Paragraph("Government of India — GST Registration Certificate", HEADING_STYLE),
        Paragraph(f"Issued to: <b>{bidder['name']}</b>", BODY_STYLE),
        Spacer(1, 0.3 * cm),
        Table([[r[0], r[1]] for r in rows],
               colWidths=[7 * cm, 9 * cm], style=_table_style()),
        Spacer(1, 0.5 * cm),
        Paragraph("This certificate is issued under the Goods and Services Tax Act, 2017.", BODY_STYLE),
    ]


def _pan_elements(bidder: dict, fields: dict) -> list:
    f = fields
    rows = [
        ["PAN", f["pan"]["value"]],
        ["Name", f["company_name_pan"]["value"]],
        ["Type", "Company"],
    ]
    return [
        Paragraph("Income Tax Department — Permanent Account Number Card", HEADING_STYLE),
        Spacer(1, 0.3 * cm),
        Table([[r[0], r[1]] for r in rows],
               colWidths=[7 * cm, 9 * cm], style=_table_style()),
        Spacer(1, 0.5 * cm),
        Paragraph("Issued under the Income Tax Act, 1961. This is a dummy document.", BODY_STYLE),
    ]


def _udyam_elements(bidder: dict, fields: dict) -> list:
    f = fields
    rows = [
        ["Udyam Number", f["udyam_number"]["value"]],
        ["Enterprise Name", bidder["name"]],
        ["Category", f["enterprise_category"]["value"]],
        ["Valid Until", f["udyam_valid_until"]["value"]],
        ["Status", "INVALID — See remarks" if not f.get("mse_proof_valid", {}).get("value", True)
                   else "Valid"],
    ]
    return [
        Paragraph("Ministry of MSME — Udyam Registration Certificate", HEADING_STYLE),
        Spacer(1, 0.3 * cm),
        Table([[r[0], r[1]] for r in rows],
               colWidths=[7 * cm, 9 * cm], style=_table_style()),
        Spacer(1, 0.5 * cm),
        Paragraph("Issued under the MSME Development Act, 2006.", BODY_STYLE),
    ]


def _turnover_elements(bidder: dict, fields: dict) -> list:
    f = fields
    rows = [
        ["Financial Year", "Turnover (INR)"],
        ["FY 2021-22", f"{f['turnover_fy1']['value']:,.0f}"],
        ["FY 2022-23", f"{f['turnover_fy2']['value']:,.0f}"],
        ["FY 2023-24", f"{f['turnover_fy3']['value']:,.0f}"],
        ["Average (3-year)", f"{f['avg_turnover_3y']['value']:,.0f}"],
    ]
    return [
        Paragraph("Chartered Accountant — Annual Turnover Certificate", HEADING_STYLE),
        Paragraph(f"Certified for: <b>{bidder['name']}</b>", BODY_STYLE),
        Spacer(1, 0.3 * cm),
        Table(rows, colWidths=[8 * cm, 8 * cm], style=_table_style()),
        Spacer(1, 0.5 * cm),
        Paragraph(
            "Certified by: CA Ramesh Sharma, FCA (ICAI Membership No. 123456). "
            "This is a dummy certificate for demonstration purposes.",
            BODY_STYLE,
        ),
    ]


def _experience_elements(bidder: dict, fields: dict) -> list:
    f = fields
    return [
        Paragraph("Experience / Incorporation Certificate", HEADING_STYLE),
        Paragraph(f"Entity: <b>{bidder['name']}</b>", BODY_STYLE),
        Spacer(1, 0.3 * cm),
        Table([
            ["Incorporation Date", f["incorporation_date"]["value"]],
            ["Years in Operation", f"{f['experience_years']['value']:.0f} years"],
            ["Business Activity", "Supply of IT Hardware and Peripherals"],
        ], colWidths=[7 * cm, 9 * cm], style=_table_style()),
        Spacer(1, 0.5 * cm),
        Paragraph("Certified under the Companies Act, 2013. Dummy document.", BODY_STYLE),
    ]


def _oem_elements(bidder: dict, fields: dict) -> list:
    f = fields
    return [
        Paragraph("OEM Authorization Letter", HEADING_STYLE),
        Paragraph(f"Authorized Dealer: <b>{bidder['name']}</b>", BODY_STYLE),
        Spacer(1, 0.3 * cm),
        Table([
            ["OEM Name", f["oem_name"]["value"]],
            ["Authorized For", "Supply of Laptop Computers — GeM Category IT Hardware"],
            ["Valid Until", f["oem_auth_valid_until"]["value"]],
            ["Authorization Status", "ACTIVE"],
        ], colWidths=[7 * cm, 9 * cm], style=_table_style()),
        Spacer(1, 0.5 * cm),
        Paragraph(
            "This letter certifies that the above dealer is authorized to supply "
            "LaptopTech Global Inc. products in India. Dummy document.",
            BODY_STYLE,
        ),
    ]


def _emd_elements(bidder: dict, emd: dict) -> list:
    return [
        Paragraph("Earnest Money Deposit / Exemption Document", HEADING_STYLE),
        Paragraph(f"Bidder: <b>{bidder['name']}</b>", BODY_STYLE),
        Spacer(1, 0.3 * cm),
        Table([
            ["EMD Amount (INR)", f"{emd['emd_amount']:,.0f}" if emd["emd_amount"] else "EXEMPT"],
            ["Type", emd["emd_type"]],
            ["Valid Until", emd["emd_valid_until"] or "N/A (Exempt)"],
            ["Status", "Present" if emd["emd_or_exemption_present"] else "MISSING"],
        ], colWidths=[7 * cm, 9 * cm], style=_table_style()),
        Spacer(1, 0.5 * cm),
        Paragraph("EMD/exemption document. Dummy for demonstration.", BODY_STYLE),
    ]


# ---------------------------------------------------------------------------
# Build all documents
# ---------------------------------------------------------------------------

ELEM_BUILDERS = {
    "gst_certificate":   (_gst_elements,        lambda b, f: f),
    "pan_card":          (_pan_elements,         lambda b, f: f),
    "udyam_certificate": (_udyam_elements,       lambda b, f: f),
    "turnover_certificate": (_turnover_elements, lambda b, f: f),
    "experience_letter": (_experience_elements,  lambda b, f: f),
    "oem_authorization": (_oem_elements,         lambda b, f: f),
}

DOC_TITLES = {
    "gst_certificate":      "GST Registration Certificate",
    "pan_card":             "PAN Card",
    "udyam_certificate":    "Udyam Registration Certificate",
    "turnover_certificate": "Annual Turnover Certificate",
    "experience_letter":    "Experience / Incorporation Certificate",
    "oem_authorization":    "OEM Authorization Letter",
    "emd_document":         "EMD / Exemption Document",
}


def make_bidder_docs(bidder: dict) -> dict:
    """Generate all PDF + sidecar files for one bidder. Returns metadata dict."""
    bdir = DUMMY_DIR / bidder["dir"]
    bdir.mkdir(parents=True, exist_ok=True)

    generated = {}

    for doc_key, doc_def in bidder["docs"].items():
        filename = doc_def["filename"]
        path = bdir / filename
        fields = doc_def["fields"]

        # Pick element builder
        if doc_key in ELEM_BUILDERS:
            builder_fn, _ = ELEM_BUILDERS[doc_key]
            elements = builder_fn(bidder, fields)
        else:
            elements = [Paragraph(f"Document: {doc_key}", BODY_STYLE)]

        title = DOC_TITLES.get(doc_key, filename.replace("_", " ").title())
        sha = _make_pdf(path, title, elements)

        # Build sidecar
        sidecar = {
            "bidder_label": bidder["label"],
            "bidder_name":  bidder["name"],
            "doc_type":     doc_def["doc_type"],
            "filename":     filename,
            "sha256":       sha,
            "fields":       fields,
        }
        _write_sidecar(path, sidecar)
        generated[doc_key] = str(path)
        print(f"    [+] {bidder['label']} - {filename}")

    # EMD document (always present, generated separately)
    emd = EMD_FIELDS[bidder["dir"]]
    emd_path = bdir / "emd_document.pdf"
    emd_elements = _emd_elements(bidder, emd)
    emd_sha = _make_pdf(emd_path, "EMD / Exemption Document", emd_elements)
    emd_sidecar = {
        "bidder_label": bidder["label"],
        "bidder_name":  bidder["name"],
        "doc_type":     "EMD_DOCUMENT",
        "filename":     "emd_document.pdf",
        "sha256":       emd_sha,
        "fields": {
            "emd_amount":               {"value": emd["emd_amount"],               "confidence": emd["confidence"], "page": 1, "snippet": f"EMD Amount: {emd['emd_amount']}", "bbox": [72, 300, 350, 320]},
            "emd_type":                 {"value": emd["emd_type"],                 "confidence": emd["confidence"], "page": 1, "snippet": f"Type: {emd['emd_type']}",         "bbox": [72, 320, 300, 340]},
            "emd_valid_until":          {"value": emd["emd_valid_until"],           "confidence": emd["confidence"], "page": 1, "snippet": f"Valid Until: {emd['emd_valid_until']}", "bbox": [72, 340, 300, 360]},
            "emd_or_exemption_present": {"value": emd["emd_or_exemption_present"], "confidence": emd["confidence"], "page": 1, "snippet": "EMD/Exemption Present", "bbox": [72, 360, 350, 380]},
        },
    }
    _write_sidecar(emd_path, emd_sidecar)
    generated["emd_document"] = str(emd_path)
    print(f"    [+] {bidder['label']} - emd_document.pdf")

    return generated


def write_manifest(tender_path: Path, bidder_results: list[dict]) -> None:
    """Write a manifest JSON listing all generated files."""
    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "tender": {
            "pdf": str(tender_path),
            "sidecar": str(tender_path.with_suffix(".json")),
        },
        "bidders": bidder_results,
    }
    manifest_path = DUMMY_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n  [+] Manifest      : {manifest_path}")


def main() -> None:
    print("\n====================================================")
    print("  BidCheck - Dummy Data Generator")
    print("  [DEMO ONLY] All data is synthetic dummy data")
    print("====================================================\n")

    print("Generating tender document...")
    tender_path = make_tender_pdf()

    bidder_results = []
    for bidder in BIDDERS:
        print(f"\nGenerating {bidder['label']} ({bidder['name']})...")
        docs = make_bidder_docs(bidder)
        bidder_results.append({
            "label": bidder["label"],
            "name":  bidder["name"],
            "gstin": bidder["gstin"],
            "pan":   bidder["pan"],
            "dir":   str(DUMMY_DIR / bidder["dir"]),
            "docs":  docs,
        })

    write_manifest(tender_path, bidder_results)

    print("\n====================================================")
    print(f"  Output directory : {DUMMY_DIR}")
    print("  Done! See data/PLANTED_ISSUES.md for planted issues.")
    print("====================================================\n")


if __name__ == "__main__":
    main()
