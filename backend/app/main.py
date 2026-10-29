from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .analysis import select_forecasts, selection_cutoff, vintage_summary
from .auctions import Auction, get_auction
from .elexon import Actual, ElexonClient, ElexonError, Forecast

app = FastAPI(title="WindDesk API", version="3.0.0")
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])

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
    """Format source values into an auction product grid without modelling new values."""
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
        rows.append({
            "start_time": iso(cursor),
            "end_time": iso(cursor + step),
            "status": status,
            "product_minutes": auction.product_minutes,
            "forecast_source_start_time": iso(source_start) if forecast else None,
            "forecast_source_resolution_minutes": 60 if forecast else None,
            "forecast_mw": forecast.generation_mw if forecast else None,
            "forecast_mwh": forecast_mwh,
            "forecast_publish_time": iso(forecast.publish_time) if forecast else None,
            "actual_mw": actual_mw,
            "actual_mwh": actual_mwh,
            "actual_available_time": iso(max(published_actuals)) if published_actuals else None,
            "signed_error_mwh": signed_error,
            "absolute_error_mwh": round(abs(signed_error), 3) if signed_error is not None else None,
        })
        cursor += step
    return rows


def energy_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    matched = [row for row in rows if row["status"] in {"matched", "source_allocated"}]
    forecast_total = sum(row["forecast_mwh"] for row in rows if row["forecast_mwh"] is not None)
    actual_total = sum(row["actual_mwh"] for row in rows if row["actual_mwh"] is not None)
    if not matched:
        return {"matched_products": 0, "forecast_energy_mwh": round(forecast_total, 1) if forecast_total else None, "actual_energy_mwh": round(actual_total, 1) if actual_total else None, "signed_error_mwh": None, "absolute_error_mwh": None, "mae_mwh": None, "rmse_mwh": None, "bias_mwh": None, "wape_percent": None}
    errors = [row["signed_error_mwh"] for row in matched]
    absolute_total = sum(abs(error) for error in errors)
    matched_actual_total = sum(row["actual_mwh"] for row in matched)
    return {"matched_products": len(matched), "forecast_energy_mwh": round(sum(row["forecast_mwh"] for row in matched), 1), "actual_energy_mwh": round(matched_actual_total, 1), "signed_error_mwh": round(sum(errors), 1), "absolute_error_mwh": round(absolute_total, 1), "mae_mwh": round(absolute_total / len(errors), 1), "rmse_mwh": round(sqrt(sum(error * error for error in errors) / len(errors)), 1), "bias_mwh": round(sum(errors) / len(errors), 1), "wape_percent": round(absolute_total / matched_actual_total * 100, 1) if matched_actual_total else None}


def daily_summaries(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[date, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[datetime.fromisoformat(row["start_time"].replace("Z", "+00:00")).date()].append(row)
    return [{"date": day.isoformat(), **energy_metrics(day_rows)} for day, day_rows in sorted(grouped.items())]


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/analysis")
async def analysis(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    mode: str = Query(default="decision", pattern="^(decision|latest|vintage|live)$"),
    auction: str = Query(default="epex_60", pattern="^(epex_60|n2ex_60|epex_30)$"),
    cutoff_time: Optional[str] = Query(default=None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"),
    cutoff_hour: Optional[int] = Query(default=None, ge=0, le=23),
    vintage_time: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    if mode == "live" and start_date is None:
        start_date = datetime.now(timezone.utc).date() + timedelta(days=1)
    start_date = start_date or DEFAULT_START
    end_date = end_date or (start_date if mode == "live" else DEFAULT_END)
    start, end = validate_window(start_date, end_date)
    auction_definition = get_auction(auction)
    resolved_cutoff = cutoff_time or (f"{cutoff_hour:02d}:00" if cutoff_hour is not None else auction_definition.cutoff_time_utc.strftime("%H:%M"))
    cutoff_clock = datetime.strptime(resolved_cutoff, "%H:%M").time()
    now = datetime.now(timezone.utc)
    client = ElexonClient(os.getenv("ELEXON_API_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"))
    publish_from = start - timedelta(days=7)
    publish_to = now if mode == "live" else end
    if mode == "decision":
        publish_to = end - timedelta(days=1) + timedelta(hours=cutoff_clock.hour, minutes=cutoff_clock.minute)
    if mode == "vintage" and vintage_time:
        publish_to = vintage_time.astimezone(timezone.utc)
    try:
        forecasts = await client.forecasts(start, end, publish_from, publish_to)
        actuals = [] if mode == "live" else await client.actuals(start, end)
    except ElexonError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    selected = select_forecasts(forecasts, mode, cutoff_clock, now if mode == "live" else vintage_time.astimezone(timezone.utc) if vintage_time else None)
    periods = serialise_periods(actuals, selected, start, end)
    products = product_rows(actuals, selected, start, end, auction_definition)
    status_counts = {status: sum(1 for row in products if row["status"] == status) for status in ("matched", "source_allocated", "forecast_only", "actual_only", "missing")}
    labels = {"decision": "Decision-time forecast", "latest": "Retrospective latest forecast", "vintage": "Selected forecast vintage", "live": "Latest published forecast"}
    return {
        "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "auction": auction_definition.serialise(),
        "selection": {"mode": mode, "label": labels[mode], "cutoff_time_utc": resolved_cutoff if mode == "decision" else None, "assumption": "Each product uses the latest source forecast published by its own day-before auction cutoff." if mode == "decision" else "This is a source-data display, not a procurement recommendation."},
        "metrics": energy_metrics(products),
        "coverage": {"expected_products": len(products), **status_counts, **vintage_summary(forecasts)},
        "products": products,
        "periods": periods,
        "daily": daily_summaries(products),
        "retrieved_at": iso(now),
    }


@app.get("/api/vintages")
async def vintages(
    start_time: datetime,
    mode: str = Query(default="decision", pattern="^(decision|latest|vintage|live)$"),
    cutoff_time: str = Query(default="09:20", pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"),
    vintage_time: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    source_target = start_time.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    client = ElexonClient(os.getenv("ELEXON_API_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"))
    try:
        forecasts = await client.forecasts(source_target, source_target + timedelta(hours=1), source_target - timedelta(days=7), datetime.now(timezone.utc))
    except ElexonError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    rows = sorted((forecast for forecast in forecasts if forecast.start_time == source_target), key=lambda value: value.publish_time)
    cutoff_clock = datetime.strptime(cutoff_time, "%H:%M").time()
    selected = select_forecasts(rows, mode, cutoff_clock, vintage_time.astimezone(timezone.utc) if vintage_time else datetime.now(timezone.utc) if mode == "live" else None)
    decision_cutoff = selection_cutoff(source_target, cutoff_clock)

    def eligibility(row: Forecast) -> str:
        if row.publish_time > source_target:
            return "published_after_delivery"
        if mode == "decision" and row.publish_time > decision_cutoff:
            return "available_after_cutoff"
        return "eligible"

    return {
        "source_interval_start": iso(source_target),
        "decision_cutoff": iso(decision_cutoff) if mode == "decision" else None,
        "vintages": [
            {
                "publish_time": iso(row.publish_time),
                "generation_mw": row.generation_mw,
                "eligibility": eligibility(row),
                "selected": selected.get(source_target) == row,
            }
            for row in rows
        ],
    }
