# Planted Issues in Dummy Dataset

> **IMPORTANT**: This file documents ALL deliberately injected compliance
> problems in the synthetic demo dataset. Every dummy value used is listed
> here. No facts were invented silently.

---

## Tender: GeM/2024/B/1234567

| Field | Value |
|---|---|
| Tender ID | GeM/2024/B/1234567 |
| Title | Supply of Laptop Computers (GeM Category: IT Hardware) |
| Bid Deadline | 2024-12-31 |
| Minimum Average Annual Turnover (3 yr) | ₹ 32,00,000 (32 lakh) |
| Minimum Experience | 3 years |
| EMD Required | ₹ 50,000 (or valid EMD exemption cert) |
| OEM Authorization | Required (or bidder is OEM itself) |
| Exemptions Allowed | MSE (Micro/Small Enterprise) exempt from turnover; Startup (DPIIT) exempt from turnover |

---

## Bidder A — TechServe Solutions Pvt. Ltd. (FULLY COMPLIANT)

| Document | Key Fields | Value |
|---|---|---|
| GST Certificate | GSTIN | 27AABCT1234A1Z5 |
| GST Certificate | Company name (GST) | TECHSERVE SOLUTIONS PRIVATE LIMITED |
| PAN Card | PAN | AABCT1234A |
| PAN Card | Company name (PAN) | TECHSERVE SOLUTIONS PRIVATE LIMITED |
| Udyam Certificate | Udyam No. | UDYAM-MH-10-0012345 |
| Udyam Certificate | Category | Small Enterprise |
| Udyam Certificate | Valid until | 2026-03-31 |
| Turnover Cert | Avg 3-yr turnover | ₹ 45,00,000 |
| Experience Letter | Years in business | 7 years (since 2017) |
| OEM Auth Letter | OEM name | LaptopTech Global Inc. |
| OEM Auth Letter | Valid until | 2025-12-31 |

**Expected outcomes**: All rules → PASS or EXEMPT. Compliance score = 100%.

---

## Bidder B — DataPrime Enterprises (GSTIN/PAN NAME MISMATCH)

**Planted Issue**: The GSTIN `29BBBDE5678B1Z9` is registered to the company name
`DATAPRIME ENTERPRISES LLP` (with "LLP") but the PAN `BBBDE5678B` shows
`DATAPRIME ENTERPRISES` (without "LLP"). This mismatch is flagged by the
cross-verification module.

| Document | Key Fields | Value |
|---|---|---|
| GST Certificate | GSTIN | 29BBBDE5678B1Z9 |
| GST Certificate | Company name (GST) | DATAPRIME ENTERPRISES LLP |
| PAN Card | PAN | BBBDE5678B |
| PAN Card | Company name (PAN) | DATAPRIME ENTERPRISES |
| Udyam Certificate | Udyam No. | UDYAM-KA-05-0067890 |
| Udyam Certificate | Valid until | 2025-06-30 |
| Turnover Cert | Avg 3-yr turnover | ₹ 55,00,000 |
| Experience Letter | Years in business | 5 years |
| OEM Auth Letter | OEM name | LaptopTech Global Inc. |

**Planted Problem**: `GSTIN_PAN_CONSISTENT` → **FLAG: MISMATCH**
(GST name has "LLP" suffix, PAN name does not; these must match for a valid entity)

**Expected outcomes**: GSTIN_PAN_CONSISTENT → NEEDS_REVIEW + FLAG:MISMATCH.
All other rules → PASS. Score reduced due to flag.

---

## Bidder C — QuickByte Systems (TURNOVER BELOW MIN, INVALID MSE CLAIM)

**Planted Issue**: Bidder C claims MSE exemption from the turnover requirement
but does NOT provide a valid Udyam certificate (the uploaded file is a dummy
with `mse_proof_valid = false` in the sidecar). Turnover is ₹ 18,00,000, well
below the ₹ 32,00,000 threshold.

| Document | Key Fields | Value |
|---|---|---|
| GST Certificate | GSTIN | 06CCCQS9012C1Z3 |
| GST Certificate | Company name (GST) | QUICKBYTE SYSTEMS |
| PAN Card | PAN | CCCQS9012C |
| Udyam Certificate | Udyam No. | UDYAM-HR-02-0034567 |
| Udyam Certificate | Category | Micro Enterprise (claimed) |
| Udyam Certificate | `mse_proof_valid` | **false** (document present but invalid) |
| Turnover Cert | Avg 3-yr turnover | ₹ 18,00,000 |
| Experience Letter | Years in business | 4 years |
| OEM Auth Letter | OEM name | LaptopTech Global Inc. |

**Planted Problems**:
1. `TURNOVER_MIN` → **FAIL** (18L < 32L) because MSE exemption is DENIED
   (proof document present but `mse_proof_valid=false`).
2. Flag `EXEMPTION_WITHOUT_PROOF` is raised.

**Expected outcomes**: TURNOVER_MIN → FAIL (exemption denied). Score < 100%.
Risk level = HIGH (mandatory criterion FAIL).

---

## Bidder D — GlobalEdge IT (EXPIRED UDYAM + MISSING OEM AUTH)

**Planted Issues**:
1. Udyam certificate expired on 2023-09-30 (before bid date 2024-12-31).
2. OEM authorization letter is not uploaded at all.

| Document | Key Fields | Value |
|---|---|---|
| GST Certificate | GSTIN | 33DDDGE3456D1Z7 |
| GST Certificate | Company name (GST) | GLOBALEDGE IT PRIVATE LIMITED |
| PAN Card | PAN | DDDGE3456D |
| Udyam Certificate | Udyam No. | UDYAM-TN-07-0089012 |
| Udyam Certificate | Valid until | **2023-09-30** (EXPIRED) |
| Turnover Cert | Avg 3-yr turnover | ₹ 48,00,000 |
| Experience Letter | Years in business | 6 years |
| OEM Auth Letter | — | **NOT UPLOADED** |

**Planted Problems**:
1. `CERT_VALIDITY` → **FAIL** (Udyam cert expired before bid date).
2. `OEM_AUTH_PRESENT` → **FAIL** (document missing; no OEM exemption claimed).
3. Flags: `EXPIRED` (Udyam), `MISSING_DOCUMENT` (OEM auth).

**Expected outcomes**: Two mandatory rules FAIL. Risk level = HIGH.

---

## Bidder E — NanoTech Components (MSE WITH VALID PROOF — CORRECTLY EXEMPT)

> This is the positive control: an MSE bidder with a valid Udyam certificate
> whose turnover is below the minimum. The exemption MUST be granted.

| Document | Key Fields | Value |
|---|---|---|
| GST Certificate | GSTIN | 24EEETN7890E1Z1 |
| GST Certificate | Company name (GST) | NANOTECH COMPONENTS PRIVATE LIMITED |
| PAN Card | PAN | EEETN7890E |
| Udyam Certificate | Udyam No. | UDYAM-GJ-08-0056789 |
| Udyam Certificate | Category | Micro Enterprise |
| Udyam Certificate | `mse_proof_valid` | **true** |
| Udyam Certificate | Valid until | 2026-12-31 |
| Turnover Cert | Avg 3-yr turnover | ₹ 12,00,000 (below 32L) |
| Experience Letter | Years in business | 3 years |
| OEM Auth Letter | OEM name | LaptopTech Global Inc. |

**Expected outcomes**: TURNOVER_MIN → **EXEMPT** (valid MSE proof, non-expired Udyam).
All other rules → PASS. Compliance score = 100%.

---

## Summary of Planted Issues

| Bidder | Issue | Rule | Expected Outcome |
|---|---|---|---|
| A | None (fully compliant) | All rules | PASS / EXEMPT |
| B | GSTIN name has LLP, PAN name does not | GSTIN_PAN_CONSISTENT | NEEDS_REVIEW + MISMATCH flag |
| C | Turnover 18L < 32L; MSE claimed but proof invalid | TURNOVER_MIN | FAIL + EXEMPTION_WITHOUT_PROOF flag |
| D | Udyam expired 2023-09-30; OEM auth missing | CERT_VALIDITY, OEM_AUTH_PRESENT | FAIL (×2) + EXPIRED + MISSING_DOC flags |
| E | Turnover 12L < 32L; valid MSE proof | TURNOVER_MIN | EXEMPT (exemption correctly granted) |

---

## Numeric Thresholds (all in this file, nowhere else)

| Parameter | Value |
|---|---|
| Minimum avg. annual turnover (3 yr) | ₹ 32,00,000 |
| Minimum experience | 3 years |
| EMD amount | ₹ 50,000 |
| Confidence threshold | 0.70 |
| Fuzzy-match threshold | 85 (out of 100) |
| Udyam expiry considered: Bidder D | 2023-09-30 |
| Bid date | 2024-12-31 |
