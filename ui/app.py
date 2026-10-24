"""
BidCheck - AI-Assisted GeM Bid Compliance Verification Dashboard.
===================================================================

Decision Support Tool for Procurement Officers evaluating Government e-Marketplace (GeM) bids.

Core Principles:
1. AI reads documents; a deterministic rule engine decides; the Officer approves.
2. System NEVER automatically disqualifies any bidder.
3. All live government APIs (GSTN, MCA, Udyam) are MOCK services.
4. Offline-first: works without external API dependencies.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from sqlalchemy.orm import Session

from app.audit.chain import record_audit_action, verify_audit_chain
from app.extraction.pdf_analyzer import render_pdf_page_with_highlight
from app.extraction.tender_parser import confirm_tender_criteria, parse_tender_document, save_parsed_tender_to_db
from app.models.database import (
    ActionType,
    Benchmark,
    Bidder,
    Criterion,
    Decision,
    Document,
    ExtractedField,
    Flag,
    RiskLevel,
    RuleOutcome,
    RuleResult,
    Tender,
    get_engine,
    create_tables,
)
from app.models.session import SessionLocal
from app.pipeline import setup_demo_environment
from app.rules.assessment import evaluate_bidder
from app.verification.mock_registry import MockRegistryService

# Page configuration
st.set_page_config(
    page_title="BidCheck | GeM Bid Compliance Verification",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern, authoritative procurement styling
st.markdown(
    """
    <style>
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .disclaimer-banner {
        background: #fef3c7;
        color: #92400e;
        border: 1px solid #f59e0b;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.88rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .stat-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .badge-pass { background-color: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; }
    .badge-fail { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; }
    .badge-exempt { background-color: #e0e7ff; color: #3730a3; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; }
    .badge-review { background-color: #fef9c3; color: #854d0e; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; }
    .badge-low { background-color: #d1fae5; color: #065f46; font-weight: bold; padding: 4px 8px; border-radius: 6px; }
    .badge-med { background-color: #fef3c7; color: #92400e; font-weight: bold; padding: 4px 8px; border-radius: 6px; }
    .badge-high { background-color: #ffe4e6; color: #9f1239; font-weight: bold; padding: 4px 8px; border-radius: 6px; }
    .mock-tag { background: #ede9fe; color: #5b21b6; border: 1px solid #c4b5fd; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_db():
    return SessionLocal()


# Initialize database if needed
@st.cache_resource
def init_app():
    engine = get_engine()
    create_tables(engine)
    session = SessionLocal()
    setup_demo_environment(session, force_reset=False)
    session.close()


init_app()

# Sidebar controls
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/5/55/Emblem_of_India.svg", width=64)
    st.title("BidCheck")
    st.caption("AI-Assisted GeM Bid Compliance")

    role = st.selectbox(
        "Current Operating Role",
        ["Procurement Officer", "Independent Auditor"],
        index=0,
        help="Switch role view. Procurement Officer has decision/override rights; Auditor has read-only audit log verification focus.",
    )

    st.divider()

    st.markdown("### Quick Navigation")
    selected_page = st.radio(
        "Go to Screen:",
        [
            "1. 📋 Tender Setup & Criteria",
            "2. 📊 Bidder Compliance Overview",
            "3. 🔍 Bidder Evidence & Findings",
            "4. ⚖️ Cross-Bidder Comparison",
            "5. ✍️ Officer Decision & Export",
            "6. 🔐 Audit Trail & Verification",
        ],
        index=1,
    )

    st.divider()
    st.markdown("### Demo Database Controls")
    if st.button("🔄 Reset Demo Data to Baseline", use_container_width=True):
        db = get_db()
        setup_demo_environment(db, force_reset=True)
        db.close()
        st.success("Reset completed! All 5 dummy bidders and planted problems restored.")
        st.rerun()

    st.markdown(
        """
        <div style='font-size:0.75rem; color:#64748b; margin-top:1rem;'>
        <b>Offline Mode Active</b><br>
        Extractor backend: <code>fake</code> (offline sidecars).<br>
        Rule engine: <code>deterministic</code> (v2.0).
        </div>
        """,
        unsafe_allow_html=True,
    )

# Top Banner
st.markdown(
    """
    <div class="main-header">
        <h1 style='margin:0; font-size:1.8rem; font-weight:700;'>BidCheck — GeM Bid Compliance Verification</h1>
        <p style='margin:0.25rem 0 0 0; opacity:0.85; font-size:0.95rem;'>
            Automated document ingestion, deterministic eligibility rules, and tamper-evident audit trail for Indian public procurement.
        </p>
    </div>
    <div class="disclaimer-banner">
        <span>🛡️</span>
        <div>
            <b>DECISION SUPPORT ONLY:</b> This system never disqualifies a bidder automatically. All evaluation verdicts are recommendations for the Procurement Officer.
            All government registries (GSTN, MCA, Udyam) are <b>MOCK services</b> utilizing synthetic data for demonstration.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

db: Session = get_db()

# ---------------------------------------------------------------------------
# SCREEN 1: TENDER SETUP & CRITERIA CONFIRMATION
# ---------------------------------------------------------------------------
if selected_page.startswith("1."):
    st.header("📋 Tender Setup & Criteria Review")
    st.markdown(
        "Extract criteria from tender document and review the checklist before running evaluations. "
        "**Strict Rule:** Extracted criteria values are never trusted automatically without the officer's review and confirmation."
    )

    tender = db.query(Tender).first()

    if not tender:
        st.warning("No tender found in database. Click 'Reset Demo Data' in sidebar.")
    else:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"**Tender Reference:** `{tender.gem_id}`")
            st.markdown(f"**Title:** {tender.title}")
            st.markdown(f"**Category:** {tender.category}")
        with col2:
            st.markdown(f"**Bid Deadline:** `{tender.bid_submission_deadline}`")
            st.markdown(f"**PDF Path:** `{tender.tender_pdf_path}`")
        with col3:
            if tender.criteria_confirmed:
                st.success("✅ **CRITERIA CONFIRMED**\n\nOfficer confirmed checklist.")
            else:
                st.warning("⚠️ **UNCONFIRMED**\n\nOfficer review pending.")

        st.subheader("Criteria Checklist")
        st.markdown("Procurement officers can edit thresholds or exemptions prior to evaluation.")

        criteria_list = db.query(Criterion).filter(Criterion.tender_id == tender.id).all()
        edit_data = {}

        for crit in criteria_list:
            with st.expander(f"{'🔒' if crit.mandatory else 'ℹ️'} {crit.label} (`{crit.rule_id}`)", expanded=True):
                c1, c2, c3 = st.columns([2, 1, 2])
                with c1:
                    new_val = st.text_input(
                        "Threshold Value",
                        value=crit.threshold_value or "",
                        key=f"val_{crit.id}",
                        disabled=(role == "Independent Auditor"),
                    )
                with c2:
                    is_mand = st.checkbox(
                        "Mandatory Criterion",
                        value=crit.mandatory,
                        key=f"mand_{crit.id}",
                        disabled=(role == "Independent Auditor"),
                    )
                with c3:
                    ex_cats_str = ", ".join(crit.exemption_categories or [])
                    new_ex = st.text_input(
                        "Allowed Exemptions (comma-separated)",
                        value=ex_cats_str,
                        key=f"ex_{crit.id}",
                        disabled=(role == "Independent Auditor"),
                    )

                edit_data[crit.rule_id] = {
                    "threshold_value": new_val if new_val else None,
                    "mandatory": is_mand,
                    "exemption_categories": [x.strip() for x in new_ex.split(",") if x.strip()],
                }

        if role == "Procurement Officer":
            col_b1, col_b2 = st.columns([1, 4])
            with col_b1:
                if st.button("💾 Confirm Criteria Checklist", type="primary", use_container_width=True):
                    confirm_tender_criteria(db, tender.id, edit_data)
                    record_audit_action(
                        db,
                        action_type=ActionType.OVERRIDE,
                        actor="Procurement Officer",
                        payload={"action": "confirm_criteria", "tender_id": tender.id},
                        tender_id=tender.id,
                    )
                    st.success("Criteria updated and confirmed! You can now evaluate bidders.")
                    st.rerun()

# ---------------------------------------------------------------------------
# SCREEN 2: BIDDER COMPLIANCE OVERVIEW
# ---------------------------------------------------------------------------
elif selected_page.startswith("2."):
    st.header("📊 Bidder Compliance Overview")
    st.markdown("Real-time eligibility scorecard across all submitted bids.")

    tender = db.query(Tender).first()
    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all() if tender else []

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("⚡ Run Full Evaluation", type="primary", use_container_width=True):
            with st.spinner("Evaluating compliance rules and cross-document verification..."):
                for b in bidders:
                    evaluate_bidder(db, b.id, actor=f"{role}")
            st.success("Evaluations completed!")
            st.rerun()

    # Metrics summary row
    m1, m2, m3, m4, m5 = st.columns(5)
    total_b = len(bidders)
    clean_b = sum(1 for b in bidders if b.risk_level == RiskLevel.LOW.value)
    med_b = sum(1 for b in bidders if b.risk_level == RiskLevel.MEDIUM.value)
    high_b = sum(1 for b in bidders if b.risk_level == RiskLevel.HIGH.value)
    total_flags = sum(len(b.flags) for b in bidders)

    m1.metric("Total Bidders", total_b)
    m2.metric("Fully Compliant (Low Risk)", clean_b)
    m3.metric("Medium Risk (Review)", med_b)
    m4.metric("High Risk (Failures)", high_b)
    m5.metric("Active Flags", total_flags)

    st.markdown("### Bidder Scorecard")

    # Table displaying all bidders
    table_rows = []
    for b in bidders:
        pass_count = sum(1 for r in b.rule_results if r.outcome == RuleOutcome.PASS.value)
        exempt_count = sum(1 for r in b.rule_results if r.outcome == RuleOutcome.EXEMPT.value)
        fail_count = sum(1 for r in b.rule_results if r.outcome == RuleOutcome.FAIL.value)
        review_count = sum(1 for r in b.rule_results if r.outcome == RuleOutcome.NEEDS_REVIEW.value)

        # Risk formatting
        risk = b.risk_level or "PENDING"
        if risk == RiskLevel.LOW.value:
            risk_badge = '<span class="badge-low">🟢 LOW</span>'
        elif risk == RiskLevel.MEDIUM.value:
            risk_badge = '<span class="badge-med">🟡 MEDIUM</span>'
        else:
            risk_badge = '<span class="badge-high">🔴 HIGH</span>'

        score = f"{b.compliance_score:.0f}%" if b.compliance_score is not None else "N/A"
        price = f"₹{b.quoted_price:,.0f}" if b.quoted_price else "—"

        table_rows.append(
            {
                "Label": b.label,
                "Company Name": b.name,
                "Quoted Price": price,
                "Compliance Score": score,
                "Risk Level": risk_badge,
                "PASS": pass_count,
                "EXEMPT": exempt_count,
                "FAIL": fail_count,
                "NEEDS_REVIEW": review_count,
                "Flags": len(b.flags),
            }
        )

    # Render as formatted HTML table for rich badge aesthetics
    html_table = """
    <table style="width:100%; border-collapse:collapse; margin-top:1rem; font-size:0.9rem;">
        <thead>
            <tr style="background:#f1f5f9; text-align:left; border-bottom:2px solid #cbd5e1;">
                <th style="padding:10px;">Bidder</th>
                <th style="padding:10px;">Company Legal Name</th>
                <th style="padding:10px;">Quoted Price</th>
                <th style="padding:10px;">Compliance Score</th>
                <th style="padding:10px;">Risk Level</th>
                <th style="padding:10px;">Pass</th>
                <th style="padding:10px;">Exempt</th>
                <th style="padding:10px;">Fail</th>
                <th style="padding:10px;">Review</th>
                <th style="padding:10px;">Flags</th>
            </tr>
        </thead>
        <tbody>
    """
    for row in table_rows:
        html_table += f"""
        <tr style="border-bottom:1px solid #e2e8f0;">
            <td style="padding:10px; font-weight:bold;">{row['Label']}</td>
            <td style="padding:10px;">{row['Company Name']}</td>
            <td style="padding:10px;">{row['Quoted Price']}</td>
            <td style="padding:10px; font-weight:bold;">{row['Compliance Score']}</td>
            <td style="padding:10px;">{row['Risk Level']}</td>
            <td style="padding:10px;"><span class="badge-pass">{row['PASS']}</span></td>
            <td style="padding:10px;"><span class="badge-exempt">{row['EXEMPT']}</span></td>
            <td style="padding:10px;"><span class="badge-fail">{row['FAIL']}</span></td>
            <td style="padding:10px;"><span class="badge-review">{row['NEEDS_REVIEW']}</span></td>
            <td style="padding:10px; font-weight:bold; color:#b91c1c;">{row['Flags']}</td>
        </tr>
        """
    html_table += "</tbody></table>"
    st.markdown(html_table, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SCREEN 3: BIDDER IN-DEPTH EVIDENCE & FINDINGS
# ---------------------------------------------------------------------------
elif selected_page.startswith("3."):
    st.header("🔍 Bidder In-Depth Evidence & Discrepancies")
    tender = db.query(Tender).first()
    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all() if tender else []

    if not bidders:
        st.warning("No bidders found.")
    else:
        bidder_map = {f"{b.label}: {b.name}": b for b in bidders}
        selected_b_str = st.selectbox("Select Bidder to Inspect:", list(bidder_map.keys()))
        bidder = bidder_map[selected_b_str]

        # Top summary card for chosen bidder
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Compliance Score", f"{bidder.compliance_score:.0f}%" if bidder.compliance_score else "N/A")
        c2.metric("Risk Level", bidder.risk_level or "N/A")
        c3.metric("Quoted Price", f"₹{bidder.quoted_price:,.0f}" if bidder.quoted_price else "—")
        c4.metric("Active Flags", len(bidder.flags))

        tab_rules, tab_evidence, tab_flags, tab_mock = st.tabs(
            ["📋 Eligibility Criteria Table", "📄 Document & Evidence Viewer", "🚩 Discrepancies & Flags", "🏛️ Mock Registry Cross-Check"]
        )

        with tab_rules:
            st.subheader("Evaluated Criteria & Deterministic Outcomes")
            st.markdown(
                "Every outcome carries a human-readable reason and linked evidence fields. "
                "The Procurement Officer may override any outcome with a mandatory documented justification."
            )

            for rr in bidder.rule_results:
                badge_class = {
                    RuleOutcome.PASS.value: "badge-pass",
                    RuleOutcome.FAIL.value: "badge-fail",
                    RuleOutcome.EXEMPT.value: "badge-exempt",
                    RuleOutcome.NEEDS_REVIEW.value: "badge-review",
                }.get(rr.outcome, "badge-review")

                with st.expander(f"{rr.criterion.label} — [{rr.outcome}]", expanded=(rr.outcome != RuleOutcome.PASS.value)):
                    col_info, col_override = st.columns([3, 2])
                    with col_info:
                        st.markdown(f"**Rule ID:** `{rr.rule_id}` | **Mandatory:** `{rr.criterion.mandatory}`")
                        st.markdown(f"**Outcome:** <span class='{badge_class}'>{rr.outcome}</span>", unsafe_allow_html=True)
                        st.markdown(f"**Reason:** {rr.reason}")
                        if rr.evidence_field_ids:
                            st.markdown(f"**Evidence Fields:** `{', '.join(rr.evidence_field_ids)}`")

                        if rr.officer_override:
                            st.info(f"**OVERRIDDEN by {rr.override_by}** to `{rr.officer_override}`.\n\n*Justification:* {rr.override_reason}")

                    with col_override:
                        if role == "Procurement Officer":
                            st.markdown("**Officer Override**")
                            new_outcome = st.selectbox(
                                "Override Outcome",
                                ["", "PASS", "FAIL", "EXEMPT", "NEEDS_REVIEW"],
                                key=f"ov_out_{rr.id}",
                            )
                            reason_txt = st.text_area("Mandatory Override Justification", key=f"ov_rsn_{rr.id}")
                            if st.button("Apply Override", key=f"btn_ov_{rr.id}"):
                                if not new_outcome or not reason_txt.strip():
                                    st.error("Both an outcome and a written justification are required to override.")
                                else:
                                    rr.officer_override = new_outcome
                                    rr.override_reason = reason_txt.strip()
                                    rr.override_by = "Procurement Officer"
                                    rr.override_at = datetime.utcnow()
                                    db.commit()

                                    record_audit_action(
                                        db,
                                        action_type=ActionType.OVERRIDE,
                                        actor="Procurement Officer",
                                        payload={
                                            "rule_id": rr.rule_id,
                                            "bidder_id": bidder.id,
                                            "old_outcome": rr.outcome,
                                            "new_outcome": new_outcome,
                                            "reason": reason_txt.strip(),
                                        },
                                        bidder_id=bidder.id,
                                    )
                                    st.success("Override recorded in audit log!")
                                    st.rerun()

        with tab_evidence:
            st.subheader("Document & Evidence Viewer")
            st.markdown("Select an uploaded document to inspect the PDF page with bounding box highlight.")

            doc_options = {d.filename: d for d in bidder.documents}
            if not doc_options:
                st.info("No documents uploaded for this bidder.")
            else:
                chosen_doc_name = st.selectbox("Choose Document to View:", list(doc_options.keys()))
                doc = doc_options[chosen_doc_name]

                col_view, col_fields = st.columns([3, 2])

                with col_fields:
                    st.markdown(f"**Document Type:** `{doc.doc_type}`")
                    st.markdown(f"**SHA-256 Hash:** `{doc.sha256_hash[:16]}...`")
                    st.markdown(f"**Scanned Pages:** `{'Yes' if doc.has_scanned_pages else 'No (Digital Text)'}`")

                    st.markdown("#### Extracted Fields")
                    ext_fields = doc.extracted_fields
                    if not ext_fields:
                        st.info("No fields extracted from this document.")
                    else:
                        selected_ef = None
                        for ef in ext_fields:
                            conf_color = "#16a34a" if ef.confidence >= 0.7 else "#dc2626"
                            st.markdown(
                                f"""
                                <div style='border:1px solid #e2e8f0; border-radius:6px; padding:8px; margin-bottom:8px;'>
                                    <b>{ef.field_name}:</b> <code>{ef.raw_value}</code><br>
                                    <span style='font-size:0.8rem; color:{conf_color};'>Confidence: {ef.confidence:.0%}</span> | Page {ef.page_number}
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                with col_view:
                    # Page selector
                    page_num = st.number_input("Page", min_value=1, max_value=max(1, doc.page_count or 1), value=1)
                    # Find bbox for selected document on this page if available
                    bbox = None
                    matching_field = next((ef for ef in doc.extracted_fields if ef.page_number == page_num and ef.bounding_box), None)
                    if matching_field:
                        bbox = matching_field.bounding_box
                        st.caption(f"Highlighting evidence for field: `{matching_field.field_name}`")

                    try:
                        img_bytes = render_pdf_page_with_highlight(doc.file_path, page_number=page_num, bbox=bbox)
                        st.image(img_bytes, caption=f"{doc.filename} — Page {page_num}", use_container_width=True)
                    except Exception as e:
                        st.error(f"Could not render PDF page: {e}")

        with tab_flags:
            st.subheader("Raised Compliance Flags")
            if not bidder.flags:
                st.success("🎉 Zero compliance flags raised. Submission is clean.")
            else:
                for f in bidder.flags:
                    sev_badge = {
                        "HIGH": '<span class="badge-high">HIGH</span>',
                        "MEDIUM": '<span class="badge-med">MEDIUM</span>',
                        "LOW": '<span class="badge-low">LOW</span>',
                    }.get(f.severity, "")
                    st.markdown(
                        f"""
                        <div style='background:#fff; border-left:4px solid #ef4444; border-radius:6px; padding:12px; margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,0.05);'>
                            <div style='display:flex; justify-content:space-between; align-items:center;'>
                                <b>{f.title}</b>
                                {sev_badge}
                            </div>
                            <p style='margin:6px 0 0 0; color:#475569; font-size:0.9rem;'>{f.detail or ''}</p>
                            <span style='font-size:0.75rem; color:#94a3b8;'>Flag Type: {f.flag_type}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        with tab_mock:
            st.subheader("🏛️ Mock Government Registry Verifications")
            st.markdown(
                "All identifiers are verified against synthetic mock registries for GSTN, MCA/Income Tax, and Udyam."
            )

            # Query mock registry
            gst_ev = next((f for f in bidder.documents for f in f.extracted_fields if f.field_name == "gstin"), None)
            pan_ev = next((f for f in bidder.documents for f in f.extracted_fields if f.field_name == "pan"), None)
            udyam_ev = next((f for f in bidder.documents for f in f.extracted_fields if f.field_name == "udyam_number"), None)

            c_g, c_p, c_u = st.columns(3)

            with c_g:
                st.markdown("#### Mock GSTN")
                if gst_ev:
                    gst_res = MockRegistryService.verify_gstin(gst_ev.raw_value)
                    st.markdown(f"<span class='mock-tag'>[MOCK GSTN]</span>", unsafe_allow_html=True)
                    st.markdown(f"**Query GSTIN:** `{gst_res.query_identifier}`")
                    st.markdown(f"**Status:** `{gst_res.status}`")
                    st.markdown(f"**Legal Name:** {gst_res.legal_name or 'N/A'}")
                else:
                    st.info("No GSTIN extracted")

            with c_p:
                st.markdown("#### Mock Income Tax (PAN)")
                if pan_ev:
                    pan_res = MockRegistryService.verify_pan(pan_ev.raw_value)
                    st.markdown(f"<span class='mock-tag'>[MOCK PAN]</span>", unsafe_allow_html=True)
                    st.markdown(f"**Query PAN:** `{pan_res.query_identifier}`")
                    st.markdown(f"**Status:** `{pan_res.status}`")
                    st.markdown(f"**Name:** {pan_res.legal_name or 'N/A'}")
                else:
                    st.info("No PAN extracted")

            with c_u:
                st.markdown("#### Mock Udyam MSME")
                if udyam_ev:
                    ud_res = MockRegistryService.verify_udyam(udyam_ev.raw_value)
                    st.markdown(f"<span class='mock-tag'>[MOCK UDYAM]</span>", unsafe_allow_html=True)
                    st.markdown(f"**Udyam No:** `{ud_res.query_identifier}`")
                    st.markdown(f"**Status:** `{ud_res.status}`")
                    st.markdown(f"**Category:** {ud_res.category or 'N/A'}")
                    st.markdown(f"**Valid Until:** `{ud_res.expiry_date or 'N/A'}`")
                else:
                    st.info("No Udyam number extracted")

# ---------------------------------------------------------------------------
# SCREEN 4: CROSS-BIDDER COMPARISON
# ---------------------------------------------------------------------------
elif selected_page.startswith("4."):
    st.header("⚖️ Cross-Bidder Comparison Matrix")
    st.markdown("Side-by-side evaluation comparison across all submitted bidders.")

    tender = db.query(Tender).first()
    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all() if tender else []
    criteria = db.query(Criterion).filter(Criterion.tender_id == tender.id).all() if tender else []

    if not bidders:
        st.warning("No bidders found.")
    else:
        # Comparison Table
        matrix = []
        for crit in criteria:
            row = {"Criterion": crit.label, "Mandatory": "Yes" if crit.mandatory else "No"}
            for b in bidders:
                res = next((r for r in b.rule_results if r.criterion_id == crit.id), None)
                if res:
                    row[b.label] = f"{res.outcome}"
                else:
                    row[b.label] = "—"
            matrix.append(row)

        st.dataframe(matrix, use_container_width=True)

        st.subheader("Quoted Price vs Market Benchmark Comparison")
        price_data = []
        for b in bidders:
            price_data.append({"Bidder": f"{b.label} ({b.name[:20]})", "Price (INR)": b.quoted_price or 0})
        st.bar_chart(data=price_data, x="Bidder", y="Price (INR)", use_container_width=True)

# ---------------------------------------------------------------------------
# SCREEN 5: OFFICER DECISION & EXPORT
# ---------------------------------------------------------------------------
elif selected_page.startswith("5."):
    st.header("✍️ Officer Evaluation Decision & Report Export")
    st.markdown("Record the official verdict and generate an audit-ready evaluation report.")

    tender = db.query(Tender).first()
    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all() if tender else []

    if not bidders:
        st.warning("No bidders found.")
    else:
        bidder_map = {f"{b.label}: {b.name}": b for b in bidders}
        chosen_str = st.selectbox("Select Bidder for Final Recommendation:", list(bidder_map.keys()))
        b = bidder_map[chosen_str]

        # Recommendation suggestion
        system_rec = "SHORTLIST" if b.risk_level == RiskLevel.LOW.value else ("REJECT" if b.risk_level == RiskLevel.HIGH.value else "REFER")

        st.markdown(
            f"""
            <div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:1rem; margin-bottom:1rem;'>
                <b>System Diagnostic Recommendation:</b> <code>{system_rec}</code><br>
                <small style='color:#64748b;'>Note: The system recommendation is strictly non-binding. The officer records the legal decision.</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_dec, col_notes = st.columns([1, 2])

        with col_dec:
            officer_choice = st.selectbox(
                "Officer Official Verdict",
                ["SHORTLIST", "REJECT", "REFER FOR CLARIFICATION"],
                disabled=(role == "Independent Auditor"),
            )
            officer_name = st.text_input("Officer Name", value="A. K. Sharma, Dy. Director (Procurement)", disabled=(role == "Independent Auditor"))

        with col_notes:
            notes = st.text_area("Officer Decision Notes & Legal Rationale", value=f"Evaluated compliant with GeM criteria after verification.", disabled=(role == "Independent Auditor"))

        if role == "Procurement Officer":
            if st.button("💾 Record Formal Decision", type="primary"):
                dec = Decision(
                    bidder_id=b.id,
                    tender_id=tender.id,
                    system_recommendation=system_rec,
                    officer_decision=officer_choice,
                    officer_name=officer_name,
                    officer_notes=notes,
                    decided_at=datetime.utcnow(),
                )
                db.add(dec)
                db.commit()

                record_audit_action(
                    db,
                    action_type=ActionType.DECISION,
                    actor=officer_name,
                    payload={
                        "bidder_id": b.id,
                        "bidder_label": b.label,
                        "officer_verdict": officer_choice,
                        "system_recommendation": system_rec,
                        "notes": notes,
                    },
                    tender_id=tender.id,
                    bidder_id=b.id,
                )
                st.success(f"Official decision for {b.label} recorded and permanently linked to the audit log!")

        st.divider()
        st.subheader("📄 Export Formal Evaluation Report")

        # HTML report generator
        html_report = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Bid Compliance Evaluation Report - {b.label}</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #1e293b; }}
                h1 {{ color: #0f172a; border-bottom: 2px solid #0284c7; padding-bottom: 8px; }}
                .badge {{ padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #cbd5e1; padding: 10px; text-align: left; }}
                th {{ background: #f8fafc; }}
                .disclaimer {{ background: #fef3c7; padding: 10px; border-left: 4px solid #f59e0b; margin: 20px 0; font-size: 12px; }}
            </style>
        </head>
        <body>
            <h1>GeM Bid Compliance Evaluation Report</h1>
            <div class="disclaimer">
                <b>LEGAL NOTICE:</b> AI Decision-Support Prototype. All government registries (GSTN/MCA/Udyam) are MOCK services. Final authority rests with the Procurement Officer.
            </div>
            <h3>Tender Details</h3>
            <p><b>Tender ID:</b> {tender.gem_id} | <b>Title:</b> {tender.title}</p>
            <h3>Bidder Evaluation: {b.label} ({b.name})</h3>
            <p><b>Compliance Score:</b> {b.compliance_score:.1f}% | <b>Assessed Risk Level:</b> {b.risk_level}</p>
            <p><b>Officer Final Verdict:</b> {officer_choice} (Officer: {officer_name})</p>
            <p><b>Officer Rationale:</b> {notes}</p>
            <h3>Eligibility Checklist Findings</h3>
            <table>
                <tr>
                    <th>Rule ID</th>
                    <th>Criterion</th>
                    <th>Outcome</th>
                    <th>Reason / Verification Finding</th>
                </tr>
        """
        for rr in b.rule_results:
            html_report += f"""
                <tr>
                    <td><b>{rr.rule_id}</b></td>
                    <td>{rr.criterion.label}</td>
                    <td><b>{rr.outcome}</b></td>
                    <td>{rr.reason}</td>
                </tr>
            """
        html_report += f"""
            </table>
            <p style='margin-top:40px; font-size:11px; color:#64748b;'>Generated by BidCheck Compliance Engine on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Hash-chained audit trail active.</p>
        </body>
        </html>
        """

        st.download_button(
            label="📥 Download Evaluation Report (HTML)",
            data=html_report,
            file_name=f"Evaluation_Report_{b.label.replace(' ', '_')}_{tender.gem_id.replace('/', '_')}.html",
            mime="text/html",
        )

# ---------------------------------------------------------------------------
# SCREEN 6: AUDIT TRAIL & TAMPER VERIFICATION
# ---------------------------------------------------------------------------
elif selected_page.startswith("6."):
    st.header("🔐 Tamper-Evident SHA-256 Audit Trail")
    st.markdown(
        "Every event (upload, extraction, rule evaluation, flag, officer override, and final decision) "
        "is cryptographically chained to its predecessor using SHA-256."
    )

    col_btn, col_tamper = st.columns([1, 1])

    with col_btn:
        if st.button("🛡️ Verify Audit Log Integrity", type="primary", use_container_width=True):
            is_valid, broken_id, msg = verify_audit_chain(db)
            if is_valid:
                st.success(f"✅ **INTEGRITY VERIFIED:** {msg}")
            else:
                st.error(f"❌ **TAMPERING DETECTED!** {msg}")

    with col_tamper:
        if st.button("🧪 Simulate Audit Log Tampering (Demo Test)", use_container_width=True):
            last_row = db.query(ActionType).first()
            first_log = db.query(from_statement=None).filter().first() if False else db.query(
                type("AuditLog", (), {})
            )
            from app.models.database import AuditLog as AL
            target = db.query(AL).filter(AL.id > 1).first()
            if target:
                target.payload = {"tampered_record": True, "unauthorized_change": "Score altered"}
                db.commit()
                st.warning(f"Tampered row {target.id} payload in SQLite! Click 'Verify Audit Log Integrity' to inspect detection.")
            else:
                st.info("No audit row available to tamper.")

    # Audit log table
    from app.models.database import AuditLog as AL
    logs = db.query(AL).order_by(AL.id.desc()).limit(50).all()

    st.markdown(f"#### Audit Log Records ({len(logs)} most recent)")

    log_data = []
    for l in logs:
        log_data.append(
            {
                "ID": l.id,
                "Action": l.action_type,
                "Actor": l.actor,
                "Prev Hash": f"{l.prev_hash[:10]}...",
                "Row Hash": f"{l.row_hash[:10]}...",
                "Timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else "",
                "Payload Summary": json.dumps(l.payload)[:60] + "...",
            }
        )
    st.dataframe(log_data, use_container_width=True)

db.close()
