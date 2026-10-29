"""Small, defensive client for Elexon's public BMRS datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from .cache import DiskResponseCache


class ElexonError(RuntimeError):
    """Raised when the upstream Elexon API cannot provide usable data."""


@dataclass(frozen=True)
class Actual:
    start_time: datetime
    generation_mw: float
    publish_time: Optional[datetime] = None


@dataclass(frozen=True)
class Forecast:
    start_time: datetime
    publish_time: datetime
    generation_mw: float


def parse_timestamp(value: str) -> datetime:
    """Parse Elexon's ISO timestamps into timezone-aware UTC datetimes."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def unwrap_records(payload: Any) -> list[dict[str, Any]]:
    """Accept both the stream array and common wrapped API response shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "records"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    raise ElexonError("Elexon returned an unexpected response shape.")


def parse_actuals(records: list[dict[str, Any]]) -> list[Actual]:
    latest_by_time: dict[datetime, Actual] = {}
    for record in records:
        if str(record.get("fuelType", "")).upper() != "WIND":
            continue
        try:
            actual = Actual(
                parse_timestamp(str(record["startTime"])),
                float(record["generation"]),
                parse_timestamp(str(record["publishTime"])) if record.get("publishTime") else None,
            )
        except (KeyError, TypeError, ValueError):
            continue
        existing = latest_by_time.get(actual.start_time)
        if existing is None or (actual.publish_time and (existing.publish_time is None or actual.publish_time > existing.publish_time)):
            latest_by_time[actual.start_time] = actual
    return sorted(latest_by_time.values(), key=lambda value: value.start_time)


def parse_forecasts(records: list[dict[str, Any]]) -> list[Forecast]:
    forecasts: list[Forecast] = []
    for record in records:
        try:
            forecasts.append(
                Forecast(
                    start_time=parse_timestamp(str(record["startTime"])),
                    publish_time=parse_timestamp(str(record["publishTime"])),
                    generation_mw=float(record["generation"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return forecasts


class ElexonClient:
    def __init__(self, base_url: str, cache: DiskResponseCache | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache = cache or DiskResponseCache.from_environment()

    async def _get_dataset(self, dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(f"{self.base_url}/datasets/{dataset}/stream", params=params)
                    response.raise_for_status()
                    return unwrap_records(response.json())
            except (httpx.HTTPError, ValueError, ElexonError) as exc:
                if isinstance(exc, ElexonError):
                    raise
                raise ElexonError("Could not retrieve data from Elexon.") from exc

        cache_key = f"{self.base_url}/datasets/{dataset}/stream?{urlencode(sorted(params.items()))}"
        return await self.cache.get_or_fetch(cache_key, fetch)

    async def actuals(self, start: datetime, end: datetime) -> list[Actual]:
        """Fetch actuals with FUELHH's settlement-date query contract."""
        records = await self._get_dataset(
            "FUELHH",
            {
                "settlementDateFrom": start.date().isoformat(),
                "settlementDateTo": (end - timedelta(microseconds=1)).date().isoformat(),
            },
        )
        return [actual for actual in parse_actuals(records) if start <= actual.start_time < end]

    async def forecasts(self, start: datetime, end: datetime, publish_from: datetime, publish_to: datetime) -> list[Forecast]:
        """Fetch forecast vintages by publication time and retain the target delivery window."""
        records = await self._get_dataset(
            "WINDFOR",
            {
                "publishDateTimeFrom": publish_from.isoformat().replace("+00:00", "Z"),
                "publishDateTimeTo": publish_to.isoformat().replace("+00:00", "Z"),
            },
        )
        return [forecast for forecast in parse_forecasts(records) if start <= forecast.start_time < end]
