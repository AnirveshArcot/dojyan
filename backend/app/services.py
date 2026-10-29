"""Application services that assemble Elexon data into API response payloads."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .analysis import select_forecasts, selection_cutoff, vintage_summary
from .auctions import get_auction
from .elexon import ElexonClient, Forecast
from .energy_metrics import daily_summaries, energy_metrics
from .products import product_rows, serialise_periods
from .window import DEFAULT_END, DEFAULT_START, iso, validate_window


def _client() -> ElexonClient:
    return ElexonClient(os.getenv("ELEXON_API_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"))


async def build_analysis(
    start_date: Optional[date],
    end_date: Optional[date],
    mode: str,
    auction: str,
    cutoff_time: Optional[str],
    cutoff_hour: Optional[int],
    vintage_time: Optional[datetime],
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
    publish_from = start - timedelta(days=7)
    publish_to = now if mode == "live" else end
    if mode == "decision":
        publish_to = end - timedelta(days=1) + timedelta(hours=cutoff_clock.hour, minutes=cutoff_clock.minute)
    if mode == "vintage" and vintage_time:
        publish_to = vintage_time.astimezone(timezone.utc)
    client = _client()
    forecasts = await client.forecasts(start, end, publish_from, publish_to)
    actuals = [] if mode == "live" else await client.actuals(start, end)
    selected = select_forecasts(forecasts, mode, cutoff_clock, now if mode == "live" else vintage_time.astimezone(timezone.utc) if vintage_time else None)
    periods = serialise_periods(actuals, selected, start, end)
    products = product_rows(actuals, selected, start, end, auction_definition)
    statuses = ("matched", "source_allocated", "forecast_only", "actual_only", "missing")
    status_counts = {status: sum(1 for row in products if row["status"] == status) for status in statuses}
    labels = {"decision": "Decision-time forecast", "latest": "Retrospective latest forecast", "vintage": "Selected forecast vintage", "live": "Latest published forecast"}
    return {"window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}, "auction": auction_definition.serialise(), "selection": {"mode": mode, "label": labels[mode], "cutoff_time_utc": resolved_cutoff if mode == "decision" else None, "assumption": "Each product uses the latest source forecast published by its own day-before auction cutoff." if mode == "decision" else "This is a source-data display, not a procurement recommendation."}, "metrics": energy_metrics(products), "coverage": {"expected_products": len(products), **status_counts, **vintage_summary(forecasts)}, "products": products, "periods": periods, "daily": daily_summaries(products), "retrieved_at": iso(now)}


async def build_vintages(start_time: datetime, mode: str, cutoff_time: str, vintage_time: Optional[datetime]) -> Dict[str, Any]:
    source_target = start_time.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    now = datetime.now(timezone.utc)
    client = _client()
    forecasts = await client.forecasts(source_target, source_target + timedelta(hours=1), source_target - timedelta(days=7), now)
    rows = sorted((forecast for forecast in forecasts if forecast.start_time == source_target), key=lambda value: value.publish_time)
    cutoff_clock = datetime.strptime(cutoff_time, "%H:%M").time()
    selected = select_forecasts(rows, mode, cutoff_clock, vintage_time.astimezone(timezone.utc) if vintage_time else now if mode == "live" else None)
    decision_cutoff = selection_cutoff(source_target, cutoff_clock)

    def eligibility(row: Forecast) -> str:
        if row.publish_time > source_target:
            return "published_after_delivery"
        if mode == "decision" and row.publish_time > decision_cutoff:
            return "available_after_cutoff"
        return "eligible"

    return {"source_interval_start": iso(source_target), "decision_cutoff": iso(decision_cutoff) if mode == "decision" else None, "vintages": [{"publish_time": iso(row.publish_time), "generation_mw": row.generation_mw, "eligibility": eligibility(row), "selected": selected.get(source_target) == row} for row in rows]}
