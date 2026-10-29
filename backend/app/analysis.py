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
        return self.forecast_mw - self.actual_mw


def select_latest_available(forecasts: list[Forecast], cutoff: datetime) -> dict[datetime, Forecast]:
    """Select the newest forecast published on or before the configured cutoff."""
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
    """Return the explicit day-ahead cutoff for a delivery period."""
    delivery_day = delivery_time.astimezone(timezone.utc).date()
    cutoff_clock = time(cutoff_time) if isinstance(cutoff_time, int) else cutoff_time
    return datetime.combine(delivery_day - timedelta(days=1), cutoff_clock, tzinfo=timezone.utc)


def select_forecasts(forecasts: list[Forecast], mode: str, cutoff_time: time | int, vintage_time: datetime | None = None) -> dict[datetime, Forecast]:
    """Select one auditable forecast per delivery period for the requested analysis mode."""
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
    matched: list[MatchedPeriod] = []
    for actual in actuals:
        forecast = forecasts.get(actual.start_time)
        if forecast:
            matched.append(MatchedPeriod(actual.start_time, actual.generation_mw, forecast.generation_mw, forecast.publish_time))
    return matched


def calculate_metrics(periods: list[MatchedPeriod]) -> dict[str, float | int | None]:
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
    periods = defaultdict(set)
    for forecast in forecasts:
        periods[forecast.start_time].add(forecast.publish_time)
    return {"forecast_records": len(forecasts), "delivery_periods_with_vintages": len(periods)}
