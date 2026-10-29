from app.elexon import parse_actuals, parse_forecasts


def test_parsers_filter_invalid_and_non_wind_records() -> None:
    actuals = parse_actuals([
        {"fuelType": "WIND", "startTime": "2026-01-20T00:00:00Z", "generation": 1234},
        {"fuelType": "GAS", "startTime": "2026-01-20T00:00:00Z", "generation": 4000},
        {"fuelType": "WIND", "generation": 10},
    ])
    forecasts = parse_forecasts([
        {"startTime": "2026-01-20T00:00:00Z", "publishTime": "2026-01-19T12:00:00Z", "generation": 1200},
        {"startTime": "bad", "publishTime": "2026-01-19T12:00:00Z", "generation": 1200},
    ])
    assert len(actuals) == 1
    assert len(forecasts) == 1

