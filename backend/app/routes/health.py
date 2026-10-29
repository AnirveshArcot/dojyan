"""Liveness route."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
async def health() -> Dict[str, str]:
    """Return a dependency-free liveness response for probes and deployment checks.

    This endpoint verifies that FastAPI can receive a request.
    It intentionally does not make an Elexon request, so an upstream outage does
    not incorrectly report the API process itself as unavailable.
    """
    return {"status": "ok"}
