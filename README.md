# ⚖️ BidCheck: AI-Assisted GeM Bid Compliance Verification

> **Decision Support System for Procurement Officers Evaluating Government e-Marketplace (GeM) Bids in India.**

[![Tests](https://img.shields.io/badge/pytest-58%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.14-blue.svg)]()
[![License](https://img.shields.io/badge/mode-offline--first-success.svg)]()
[![Principle](https://img.shields.io/badge/verdict-deterministic%20engine-orange.svg)]()

---

## 🏛️ Core Principles

1. **AI Reads Documents, A Deterministic Rule Engine Decides, The Officer Approves.**
   - Large Language Models or OCR extract text and coordinates.
   - Plain Python deterministic rules decide eligibility without hallucination risk.
   - The system is **DECISION SUPPORT ONLY** and **NEVER** automatically disqualifies a bidder.
2. **Offline-First & Zero API Dependencies**:
   - Runs out-of-the-box in 100% offline mode via `FakeExtractor` reading sidecar JSONs.
   - Switchable to OpenAI via `EXTRACTOR=llm` when configured with `OPENAI_API_KEY`.
3. **Mock Registries Only**:
   - All external government services (GSTN, MCA/Income Tax, Udyam MSME) are **MOCK services** utilizing synthetic dummy records.
4. **Tamper-Evident Auditability**:
   - Every action (upload, extraction, rule evaluation, flag, officer override, verdict) is appended to a **SHA-256 hash-chained log**. A single bit altered in SQLite breaks verification.

---

## 🚀 Quickstart Guide

### 1. Requirements & Setup
```bash
# Clone and enter workspace
git clone <repo-url>
cd BidCheck

# Install dependencies (Python 3.11+ recommended)
pip install -r requirements.txt

# Copy environment configuration
cp .env.example .env
```

### 2. Run Locally (One Command)
```bash
# Start Streamlit Officer Dashboard
make run
# Or directly:
streamlit run ui/app.py
```
Open your browser to: **http://localhost:8501**

### 3. Run with Docker Compose
```bash
docker compose up --build
```
Access the dashboard at **http://localhost:8501** and FastAPI at **http://localhost:8000/docs**.

### 4. Run Test Suite
```bash
make test
# Or:
python -m pytest tests/ -v
```
*Result: 58 unit and integration tests passing (100%).*

---

## ⏱️ 5-Minute Hackathon Demo Script

Follow this step-by-step walkthrough to present BidCheck to judges in 5 minutes:

### **Minute 1: The Core Problem & Guiding Principle**
1. Open the dashboard at `http://localhost:8501`.
2. Highlight the persistent disclaimer banner:
   > *"AI assists with reading; a deterministic rule engine evaluates; the Procurement Officer retains final legal authority."*
3. Navigate to **Screen 1: 📋 Tender Setup & Criteria**:
   - Show how the tender checklist was parsed.
   - Point out that criteria start in an **UNCONFIRMED** status: numbers are never blindly trusted without human review.

### **Minute 2: Real-time Eligibility Scorecard**
1. Switch to **Screen 2: 📊 Bidder Compliance Overview**.
2. Click **"⚡ Run Full Evaluation"**:
   - Show how all 5 synthetic bidders are scored in milliseconds.
   - Point out the metrics:
     - **Bidder A**: 100% Score, Low Risk (Fully compliant control).
     - **Bidder B**: 66.7% Score, High Risk (Name/LLP discrepancy).
     - **Bidder C**: 66.7% Score, High Risk (Turnover below min, invalid MSE proof).
     - **Bidder D**: 50.0% Score, High Risk (Expired Udyam & missing OEM auth).
     - **Bidder E**: 100% Score, Low Risk (Turnover 12L < 32L, but **correctly EXEMPT** due to valid Udyam).

### **Minute 3: In-Depth Evidence & Discrepancy Viewer**
1. Navigate to **Screen 3: 🔍 Bidder Evidence & Findings**:
2. Select **Bidder B**:
   - Show **Discrepancies & Flags**: Tab shows GSTIN entity name has "LLP" suffix, but PAN card shows proprietorship/firm without "LLP".
   - Show **Mock Registry Tab**: Shows how the system cross-checks synthetic GSTN and Income Tax registries.
3. Select **Bidder D**:
   - Show **Document & Evidence Viewer**: Page rendered with yellow bounding box highlight around certificate validity.
   - Show `CERT_VALIDITY` failure because Udyam expired on 2023-09-30 (before bid deadline 2024-12-31).
   - Show `OEM_AUTH_PRESENT` failure because document was not submitted.

### **Minute 4: Officer Override & Legal Decision Recording**
1. On **Bidder D**, expand `OEM_AUTH_PRESENT`.
2. Demonstrate **Officer Override**:
   - Explain: *"Suppose the vendor sent a physical hardcopy OEM authorization to the department."*
   - Select Outcome: `PASS`.
   - Type mandatory justification: *"Hardcopy verified in office files by Dy. Director on 24-Oct-2026."*
   - Click **Apply Override**.
   - Show that the override is permanently saved with the officer's name and logged to the audit chain.
3. Switch to **Screen 5: ✍️ Officer Decision & Export**:
   - Select Final Recommendation: `SHORTLIST` or `REJECT`.
   - Click **📥 Download Evaluation Report (HTML)** to view the printable audit document.

### **Minute 5: Cryptographic Tamper-Evident Audit Trail**
1. Navigate to **Screen 6: 🔐 Audit Trail & Verification**:
2. Click **"🛡️ Verify Audit Log Integrity"**:
   - Displays green badge: *"All N chained records are authentic and untampered."*
3. Click **"🧪 Simulate Audit Log Tampering (Demo Test)"**:
   - The test artificially modifies a past record in SQLite.
4. Click **"🛡️ Verify Audit Log Integrity"** again:
   - Immediately alerts red: *"❌ TAMPERING DETECTED! Tampered row payload detected at row ID..."*
   - Demonstrates complete resistance to unauthorized database manipulation.

---

## 📂 Repository Structure

```
BidCheck/
├── app/
│   ├── api/                 # FastAPI REST server & endpoints
│   ├── audit/               # SHA-256 hash-chained tamper-evident audit log
│   ├── extraction/          # Extractor interface, FakeExtractor, LLMExtractor, Normalizer
│   ├── models/              # SQLAlchemy database models & session management
│   ├── rules/               # Deterministic rule engine, scoring, and perturbation logic
│   │   └── definitions/     # JSON rule definitions (TURNOVER_MIN, CERT_VALIDITY, etc.)
│   ├── verification/        # Cross-document fuzzy matching & Mock Registry service
│   ├── config.py            # Pydantic BaseSettings configuration
│   └── pipeline.py          # End-to-end evaluation orchestrator
├── data/
│   ├── dummy/               # Synthetic tenders and bidders A-E (PDFs + sidecar JSONs)
│   ├── kaggle_sample/       # Proxy procurement benchmark CSVs
│   └── PLANTED_ISSUES.md    # Complete catalog of all planted demo defects
├── ui/
│   └── app.py               # Streamlit multi-screen interactive officer dashboard
├── scripts/
│   ├── make_dummy_data.py   # Generates PDFs and sidecars from scratch
│   ├── load_kaggle_data.py  # Ingests benchmark proxies into SQLite
│   └── evaluate.py          # Automated pipeline benchmark and accuracy evaluator
├── tests/                   # 58 pytest test suites across all 9 phases
├── Dockerfile               # Container build definition
├── docker-compose.yml       # Multi-service container orchestration
├── Makefile                 # Developer CLI shortcuts
├── requirements.txt         # Pinned Python package dependencies
└── README.md                # Project documentation
```

---

## 🧪 Planted Issues Catalog

| Bidder | Synthetic Entity | Planted Problem | Expected Outcome |
|---|---|---|---|
| **Bidder A** | TechServe Solutions Pvt. Ltd. | Fully compliant control entity | Score 100%, Low Risk, 0 Flags |
| **Bidder B** | DataPrime Enterprises | GSTIN has "LLP" suffix; PAN card does not | Flag: `MISMATCH` on legal entity form |
| **Bidder C** | QuickByte Systems | Turnover 18L < 32L; MSE claimed but proof invalid | `TURNOVER_MIN`: FAIL; Flag: `EXEMPTION_WITHOUT_PROOF` |
| **Bidder D** | GlobalEdge IT Pvt. Ltd. | Expired Udyam (2023) + Missing OEM Auth | `CERT_VALIDITY`: FAIL, `OEM_AUTH_PRESENT`: FAIL |
| **Bidder E** | NanoTech Components Pvt. Ltd. | Turnover 12L < 32L with valid non-expired Udyam | `TURNOVER_MIN`: **EXEMPT** (Score 100%) |

---

## ⚠️ Known Limitations & Future Scope

### Known Limitations (Prototype Scope)
- **Mock Government Registries**: Live GSTN, MCA, and Udyam portals are simulated via in-memory mock responses.
- **Offline OCR**: In offline mode, the system defaults to sidecar JSONs or digital text extraction; scanned OCR requires local Tesseract or PaddleOCR binary.
- **Single-Node SQLite**: SQLite is used for lightweight demo execution (fully Postgres-compatible via `DATABASE_URL`).

### Future Scope
- **Production GeM Integration**: Direct API integration with GeM portal for automated bid package download.
- **Multi-Officer Committee Workflow**: Quorum voting and dual-key signoff for high-value tenders.
- **LayoutLMv3 Fine-Tuning**: Indian bilingual (Hindi/English) invoice and stamp-paper layout parsing.
