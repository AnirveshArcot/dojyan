"""Forecast-vintage selection and accuracy calculations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from math import sqrt

from .elexon import Actual, Forecast


@dataclass(frozen=True)
class MatchedPeriod:
    start_time: datetime
    actual_mw: float
    forecast_mw: float
    publish_time: datetime

    @property
    def error_mw(self) -> float:
        """Return signed source-resolution error as forecast MW minus actual MW."""
        return self.forecast_mw - self.actual_mw


def select_latest_available(forecasts: list[Forecast], cutoff: datetime) -> dict[datetime, Forecast]:
    """Select the newest forecast published on or before one absolute cutoff.

    This utility applies the same cutoff to all supplied forecasts.
    When publication timestamps tie, the higher MW value wins to make selection
    deterministic rather than dependent on upstream response order.
    """
    selected: dict[datetime, Forecast] = {}
    for forecast in forecasts:
        if forecast.publish_time > cutoff:
            continue
        existing = selected.get(forecast.start_time)
        if existing is None or forecast.publish_time > existing.publish_time or (
            forecast.publish_time == existing.publish_time and forecast.generation_mw > existing.generation_mw
        ):
            selected[forecast.start_time] = forecast
    return selected


def selection_cutoff(delivery_time: datetime, cutoff_time: time | int) -> datetime:
    """Return the UTC day-before cutoff for one delivery timestamp.

    The day-ahead decision is made on the calendar day preceding delivery.
    An integer cutoff is retained for backward-compatible whole-hour requests.
    """
    delivery_day = delivery_time.astimezone(timezone.utc).date()
    cutoff_clock = time(cutoff_time) if isinstance(cutoff_time, int) else cutoff_time
    return datetime.combine(delivery_day - timedelta(days=1), cutoff_clock, tzinfo=timezone.utc)


def select_forecasts(forecasts: list[Forecast], mode: str, cutoff_time: time | int, vintage_time: datetime | None = None) -> dict[datetime, Forecast]:
    """Select one deterministic source forecast per delivery hour for a mode.

    ``decision`` selects the latest record available by each hour's day-before
    cutoff, while ``latest`` selects the newest record published before delivery.
    ``vintage`` and ``live`` select records available no later than the supplied
    reference timestamp.

    No forecast value is calculated or altered by this function.
    """
    selected: dict[datetime, Forecast] = {}
    for forecast in forecasts:
        if mode == "decision":
            eligible = forecast.publish_time <= selection_cutoff(forecast.start_time, cutoff_time)
        elif mode == "latest":
            eligible = forecast.publish_time <= forecast.start_time
        elif mode in {"vintage", "live"}:
            eligible = vintage_time is not None and forecast.publish_time <= vintage_time
        else:
            raise ValueError("Unknown forecast selection mode.")
        if not eligible:
            continue
        existing = selected.get(forecast.start_time)
        if existing is None or forecast.publish_time > existing.publish_time or (
            forecast.publish_time == existing.publish_time and forecast.generation_mw > existing.generation_mw
        ):
            selected[forecast.start_time] = forecast
    return selected


def match_periods(actuals: list[Actual], forecasts: dict[datetime, Forecast]) -> list[MatchedPeriod]:
    """Pair exact source timestamps that have both actual and selected forecast MW.

    This legacy source-resolution helper does not allocate hourly forecasts into
    30-minute products.
    The auction-aware equivalent is ``product_rows``.
    """
    matched: list[MatchedPeriod] = []
    for actual in actuals:
        forecast = forecasts.get(actual.start_time)
        if forecast:
            matched.append(MatchedPeriod(actual.start_time, actual.generation_mw, forecast.generation_mw, forecast.publish_time))
    return matched


def calculate_metrics(periods: list[MatchedPeriod]) -> dict[str, float | int | None]:
    """Calculate legacy MW accuracy metrics for exact source-resolution matches.

    Product-facing dashboard metrics use MWh in ``energy_metrics`` instead.
    This function remains available for source-level analysis and tests.
    """
    if not periods:
        return {"matched_periods": 0, "mae_mw": None, "rmse_mw": None, "bias_mw": None, "wape_percent": None}
    errors = [period.error_mw for period in periods]
    actual_total = sum(abs(period.actual_mw) for period in periods)
    absolute_error_total = sum(abs(error) for error in errors)
    return {
        "matched_periods": len(periods),
        "mae_mw": round(absolute_error_total / len(errors), 1),
        "rmse_mw": round(sqrt(sum(error * error for error in errors) / len(errors)), 1),
        "bias_mw": round(sum(errors) / len(errors), 1),
        "wape_percent": round(absolute_error_total / actual_total * 100, 1) if actual_total else None,
    }


def vintage_summary(forecasts: list[Forecast]) -> dict[str, int]:
    """Count source forecast records and distinct delivery hours with vintages.

    The counts describe data coverage only and do not imply that every vintage
    passed the selected auction cutoff.
    """
    periods = defaultdict(set)
    for forecast in forecasts:
        periods[forecast.start_time].add(forecast.publish_time)
    return {"forecast_records": len(forecasts), "delivery_periods_with_vintages": len(periods)}
