"""Forecast-vintage audit route."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from ..elexon import ElexonError
from ..services import build_vintages

router = APIRouter(prefix="/api")


@router.get("/vintages")
async def vintages(
    start_time: datetime,
    mode: str = Query(default="decision", pattern="^(decision|latest|vintage|live)$"),
    cutoff_time: str = Query(default="09:20", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"),
    vintage_time: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    try:
        return await build_vintages(start_time, mode, cutoff_time, vintage_time)
    except ElexonError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
