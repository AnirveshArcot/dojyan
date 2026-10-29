from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.elexon import Actual, Forecast
from app.main import app


def utc(day: int, hour: int) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def test_analysis_returns_an_operational_view(monkeypatch) -> None:
    async def fake_actuals(self, start, end):
        return [
            Actual(utc(20, 0), 100.0),
            Actual(utc(20, 0).replace(minute=30), 100.0),
            Actual(utc(20, 1), 200.0),
            Actual(utc(20, 1).replace(minute=30), 200.0),
        ]

    async def fake_forecasts(self, start, end, publish_from, publish_to):
        return [
            Forecast(utc(20, 0), utc(19, 0), 120.0),
            Forecast(utc(20, 0), utc(18, 0), 90.0),
            Forecast(utc(20, 1), utc(19, 0), 160.0),
        ]

    monkeypatch.setattr("app.services.ElexonClient.actuals", fake_actuals)
    monkeypatch.setattr("app.services.ElexonClient.forecasts", fake_forecasts)

    response = TestClient(app).get("/api/analysis?start_date=2026-01-20&end_date=2026-01-20&cutoff_hour=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["mae_mwh"] == 30.0
    assert payload["metrics"]["matched_products"] == 2
    assert payload["metrics"]["signed_error_mwh"] == -20.0
    assert payload["periods"][0]["forecast_mw"] == 120.0
    assert payload["coverage"]["expected_products"] == 24
    assert payload["products"][0]["forecast_mwh"] == 120.0
    assert payload["selection"]["mode"] == "decision"


def test_openapi_document_is_exposed_under_api_prefix() -> None:
    response = TestClient(app).get("/api/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "WindDesk API"


def test_analysis_accepts_dates_outside_the_january_demo(monkeypatch) -> None:
    async def fake_actuals(self, start, end):
        return []

    async def fake_forecasts(self, start, end, publish_from, publish_to):
        return []

    monkeypatch.setattr("app.services.ElexonClient.actuals", fake_actuals)
    monkeypatch.setattr("app.services.ElexonClient.forecasts", fake_forecasts)
    response = TestClient(app).get("/api/analysis?start_date=2026-02-01&end_date=2026-02-01")
    assert response.status_code == 200


def test_epex_30_applies_hourly_source_rate_to_each_product(monkeypatch) -> None:
    async def fake_actuals(self, start, end):
        return [Actual(utc(20, 0), 100.0), Actual(utc(20, 0).replace(minute=30), 140.0)]

    async def fake_forecasts(self, start, end, publish_from, publish_to):
        return [Forecast(utc(20, 0), utc(19, 0), 120.0)]

    monkeypatch.setattr("app.services.ElexonClient.actuals", fake_actuals)
    monkeypatch.setattr("app.services.ElexonClient.forecasts", fake_forecasts)
    response = TestClient(app).get("/api/analysis?start_date=2026-01-20&end_date=2026-01-20&auction=epex_30")
    assert response.status_code == 200
    first, second = response.json()["products"][:2]
    assert first["forecast_mwh"] == second["forecast_mwh"] == 60.0
    assert first["forecast_source_resolution_minutes"] == 60
    assert first["status"] == second["status"] == "source_allocated"
