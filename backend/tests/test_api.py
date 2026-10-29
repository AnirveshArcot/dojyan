from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.elexon import Actual, Forecast
from app.main import app


def utc(day: int, hour: int) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def test_analysis_returns_an_operational_view(monkeypatch) -> None:
    async def fake_actuals(self, start, end):
        return [Actual(utc(20, 0), 100.0), Actual(utc(20, 1), 200.0)]

    async def fake_forecasts(self, start, end, publish_from, publish_to):
        return [
            Forecast(utc(20, 0), utc(19, 0), 120.0),
            Forecast(utc(20, 0), utc(18, 0), 90.0),
            Forecast(utc(20, 1), utc(19, 0), 160.0),
        ]

    monkeypatch.setattr("app.main.ElexonClient.actuals", fake_actuals)
    monkeypatch.setattr("app.main.ElexonClient.forecasts", fake_forecasts)

    response = TestClient(app).get("/api/analysis?start_date=2026-01-20&end_date=2026-01-20&cutoff_hour=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["mae_mw"] == 30.0
    assert payload["metrics"]["matched_periods"] == 2
    assert payload["periods"][0]["forecast_mw"] == 120.0
    assert payload["coverage"]["expected_periods"] == 48
    assert payload["selection"]["mode"] == "decision"


def test_analysis_rejects_dates_outside_the_pilot() -> None:
    response = TestClient(app).get("/api/analysis?start_date=2026-02-01&end_date=2026-02-01")
    assert response.status_code == 422
    assert "January 2026" in response.json()["detail"]
