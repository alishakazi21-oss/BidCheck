"""
BidCheck - Fake Extractor (Offline & Deterministic).

Reads fields directly from the ground-truth sidecar JSON accompanying each
dummy document. Enables the complete offline demo without any LLM API key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.extraction.base import BaseExtractor
from app.extraction.schema import (
    CriterionSchema,
    ExtractedDocumentData,
    ExtractedFieldValue,
    ParsedTenderSchema,
)


class FakeExtractor(BaseExtractor):
    """
    Offline extractor reading ground-truth sidecar JSON files.
    Guarantees deterministic, fast, offline execution for demos and tests.
    """

    @property
    def name(self) -> str:
        return "fake"

    def _resolve_sidecar_path(self, pdf_path: str, sidecar_path: Optional[str] = None) -> Path:
        if sidecar_path and Path(sidecar_path).is_file():
            return Path(sidecar_path)
        p = Path(pdf_path)
        direct_sidecar = p.with_suffix(".json")
        if direct_sidecar.is_file():
            return direct_sidecar
        raise FileNotFoundError(f"Sidecar JSON not found for document: {pdf_path}")

    def extract_tender(
        self,
        pdf_path: str,
        sidecar_path: Optional[str] = None,
    ) -> ParsedTenderSchema:
        """
        Extract tender checklist from sidecar JSON or raise FileNotFoundError.
        """
        json_file = self._resolve_sidecar_path(pdf_path, sidecar_path)
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        tender_dict = data.get("tender", data)
        raw_criteria = tender_dict.get("criteria", {})

        criteria_map = {}
        for rule_id, c_data in raw_criteria.items():
            criteria_map[rule_id] = CriterionSchema(
                rule_id=rule_id,
                label=c_data.get("label", rule_id),
                mandatory=c_data.get("mandatory", True),
                threshold_value=str(c_data["threshold_value"]) if c_data.get("threshold_value") is not None else None,
                threshold_unit=c_data.get("threshold_unit"),
                exemption_categories=c_data.get("exemption_categories", []),
            )

        return ParsedTenderSchema(
            gem_id=tender_dict.get("gem_id", "GeM/UNKNOWN"),
            title=tender_dict.get("title", "Untitled GeM Tender"),
            category=tender_dict.get("category", "IT Hardware"),
            description=tender_dict.get("description"),
            bid_submission_deadline=tender_dict.get("bid_submission_deadline"),
            criteria=criteria_map,
        )

    def extract_document(
        self,
        pdf_path: str,
        doc_type: str,
        sidecar_path: Optional[str] = None,
    ) -> ExtractedDocumentData:
        """
        Extract fields from sidecar JSON into structured ExtractedDocumentData.
        """
        json_file = self._resolve_sidecar_path(pdf_path, sidecar_path)
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_fields = data.get("fields", {})
        parsed_fields = {}
        for field_name, val_dict in raw_fields.items():
            if isinstance(val_dict, dict):
                parsed_fields[field_name] = ExtractedFieldValue(
                    value=val_dict.get("value"),
                    confidence=float(val_dict.get("confidence", 1.0)),
                    page=int(val_dict.get("page", 1)),
                    snippet=val_dict.get("snippet"),
                    bbox=val_dict.get("bbox"),
                )
            else:
                parsed_fields[field_name] = ExtractedFieldValue(
                    value=val_dict,
                    confidence=1.0,
                    page=1,
                    snippet=str(val_dict),
                )

        return ExtractedDocumentData(
            bidder_label=data.get("bidder_label"),
            bidder_name=data.get("bidder_name"),
            doc_type=data.get("doc_type", doc_type),
            filename=data.get("filename", Path(pdf_path).name),
            sha256=data.get("sha256"),
            fields=parsed_fields,
            metadata=data.get("metadata", {}),
        )
