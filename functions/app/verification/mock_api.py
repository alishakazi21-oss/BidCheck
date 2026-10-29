"""
BidCheck - Mock Registry FastAPI Router.

Provides HTTP endpoints to inspect mock government registries (GSTN, PAN, Udyam).
"""

from fastapi import APIRouter
from app.verification.mock_registry import MockRegistryResponse, MockRegistryService

router = APIRouter(prefix="/mock-registry", tags=["Mock Government Registries"])


@router.get("/gstin/{gstin}", response_model=MockRegistryResponse)
def lookup_gstin(gstin: str):
    """Query mock GSTN portal."""
    return MockRegistryService.verify_gstin(gstin)


@router.get("/pan/{pan}", response_model=MockRegistryResponse)
def lookup_pan(pan: str):
    """Query mock Income Tax PAN portal."""
    return MockRegistryService.verify_pan(pan)


@router.get("/udyam/{udyam_number}", response_model=MockRegistryResponse)
def lookup_udyam(udyam_number: str):
    """Query mock MSME Udyam portal."""
    return MockRegistryService.verify_udyam(udyam_number)
