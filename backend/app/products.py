"""Transform Elexon source records into auditable auction-product rows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from .auctions import Auction
from .elexon import Actual, Forecast
from .window import iso


def serialise_periods(actuals: List[Actual], selected: Dict[datetime, Forecast], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Return source-resolution completeness rows without inventing forecasts."""
    actual_by_time = {actual.start_time: actual for actual in actuals}
    rows: List[Dict[str, Any]] = []
    cursor = start
    while cursor < end:
        actual = actual_by_time.get(cursor)
        forecast = selected.get(cursor)
        if actual and forecast:
            status, error = "matched", round(forecast.generation_mw - actual.generation_mw, 1)
        elif forecast:
            status, error = "forecast_only", None
        elif actual:
            status, error = "actual_only", None
        else:
            status, error = "missing", None
        rows.append({"start_time": iso(cursor), "actual_mw": actual.generation_mw if actual else None, "actual_publish_time": iso(actual.publish_time) if actual else None, "forecast_mw": forecast.generation_mw if forecast else None, "error_mw": error, "publish_time": iso(forecast.publish_time) if forecast else None, "status": status})
        cursor += timedelta(minutes=30)
    return rows


def product_rows(actuals: List[Actual], selected: Dict[datetime, Forecast], start: datetime, end: datetime, auction: Auction) -> List[Dict[str, Any]]:
    """Format source values into an auction grid without modelling new forecasts."""
    actual_by_time = {actual.start_time: actual for actual in actuals}
    rows: List[Dict[str, Any]] = []
    cursor = start
    step = timedelta(minutes=auction.product_minutes)
    while cursor < end:
        source_start = cursor.replace(minute=0, second=0, microsecond=0)
        forecast = selected.get(source_start)
        duration_hours = auction.product_minutes / 60
        actual_slots = [actual_by_time.get(cursor + timedelta(minutes=offset)) for offset in range(0, auction.product_minutes, 30)]
        actual_available = all(actual_slots)
        actual_mwh = round(sum(slot.generation_mw * 0.5 for slot in actual_slots), 3) if actual_available else None
        actual_mw = round(actual_mwh / duration_hours, 3) if actual_mwh is not None else None
        forecast_mwh = round(forecast.generation_mw * duration_hours, 3) if forecast else None
        if forecast and actual_available:
            status = "source_allocated" if auction.product_minutes == 30 else "matched"
        elif forecast:
            status = "forecast_only"
        elif actual_available:
            status = "actual_only"
        else:
            status = "missing"
        signed_error = round(forecast_mwh - actual_mwh, 3) if forecast_mwh is not None and actual_mwh is not None else None
        published_actuals = [slot.publish_time for slot in actual_slots if slot and slot.publish_time]
        rows.append({"start_time": iso(cursor), "end_time": iso(cursor + step), "status": status, "product_minutes": auction.product_minutes, "forecast_source_start_time": iso(source_start) if forecast else None, "forecast_source_resolution_minutes": 60 if forecast else None, "forecast_mw": forecast.generation_mw if forecast else None, "forecast_mwh": forecast_mwh, "forecast_publish_time": iso(forecast.publish_time) if forecast else None, "actual_mw": actual_mw, "actual_mwh": actual_mwh, "actual_available_time": iso(max(published_actuals)) if published_actuals else None, "signed_error_mwh": signed_error, "absolute_error_mwh": round(abs(signed_error), 3) if signed_error is not None else None})
        cursor += step
    return rows
