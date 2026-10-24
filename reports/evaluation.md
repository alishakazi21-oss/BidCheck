# BidCheck Pipeline Evaluation Report
**Generated At:** 2026-10-24 17:46:49 UTC
**Tender Reference:** `GeM/2024/B/1234567`

## 1. Executive Summary

- **Extraction Accuracy (Exact Match):** 100.0%
- **Extraction Accuracy (Fuzzy Match >=85%):** 100.0%
- **Planted Issue Detection Rate:** 6 / 6 (100%)
- **False Flag Count on Fully Compliant Bidders:** 0

---

## 2. Planted Issues Verification Matrix

| Test Case | Bidder | Expected Ground Truth & Planted Defect | Detection Status |
|---|---|---|---|
| `BIDDER_A_CLEAN` | **Bidder A** | Bidder A is fully compliant (Score 100%, Low Risk, 0 flags) | **✅ DETECTED** |
| `BIDDER_B_NAME_MISMATCH` | **Bidder B** | Bidder B GSTIN/PAN LLP name mismatch detected | **✅ DETECTED** |
| `BIDDER_C_TURNOVER_FAIL` | **Bidder C** | Bidder C turnover below min & MSE exemption denied (TURNOVER_MIN FAIL) | **✅ DETECTED** |
| `BIDDER_D_EXPIRED_UDYAM` | **Bidder D** | Bidder D expired Udyam cert detected (CERT_VALIDITY FAIL + EXPIRED flag) | **✅ DETECTED** |
| `BIDDER_D_MISSING_OEM` | **Bidder D** | Bidder D missing OEM authorization letter detected (OEM_AUTH_PRESENT FAIL) | **✅ DETECTED** |
| `BIDDER_E_VALID_MSE_EXEMPT` | **Bidder E** | Bidder E MSE with valid proof correctly EXEMPT from turnover requirement | **✅ DETECTED** |

---

## 3. Bidder Summary Outcomes

| Bidder | Legal Name | Quoted Price | Score | Risk Level | Active Flags | Final Recommendation |
|---|---|---|---|---|---|---|
| **Bidder A** | TechServe Solutions Pvt. Ltd. | ₹5,800,000 | 100.0% | `LOW` | 0 | **SHORTLIST** |
| **Bidder B** | DataPrime Enterprises | ₹6,200,000 | 66.7% | `HIGH` | 4 | **REJECT** |
| **Bidder C** | QuickByte Systems | ₹5,400,000 | 66.7% | `HIGH` | 3 | **REJECT** |
| **Bidder D** | GlobalEdge IT Private Limited | ₹7,100,000 | 50.0% | `HIGH` | 4 | **REJECT** |
| **Bidder E** | NanoTech Components Pvt. Ltd. | ₹5,950,000 | 100.0% | `LOW` | 0 | **SHORTLIST** |

---

## 4. Methodology & Compliance Principles

1. **Deterministic Rule Engine:** All numbers, dates, and eligibility verdicts are evaluated in plain Python code, strictly independent of LLM hallucinations.
2. **Evidence Linking:** Every evaluation finding references source document, page number, confidence, and text snippet.
3. **Decision Support:** Disqualification is NEVER automated. Procurement officers hold the legal authority to approve, reject, or override findings with a mandatory written justification.
4. **Tamper-Evident Audit:** Every pipeline action is chained via SHA-256 hashes from genesis block to final verdict.