"""
BidCheck - LLM Extractor (OpenAI backend with fallback).

Extracts tender criteria and document fields using an LLM.
Validates LLM output against Pydantic schemas. If OpenAI is not configured
or fails, cleanly falls back to FakeExtractor so the application never breaks.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.extraction.base import BaseExtractor
from app.extraction.fake_extractor import FakeExtractor
from app.extraction.schema import (
    CriterionSchema,
    ExtractedDocumentData,
    ExtractedFieldValue,
    ParsedTenderSchema,
)

logger = logging.getLogger(__name__)


class LLMExtractor(BaseExtractor):
    """
    LLM-powered extractor using OpenAI with strict JSON schemas.
    Falls back to FakeExtractor if API key is unset or call fails.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self._fallback_extractor = FakeExtractor()

    @property
    def name(self) -> str:
        return "llm"

    def _extract_pdf_text(self, pdf_path: str) -> str:
        """Extract plain text across all pages using PyMuPDF or pdfplumber."""
        text_parts = []
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                text_parts.append(f"--- PAGE {page_num + 1} ---\n{text}")
            doc.close()
        except Exception as e:
            logger.warning("PyMuPDF failed on %s, trying pdfplumber: %s", pdf_path, e)
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages, start=1):
                        text = page.extract_text() or ""
                        text_parts.append(f"--- PAGE {page_num} ---\n{text}")
            except Exception as e2:
                logger.error("Failed to extract text from %s: %s", pdf_path, e2)
        return "\n\n".join(text_parts)

    def extract_tender(
        self,
        pdf_path: str,
        sidecar_path: Optional[str] = None,
    ) -> ParsedTenderSchema:
        """
        Extract tender checklist using LLM, or fallback to FakeExtractor.
        """
        if not self.api_key:
            logger.info("OPENAI_API_KEY not configured. Falling back to FakeExtractor.")
            return self._fallback_extractor.extract_tender(pdf_path, sidecar_path)

        text = self._extract_pdf_text(pdf_path)
        if not text.strip():
            logger.warning("Empty text extracted from %s. Using FakeExtractor fallback.", pdf_path)
            return self._fallback_extractor.extract_tender(pdf_path, sidecar_path)

        prompt = f"""You are a procurement expert analyzing an Indian GeM tender document.
Extract the tender details and eligibility criteria in exact JSON format:
{{
  "gem_id": "GeM/...",
  "title": "Title of tender",
  "category": "e.g. IT Hardware",
  "description": "Short description",
  "bid_submission_deadline": "YYYY-MM-DD",
  "criteria": {{
    "TURNOVER_MIN": {{
      "rule_id": "TURNOVER_MIN",
      "label": "Minimum average annual turnover",
      "mandatory": true,
      "threshold_value": "3200000",
      "threshold_unit": "INR",
      "exemption_categories": ["MSE", "STARTUP"]
    }},
    "EXPERIENCE_YEARS_MIN": {{
      "rule_id": "EXPERIENCE_YEARS_MIN",
      "label": "Minimum experience years",
      "mandatory": true,
      "threshold_value": "3",
      "threshold_unit": "years",
      "exemption_categories": ["STARTUP"]
    }},
    "OEM_AUTH_PRESENT": {{
      "rule_id": "OEM_AUTH_PRESENT",
      "label": "OEM Authorization required",
      "mandatory": true,
      "threshold_value": null,
      "threshold_unit": null,
      "exemption_categories": ["OEM_ITSELF"]
    }},
    "EMD_OR_EXEMPTION_PROOF": {{
      "rule_id": "EMD_OR_EXEMPTION_PROOF",
      "label": "EMD or Exemption proof",
      "mandatory": true,
      "threshold_value": "50000",
      "threshold_unit": "INR",
      "exemption_categories": ["MSE", "STARTUP"]
    }},
    "CERT_VALIDITY": {{
      "rule_id": "CERT_VALIDITY",
      "label": "Certificate validity on bid date",
      "mandatory": true,
      "threshold_value": "2024-12-31",
      "threshold_unit": "date",
      "exemption_categories": []
    }},
    "GSTIN_PAN_CONSISTENT": {{
      "rule_id": "GSTIN_PAN_CONSISTENT",
      "label": "GSTIN and PAN consistency",
      "mandatory": true,
      "threshold_value": null,
      "threshold_unit": null,
      "exemption_categories": []
    }}
  }}
}}

Tender document text:
{text}
"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=settings.llm_temperature,
            )
            raw_json = response.choices[0].message.content or "{}"
            data = json.loads(raw_json)
            return ParsedTenderSchema.model_validate(data)
        except Exception as e:
            logger.error("LLM tender extraction failed: %s. Using FakeExtractor fallback.", e)
            return self._fallback_extractor.extract_tender(pdf_path, sidecar_path)

    def extract_document(
        self,
        pdf_path: str,
        doc_type: str,
        sidecar_path: Optional[str] = None,
    ) -> ExtractedDocumentData:
        """
        Extract document fields using LLM, or fallback to FakeExtractor.
        """
        if not self.api_key:
            logger.info("OPENAI_API_KEY not configured. Falling back to FakeExtractor.")
            return self._fallback_extractor.extract_document(pdf_path, doc_type, sidecar_path)

        text = self._extract_pdf_text(pdf_path)
        if not text.strip():
            return self._fallback_extractor.extract_document(pdf_path, doc_type, sidecar_path)

        prompt = f"""You are an automated document extraction assistant for procurement compliance.
Analyze the following document of type {doc_type}.
Extract key compliance fields into strict JSON:
{{
  "bidder_name": "company name if present",
  "doc_type": "{doc_type}",
  "fields": {{
    "<field_name>": {{
      "value": <extracted_typed_or_string_value>,
      "confidence": <confidence between 0.0 and 1.0>,
      "page": <page number where found>,
      "snippet": "<verbatim text snippet surrounding this value>"
    }}
  }}
}}

Document text:
{text}
"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=settings.llm_temperature,
            )
            raw_json = response.choices[0].message.content or "{}"
            data = json.loads(raw_json)
            return ExtractedDocumentData.model_validate(data)
        except Exception as e:
            logger.error("LLM document extraction failed: %s. Using FakeExtractor fallback.", e)
            return self._fallback_extractor.extract_document(pdf_path, doc_type, sidecar_path)
