"""Delivery-window validation and timestamp serialisation helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException


DEFAULT_START = date(2026, 1, 1)
DEFAULT_END = date(2026, 1, 31)
MAX_WINDOW_DAYS = 62


def validate_window(start_date: date, end_date: date) -> Tuple[datetime, datetime]:
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="The delivery start date must not be after the end date.")
    if (end_date - start_date).days + 1 > MAX_WINDOW_DAYS:
        raise HTTPException(status_code=422, detail=f"Delivery windows are limited to {MAX_WINDOW_DAYS} days per request.")
    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    return start, datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat().replace("+00:00", "Z") if value else None
