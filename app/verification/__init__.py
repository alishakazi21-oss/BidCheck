"""
BidCheck Verification Package.
"""

from app.verification.mock_registry import (
    MockRegistryService,
    MockRegistryResponse,
    MOCK_GSTIN_DB,
    MOCK_PAN_DB,
    MOCK_UDYAM_DB,
)
from app.verification.cross_check import (
    verify_bidder_cross_documents,
    normalize_company_name,
    VerificationDiscrepancy,
)
from app.verification.mock_api import router as mock_registry_router

__all__ = [
    "MockRegistryService",
    "MockRegistryResponse",
    "MOCK_GSTIN_DB",
    "MOCK_PAN_DB",
    "MOCK_UDYAM_DB",
    "verify_bidder_cross_documents",
    "normalize_company_name",
    "VerificationDiscrepancy",
    "mock_registry_router",
]
