"""
BidCheck - Base Extractor Interface.

All extraction backends (offline fake extractor, online LLM extractor, OCR pipeline)
implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.extraction.schema import ExtractedDocumentData, ParsedTenderSchema


class BaseExtractor(ABC):
    """
    Abstract interface for document and tender extraction.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the extractor implementation ('fake' or 'llm')."""
        pass

    @abstractmethod
    def extract_tender(
        self,
        pdf_path: str,
        sidecar_path: Optional[str] = None,
    ) -> ParsedTenderSchema:
        """
        Extract structured tender metadata and criteria checklist from a tender document.
        """
        pass

    @abstractmethod
    def extract_document(
        self,
        pdf_path: str,
        doc_type: str,
        sidecar_path: Optional[str] = None,
    ) -> ExtractedDocumentData:
        """
        Extract key compliance evidence fields from a bidder's document.
        """
        pass
