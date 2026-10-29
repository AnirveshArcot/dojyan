from datetime import datetime, time, timezone

from app.analysis import calculate_metrics, match_periods, select_forecasts, select_latest_available
from app.elexon import Actual, Forecast


def timestamp(hour: int) -> datetime:
    return datetime(2026, 1, 20, hour, tzinfo=timezone.utc)


def test_selects_newest_forecast_before_cutoff() -> None:
    forecasts = [
        Forecast(timestamp(1), timestamp(0), 100.0),
        Forecast(timestamp(1), timestamp(2), 200.0),
        Forecast(timestamp(1), timestamp(3), 300.0),
    ]
    selected = select_latest_available(forecasts, timestamp(2))
    assert selected[timestamp(1)].generation_mw == 200.0


def test_decision_mode_uses_each_delivery_days_cutoff() -> None:
    next_day = datetime(2026, 1, 21, 1, tzinfo=timezone.utc)
    forecasts = [
        Forecast(timestamp(1), datetime(2026, 1, 19, 12, tzinfo=timezone.utc), 100.0),
        Forecast(timestamp(1), datetime(2026, 1, 19, 13, tzinfo=timezone.utc), 200.0),
        Forecast(next_day, datetime(2026, 1, 20, 12, tzinfo=timezone.utc), 300.0),
    ]
    selected = select_forecasts(forecasts, "decision", 12)
    assert selected[timestamp(1)].generation_mw == 100.0
    assert selected[next_day].generation_mw == 300.0


def test_decision_mode_supports_minute_precise_cutoffs() -> None:
    next_day = datetime(2026, 1, 21, 1, tzinfo=timezone.utc)
    forecasts = [
        Forecast(next_day, datetime(2026, 1, 20, 9, 20, tzinfo=timezone.utc), 100.0),
        Forecast(next_day, datetime(2026, 1, 20, 9, 21, tzinfo=timezone.utc), 200.0),
    ]
    selected = select_forecasts(forecasts, "decision", time(9, 20))
    assert selected[next_day].generation_mw == 100.0


def test_matches_and_calculates_metrics() -> None:
    actuals = [Actual(timestamp(1), 100.0), Actual(timestamp(2), 200.0)]
    forecasts = {timestamp(1): Forecast(timestamp(1), timestamp(0), 120.0), timestamp(2): Forecast(timestamp(2), timestamp(0), 160.0)}
    metrics = calculate_metrics(match_periods(actuals, forecasts))
    assert metrics == {"matched_periods": 2, "mae_mw": 30.0, "rmse_mw": 31.6, "bias_mw": -10.0, "wape_percent": 20.0}


def test_empty_metrics_are_explicit() -> None:
    assert calculate_metrics([])["mae_mw"] is None
