"""
scripts/evaluate.py
===================
Runs end-to-end evaluation of the BidCheck extraction and deterministic rule engine
pipeline against the synthetic ground-truth dataset.

Evaluates:
  1. Per-field extraction accuracy (exact match and fuzzy similarity).
  2. Detection of every deliberately planted issue documented in data/PLANTED_ISSUES.md.
  3. False positive flag rate.
  4. Saves comprehensive results report to reports/evaluation.md.

Usage:
    python scripts/evaluate.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from rapidfuzz import fuzz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Safe stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.models.database import (
    Base,
    Bidder,
    FlagType,
    RuleOutcome,
    Tender,
    create_tables,
    get_engine,
)
from app.models.session import SessionLocal
from app.pipeline import setup_demo_environment


def evaluate_pipeline() -> Tuple[Dict[str, Any], str]:
    """
    Run pipeline and evaluate performance metrics.
    """
    engine = get_engine()
    create_tables(engine)
    session = SessionLocal()

    # Reset demo environment to fresh baseline
    tender = setup_demo_environment(session, force_reset=True)

    bidders = session.query(Bidder).filter(Bidder.tender_id == tender.id).all()

    # -----------------------------------------------------------------------
    # 1. Extraction Accuracy Assessment
    # -----------------------------------------------------------------------
    total_fields = 0
    exact_matches = 0
    fuzzy_matches = 0

    extraction_details = []

    for bidder in bidders:
        for doc in bidder.documents:
            sidecar_file = Path(doc.file_path).with_suffix(".json")
            if not sidecar_file.is_file():
                continue
            with open(sidecar_file, "r", encoding="utf-8") as f:
                ground_truth = json.load(f)

            gt_fields = ground_truth.get("fields", {})
            for ef in doc.extracted_fields:
                if ef.field_name in gt_fields:
                    total_fields += 1
                    gt_val = gt_fields[ef.field_name].get("value")
                    ext_val = ef.raw_value

                    # Check exact match
                    is_exact = str(gt_val).strip() == str(ext_val).strip()
                    if is_exact:
                        exact_matches += 1

                    # Check fuzzy match
                    sim = fuzz.ratio(str(gt_val).strip().lower(), str(ext_val).strip().lower())
                    if sim >= 85:
                        fuzzy_matches += 1

                    extraction_details.append(
                        {
                            "bidder": bidder.label,
                            "document": doc.filename,
                            "field": ef.field_name,
                            "ground_truth": gt_val,
                            "extracted": ext_val,
                            "exact": is_exact,
                            "fuzzy_score": sim,
                        }
                    )

    exact_acc = (exact_matches / total_fields * 100) if total_fields else 100.0
    fuzzy_acc = (fuzzy_matches / total_fields * 100) if total_fields else 100.0

    # -----------------------------------------------------------------------
    # 2. Planted Issue Detection Assessment
    # -----------------------------------------------------------------------
    planted_tests = [
        {
            "id": "BIDDER_A_CLEAN",
            "bidder": "Bidder A",
            "desc": "Bidder A is fully compliant (Score 100%, Low Risk, 0 flags)",
            "check": lambda b: b.compliance_score == 100.0 and b.risk_level == "LOW" and len(b.flags) == 0,
        },
        {
            "id": "BIDDER_B_NAME_MISMATCH",
            "bidder": "Bidder B",
            "desc": "Bidder B GSTIN/PAN LLP name mismatch detected",
            "check": lambda b: any(f.flag_type == FlagType.MISMATCH.value for f in b.flags),
        },
        {
            "id": "BIDDER_C_TURNOVER_FAIL",
            "bidder": "Bidder C",
            "desc": "Bidder C turnover below min & MSE exemption denied (TURNOVER_MIN FAIL)",
            "check": lambda b: any(r.rule_id == "TURNOVER_MIN" and r.outcome == RuleOutcome.FAIL.value for r in b.rule_results)
            and any(f.flag_type == FlagType.EXEMPTION_WITHOUT_PROOF.value for f in b.flags),
        },
        {
            "id": "BIDDER_D_EXPIRED_UDYAM",
            "bidder": "Bidder D",
            "desc": "Bidder D expired Udyam cert detected (CERT_VALIDITY FAIL + EXPIRED flag)",
            "check": lambda b: any(r.rule_id == "CERT_VALIDITY" and r.outcome == RuleOutcome.FAIL.value for r in b.rule_results)
            and any(f.flag_type == FlagType.EXPIRED.value for f in b.flags),
        },
        {
            "id": "BIDDER_D_MISSING_OEM",
            "bidder": "Bidder D",
            "desc": "Bidder D missing OEM authorization letter detected (OEM_AUTH_PRESENT FAIL)",
            "check": lambda b: any(r.rule_id == "OEM_AUTH_PRESENT" and r.outcome == RuleOutcome.FAIL.value for r in b.rule_results),
        },
        {
            "id": "BIDDER_E_VALID_MSE_EXEMPT",
            "bidder": "Bidder E",
            "desc": "Bidder E MSE with valid proof correctly EXEMPT from turnover requirement",
            "check": lambda b: any(r.rule_id == "TURNOVER_MIN" and r.outcome == RuleOutcome.EXEMPT.value for r in b.rule_results)
            and b.compliance_score == 100.0,
        },
    ]

    bidder_map = {b.label: b for b in bidders}
    planted_results = []
    all_planted_detected = True

    for pt in planted_tests:
        target_b = bidder_map.get(pt["bidder"])
        if target_b and pt["check"](target_b):
            passed = True
        else:
            passed = False
            all_planted_detected = False
        planted_results.append(
            {
                "id": pt["id"],
                "bidder": pt["bidder"],
                "description": pt["desc"],
                "detected": passed,
            }
        )

    # -----------------------------------------------------------------------
    # 3. False Flags Check (Compliant bidders should have 0 flags)
    # -----------------------------------------------------------------------
    false_flags = len(bidder_map.get("Bidder A", type("B", (), {"flags": []})).flags)

    # -----------------------------------------------------------------------
    # 4. Generate Markdown Report
    # -----------------------------------------------------------------------
    report_lines = [
        "# BidCheck Pipeline Evaluation Report",
        f"**Generated At:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Tender Reference:** `{tender.gem_id}`",
        "",
        "## 1. Executive Summary",
        "",
        f"- **Extraction Accuracy (Exact Match):** {exact_acc:.1f}%",
        f"- **Extraction Accuracy (Fuzzy Match >=85%):** {fuzzy_acc:.1f}%",
        f"- **Planted Issue Detection Rate:** {sum(1 for p in planted_results if p['detected'])} / {len(planted_results)} ({sum(1 for p in planted_results if p['detected']) / len(planted_results):.0%})",
        f"- **False Flag Count on Fully Compliant Bidders:** {false_flags}",
        "",
        "---",
        "",
        "## 2. Planted Issues Verification Matrix",
        "",
        "| Test Case | Bidder | Expected Ground Truth & Planted Defect | Detection Status |",
        "|---|---|---|---|",
    ]

    for p in planted_results:
        status_str = "✅ DETECTED" if p["detected"] else "❌ MISSED"
        report_lines.append(f"| `{p['id']}` | **{p['bidder']}** | {p['description']} | **{status_str}** |")

    report_lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Bidder Summary Outcomes",
            "",
            "| Bidder | Legal Name | Quoted Price | Score | Risk Level | Active Flags | Final Recommendation |",
            "|---|---|---|---|---|---|---|",
        ]
    )

    for b in bidders:
        rec = "SHORTLIST" if b.risk_level == "LOW" else ("REJECT" if b.risk_level == "HIGH" else "REFER")
        report_lines.append(
            f"| **{b.label}** | {b.name} | ₹{b.quoted_price:,.0f} | {b.compliance_score:.1f}% | `{b.risk_level}` | {len(b.flags)} | **{rec}** |"
        )

    report_lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Methodology & Compliance Principles",
            "",
            "1. **Deterministic Rule Engine:** All numbers, dates, and eligibility verdicts are evaluated in plain Python code, strictly independent of LLM hallucinations.",
            "2. **Evidence Linking:** Every evaluation finding references source document, page number, confidence, and text snippet.",
            "3. **Decision Support:** Disqualification is NEVER automated. Procurement officers hold the legal authority to approve, reject, or override findings with a mandatory written justification.",
            "4. **Tamper-Evident Audit:** Every pipeline action is chained via SHA-256 hashes from genesis block to final verdict.",
        ]
    )

    report_content = "\n".join(report_lines)

    # Save to reports/evaluation.md
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "evaluation.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    session.close()

    metrics = {
        "exact_accuracy": exact_acc,
        "fuzzy_accuracy": fuzzy_acc,
        "all_planted_detected": all_planted_detected,
        "false_flags": false_flags,
        "report_path": str(report_file),
    }

    return metrics, report_content


def main():
    print("=================================================================")
    print("  BidCheck Compliance Engine - Automated Evaluation")
    print("=================================================================")

    metrics, report_md = evaluate_pipeline()

    print(f"\n[+] Extraction Accuracy (Exact): {metrics['exact_accuracy']:.1f}%")
    print(f"[+] Extraction Accuracy (Fuzzy): {metrics['fuzzy_accuracy']:.1f}%")
    print(f"[+] All Planted Issues Detected: {'YES (100%)' if metrics['all_planted_detected'] else 'NO'}")
    print(f"[+] False Flag Count: {metrics['false_flags']}")
    print(f"[+] Report saved to: {metrics['report_path']}")
    print("\n=================================================================")
    print("  Evaluation Completed Successfully.")
    print("=================================================================")


if __name__ == "__main__":
    main()
