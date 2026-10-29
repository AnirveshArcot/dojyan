"""Analysis route and request validation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from ..elexon import ElexonError
from ..services import build_analysis

router = APIRouter(prefix="/api")


@router.get("/analysis")
async def analysis(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    mode: str = Query(default="decision", pattern="^(decision|latest|vintage|live)$"),
    auction: str = Query(default="epex_60", pattern="^(epex_60|n2ex_60|epex_30)$"),
    cutoff_time: Optional[str] = Query(default=None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"),
    cutoff_hour: Optional[int] = Query(default=None, ge=0, le=23),
    vintage_time: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    """Validate analysis query parameters and return the dashboard payload.

    FastAPI validates mode, auction, dates, and cutoff format before this handler
    calls the application service.
    Elexon errors are translated to HTTP 502 because the request cannot be
    fulfilled due to an upstream data-provider failure.
    """
    try:
        return await build_analysis(start_date, end_date, mode, auction, cutoff_time, cutoff_hour, vintage_time)
    except ElexonError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
