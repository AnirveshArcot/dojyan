from __future__ import annotations

import asyncio

from app.cache import DiskResponseCache
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


def test_disk_cache_reuses_fresh_response_and_serves_stale_on_error(tmp_path) -> None:
    calls = 0

    async def fetch() -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return [{"startTime": "2026-01-20T00:00:00Z"}]

    async def unavailable() -> list[dict[str, object]]:
        raise RuntimeError("upstream unavailable")

    async def scenario() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
        fresh_cache = DiskResponseCache(tmp_path, ttl_seconds=60, stale_ttl_seconds=60)
        first = await fresh_cache.get_or_fetch("fuelhh-january", fetch)
        second = await fresh_cache.get_or_fetch("fuelhh-january", fetch)
        stale_cache = DiskResponseCache(tmp_path, ttl_seconds=0, stale_ttl_seconds=60)
        stale = await stale_cache.get_or_fetch("fuelhh-january", unavailable)
        return first, second, stale

    first, second, stale = asyncio.run(scenario())
    assert first == second == stale
    assert calls == 1
