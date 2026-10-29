from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .analysis import calculate_metrics, match_periods, select_forecasts, selection_cutoff, vintage_summary
from .elexon import Actual, ElexonClient, ElexonError, Forecast

app = FastAPI(title="WindDesk API", version="2.0.0")
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])


def validate_window(start_date: date, end_date: date) -> Tuple[datetime, datetime]:
    if start_date > end_date or start_date.year != 2026 or end_date.year != 2026 or start_date.month != 1 or end_date.month != 1:
        raise HTTPException(status_code=422, detail="This pilot is limited to an ordered January 2026 delivery window.")
    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    return start, datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)


def serialise_periods(actuals: List[Actual], selected: Dict[datetime, Forecast], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    actual_by_time = {actual.start_time: actual for actual in actuals}
    rows: List[Dict[str, Any]] = []
    cursor = start
    while cursor < end:
        actual = actual_by_time.get(cursor)
        forecast = selected.get(cursor)
        if actual and forecast:
            status = "matched"
            error = round(forecast.generation_mw - actual.generation_mw, 1)
        elif forecast:
            status = "forecast_only"
            error = None
        elif actual:
            status = "actual_only"
            error = None
        else:
            status = "missing"
            error = None
        rows.append({
            "start_time": cursor.isoformat().replace("+00:00", "Z"),
            "actual_mw": actual.generation_mw if actual else None,
            "actual_publish_time": actual.publish_time.isoformat().replace("+00:00", "Z") if actual and actual.publish_time else None,
            "forecast_mw": forecast.generation_mw if forecast else None,
            "error_mw": error,
            "publish_time": forecast.publish_time.isoformat().replace("+00:00", "Z") if forecast else None,
            "status": status,
        })
        cursor += timedelta(minutes=30)
    return rows


def daily_summaries(actuals: List[Actual], selected: Dict[datetime, Forecast]) -> List[Dict[str, Any]]:
    grouped_actuals: Dict[date, List[Actual]] = defaultdict(list)
    grouped_selected: Dict[date, Dict[datetime, Forecast]] = defaultdict(dict)
    for actual in actuals:
        grouped_actuals[actual.start_time.date()].append(actual)
    for timestamp, forecast in selected.items():
        grouped_selected[timestamp.date()][timestamp] = forecast
    rows = []
    for delivery_day in sorted(set(grouped_actuals) | set(grouped_selected)):
        periods = match_periods(grouped_actuals[delivery_day], grouped_selected[delivery_day])
        rows.append({"date": delivery_day.isoformat(), **calculate_metrics(periods)})
    return rows


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/analysis")
async def analysis(
    start_date: date = Query(default=date(2026, 1, 1)),
    end_date: date = Query(default=date(2026, 1, 31)),
    mode: str = Query(default="decision", pattern="^(decision|latest|vintage)$"),
    cutoff_time: Optional[str] = Query(default=None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$"),
    cutoff_hour: Optional[int] = Query(default=None, ge=0, le=23),
    vintage_time: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    start, end = validate_window(start_date, end_date)
    resolved_cutoff = cutoff_time or (f"{cutoff_hour:02d}:00" if cutoff_hour is not None else "09:20")
    cutoff_clock = datetime.strptime(resolved_cutoff, "%H:%M").time()
    client = ElexonClient(os.getenv("ELEXON_API_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"))
    publish_from = start - timedelta(days=7)
    publish_to = end if mode == "latest" else end - timedelta(days=1) + timedelta(hours=cutoff_clock.hour, minutes=cutoff_clock.minute)
    if mode == "vintage" and vintage_time:
        publish_to = vintage_time.astimezone(timezone.utc)
    try:
        actuals, forecasts = await client.actuals(start, end), await client.forecasts(start, end, publish_from, publish_to)
    except ElexonError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    selected = select_forecasts(forecasts, mode, cutoff_clock, vintage_time.astimezone(timezone.utc) if vintage_time else None)
    matched = match_periods(actuals, selected)
    periods = serialise_periods(actuals, selected, start, end)
    status_counts = {status: sum(1 for row in periods if row["status"] == status) for status in ("matched", "forecast_only", "actual_only", "missing")}
    label = {"decision": "Decision-time forecast", "latest": "Retrospective latest forecast", "vintage": "Selected forecast vintage"}[mode]
    return {
        "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "selection": {
            "mode": mode,
            "label": label,
            "cutoff_time_utc": resolved_cutoff if mode == "decision" else None,
            "cutoff_hour_utc": cutoff_clock.hour if mode == "decision" else None,
            "assumption": "Each delivery period uses the latest forecast published by its own day-ahead cutoff." if mode == "decision" else "This view is for comparison and was not necessarily available at the procurement decision time.",
        },
        "metrics": calculate_metrics(matched),
        "coverage": {"expected_periods": len(periods), **status_counts, **vintage_summary(forecasts)},
        "periods": periods,
        "daily": daily_summaries(actuals, selected),
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@app.get("/api/vintages")
async def vintages(start_time: datetime) -> Dict[str, Any]:
    target = start_time.astimezone(timezone.utc).replace(minute=0 if start_time.minute == 0 else 30, second=0, microsecond=0)
    if target.year != 2026 or target.month != 1:
        raise HTTPException(status_code=422, detail="This pilot is limited to January 2026.")
    client = ElexonClient(os.getenv("ELEXON_API_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"))
    try:
        forecasts = await client.forecasts(target, target + timedelta(minutes=30), target - timedelta(days=7), target)
    except ElexonError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    rows = sorted((forecast for forecast in forecasts if forecast.start_time == target), key=lambda value: value.publish_time)
    return {"start_time": target.isoformat().replace("+00:00", "Z"), "vintages": [{"publish_time": row.publish_time.isoformat().replace("+00:00", "Z"), "generation_mw": row.generation_mw} for row in rows]}
