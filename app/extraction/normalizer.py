"""
BidCheck - Post-extraction Normalization.

Normalizes extracted text into strict, deterministic formats:
- Dates to ISO format (YYYY-MM-DD) and Python date objects.
- Indian currency strings (lakh, crore, formatted commas) to float amounts in INR.
- GSTIN and PAN syntax validation via regex.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple


# Regex patterns
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def normalize_date(val: Any) -> Optional[date]:
    """
    Parse a date string or object into a datetime.date object.
    Supports DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, and month name strings.
    """
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()

    val_str = str(val).strip()
    if not val_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue

    # Attempt regex extraction if embedded in longer sentence
    match = re.search(r"(\d{4}-\d{2}-\d{2})|(\d{1,2}[/-]\d{1,2}[/-]\d{4})", val_str)
    if match:
        matched_str = match.group(0).replace("/", "-")
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(matched_str, fmt).date()
            except ValueError:
                continue

    return None


def normalize_currency(val: Any) -> Optional[float]:
    """
    Parse Indian currency amounts into numeric float (INR).
    Handles '45 Lakh', '1.5 Crore', '₹45,00,000', 'Rs. 50,000', etc.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s:
        return None

    # Check for Crore / Cr
    cr_match = re.search(r"([\d,.]+)\s*(?:crore|cr)\b", s, re.IGNORECASE)
    if cr_match:
        num_str = cr_match.group(1).replace(",", "")
        try:
            return float(num_str) * 10000000.0
        except ValueError:
            pass

    # Check for Lakh / Lac / Lacs / Lakhs
    lakh_match = re.search(r"([\d,.]+)\s*(?:lakh|lakhs|lac|lacs)\b", s, re.IGNORECASE)
    if lakh_match:
        num_str = lakh_match.group(1).replace(",", "")
        try:
            return float(num_str) * 100000.0
        except ValueError:
            pass

    # Strip currency prefixes (Rs., Rs, INR, ₹)
    s_clean = re.sub(r"^(?:₹|rs\.?|inr)\s*", "", s, flags=re.IGNORECASE).strip()
    s_clean = s_clean.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", s_clean)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            pass

    return None


def validate_pan(pan: str) -> Tuple[bool, Optional[str]]:
    """
    Validate 10-character Indian Permanent Account Number format.
    Format: 5 uppercase letters + 4 digits + 1 uppercase letter.
    """
    if not pan:
        return False, "PAN is missing"
    pan_clean = pan.strip().upper()
    if not PAN_REGEX.match(pan_clean):
        return False, f"Invalid PAN format: '{pan}' does not match 5 letters, 4 numbers, 1 letter."
    return True, None


def validate_gstin(gstin: str) -> Tuple[bool, Optional[str]]:
    """
    Validate 15-character Indian Goods and Services Tax Identification Number.
    Format: 2 state digits + 10 PAN characters + 1 entity number + 'Z' + 1 checksum.
    """
    if not gstin:
        return False, "GSTIN is missing"
    gstin_clean = gstin.strip().upper()
    if not GSTIN_REGEX.match(gstin_clean):
        return False, f"Invalid GSTIN format: '{gstin}' does not match standard 15-character GSTIN regex."
    return True, None


def check_gstin_pan_match(gstin: str, pan: str) -> Tuple[bool, Optional[str]]:
    """
    Verify that characters 3 to 12 of the GSTIN match the PAN exactly.
    """
    is_pan_ok, pan_err = validate_pan(pan)
    if not is_pan_ok:
        return False, pan_err

    is_gst_ok, gst_err = validate_gstin(gstin)
    if not is_gst_ok:
        return False, gst_err

    gstin_clean = gstin.strip().upper()
    pan_clean = pan.strip().upper()

    embedded_pan = gstin_clean[2:12]
    if embedded_pan != pan_clean:
        return (
            False,
            f"PAN mismatch: PAN '{pan_clean}' does not match embedded PAN '{embedded_pan}' in GSTIN '{gstin_clean}'.",
        )

    return True, None
