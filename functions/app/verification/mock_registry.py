"""
BidCheck - Mock Verification Registry Service.

Simulates Indian government registries (GSTN, Income Tax / MCA, Udyam MSME)
using preconfigured synthetic records for demo evaluation.

CRITICAL DISCLAIMER:
Live government APIs (GSTN, MCA, Udyam) are NOT connected. This service uses
only synthetic dummy data and mock responses. Every response carries is_mock=True.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class MockRegistryResponse(BaseModel):
    """Standard response model for all mock registry inquiries."""
    is_mock: bool = Field(default=True, description="Always true: confirms mock service")
    disclaimer: str = Field(
        default="MOCK REGISTRY - FOR DEMO PURPOSES ONLY. Not connected to live government portals.",
        description="Statutory mock disclaimer",
    )
    query_identifier: str
    status: str  # ACTIVE | CANCELLED | NOT_FOUND | EXPIRED | SUSPENDED
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    entity_type: Optional[str] = None
    registration_date: Optional[str] = None
    expiry_date: Optional[str] = None
    category: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


# Synthetic Registry Databases
MOCK_GSTIN_DB: Dict[str, Dict[str, Any]] = {
    "27AABCT1234A1Z5": {
        "status": "ACTIVE",
        "legal_name": "TECHSERVE SOLUTIONS PRIVATE LIMITED",
        "trade_name": "TechServe Solutions",
        "entity_type": "Private Limited Company",
        "registration_date": "2017-04-12",
        "state": "Maharashtra",
    },
    "29BBBDE5678B1Z9": {
        "status": "ACTIVE",
        "legal_name": "DATAPRIME ENTERPRISES LLP",
        "trade_name": "DataPrime Enterprises",
        "entity_type": "Limited Liability Partnership",
        "registration_date": "2019-08-20",
        "state": "Karnataka",
    },
    "06CCCQS9012C1Z3": {
        "status": "ACTIVE",
        "legal_name": "QUICKBYTE SYSTEMS",
        "trade_name": "QuickByte Systems",
        "entity_type": "Proprietorship",
        "registration_date": "2020-01-15",
        "state": "Haryana",
    },
    "33DDDGE3456D1Z7": {
        "status": "ACTIVE",
        "legal_name": "GLOBALEDGE IT PRIVATE LIMITED",
        "trade_name": "GlobalEdge IT",
        "entity_type": "Private Limited Company",
        "registration_date": "2018-06-10",
        "state": "Tamil Nadu",
    },
    "24EEETN7890E1Z1": {
        "status": "ACTIVE",
        "legal_name": "NANOTECH COMPONENTS PRIVATE LIMITED",
        "trade_name": "NanoTech Components",
        "entity_type": "Private Limited Company",
        "registration_date": "2021-03-01",
        "state": "Gujarat",
    },
}

MOCK_PAN_DB: Dict[str, Dict[str, Any]] = {
    "AABCT1234A": {
        "status": "VALID",
        "name": "TECHSERVE SOLUTIONS PRIVATE LIMITED",
        "entity_type": "Company",
        "issued_date": "2017-03-25",
    },
    "BBBDE5678B": {
        "status": "VALID",
        "name": "DATAPRIME ENTERPRISES",  # Note: missing "LLP" suffix - planted mismatch
        "entity_type": "Firm",
        "issued_date": "2019-07-15",
    },
    "CCCQS9012C": {
        "status": "VALID",
        "name": "QUICKBYTE SYSTEMS",
        "entity_type": "Individual / Proprietor",
        "issued_date": "2019-12-05",
    },
    "DDDGE3456D": {
        "status": "VALID",
        "name": "GLOBALEDGE IT PRIVATE LIMITED",
        "entity_type": "Company",
        "issued_date": "2018-05-18",
    },
    "EEETN7890E": {
        "status": "VALID",
        "name": "NANOTECH COMPONENTS PRIVATE LIMITED",
        "entity_type": "Company",
        "issued_date": "2021-02-14",
    },
}

MOCK_UDYAM_DB: Dict[str, Dict[str, Any]] = {
    "UDYAM-MH-10-0012345": {
        "status": "ACTIVE",
        "enterprise_name": "TECHSERVE SOLUTIONS PRIVATE LIMITED",
        "category": "Small Enterprise",
        "registration_date": "2020-07-10",
        "expiry_date": "2026-03-31",
    },
    "UDYAM-KA-05-0067890": {
        "status": "ACTIVE",
        "enterprise_name": "DATAPRIME ENTERPRISES LLP",
        "category": "Small Enterprise",
        "registration_date": "2020-09-15",
        "expiry_date": "2025-06-30",
    },
    "UDYAM-HR-02-0034567": {
        # Planted problem for Bidder C: Not verified / Invalid in registry
        "status": "NOT_FOUND",
        "enterprise_name": None,
        "category": None,
        "registration_date": None,
        "expiry_date": None,
    },
    "UDYAM-TN-07-0089012": {
        # Planted problem for Bidder D: Expired in 2023
        "status": "EXPIRED",
        "enterprise_name": "GLOBALEDGE IT PRIVATE LIMITED",
        "category": "Micro Enterprise",
        "registration_date": "2018-08-11",
        "expiry_date": "2023-09-30",
    },
    "UDYAM-GJ-08-0056789": {
        # Positive control for Bidder E: Valid active micro enterprise
        "status": "ACTIVE",
        "enterprise_name": "NANOTECH COMPONENTS PRIVATE LIMITED",
        "category": "Micro Enterprise",
        "registration_date": "2021-04-10",
        "expiry_date": "2026-12-31",
    },
}


class MockRegistryService:
    """Mock registry lookup service."""

    @staticmethod
    def verify_gstin(gstin: str) -> MockRegistryResponse:
        clean = (gstin or "").strip().upper()
        rec = MOCK_GSTIN_DB.get(clean)
        if rec:
            return MockRegistryResponse(
                query_identifier=clean,
                status=rec["status"],
                legal_name=rec.get("legal_name"),
                trade_name=rec.get("trade_name"),
                entity_type=rec.get("entity_type"),
                registration_date=rec.get("registration_date"),
                details=rec,
            )
        return MockRegistryResponse(
            query_identifier=clean,
            status="NOT_FOUND",
            legal_name=None,
        )

    @staticmethod
    def verify_pan(pan: str) -> MockRegistryResponse:
        clean = (pan or "").strip().upper()
        rec = MOCK_PAN_DB.get(clean)
        if rec:
            return MockRegistryResponse(
                query_identifier=clean,
                status=rec["status"],
                legal_name=rec.get("name"),
                entity_type=rec.get("entity_type"),
                registration_date=rec.get("issued_date"),
                details=rec,
            )
        return MockRegistryResponse(
            query_identifier=clean,
            status="NOT_FOUND",
            legal_name=None,
        )

    @staticmethod
    def verify_udyam(udyam_number: str) -> MockRegistryResponse:
        clean = (udyam_number or "").strip().upper()
        rec = MOCK_UDYAM_DB.get(clean)
        if rec:
            return MockRegistryResponse(
                query_identifier=clean,
                status=rec["status"],
                legal_name=rec.get("enterprise_name"),
                category=rec.get("category"),
                registration_date=rec.get("registration_date"),
                expiry_date=rec.get("expiry_date"),
                details=rec,
            )
        return MockRegistryResponse(
            query_identifier=clean,
            status="NOT_FOUND",
            legal_name=None,
        )
