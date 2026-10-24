"""
BidCheck - Extractor Factory.

Instantiates either FakeExtractor or LLMExtractor based on configuration or environment variable.
"""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.extraction.base import BaseExtractor
from app.extraction.fake_extractor import FakeExtractor
from app.extraction.llm_extractor import LLMExtractor


def get_extractor(backend: Optional[str] = None) -> BaseExtractor:
    """
    Return extractor instance based on setting or parameter ('llm' or 'fake').
    Defaults to 'fake' for offline reliability.
    """
    chosen = (backend or settings.extractor).lower().strip()
    if chosen == "llm":
        return LLMExtractor()
    return FakeExtractor()
