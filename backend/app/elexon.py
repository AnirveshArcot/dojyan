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
    """Parse an Elexon ISO timestamp into a timezone-aware UTC datetime.

    The source can use either a trailing ``Z`` or an explicit offset.
    Normalising both forms to UTC makes interval comparisons deterministic.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def unwrap_records(payload: Any) -> list[dict[str, Any]]:
    """Extract dictionary records from supported Elexon response shapes.

    BMRS stream responses are normally arrays, but accepted wrapper keys allow
    the client to tolerate common API envelope variations.
    Invalid shapes raise ``ElexonError`` rather than silently producing an empty
    analysis.
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "records"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    raise ElexonError("Elexon returned an unexpected response shape.")


def parse_actuals(records: list[dict[str, Any]]) -> list[Actual]:
    """Parse FUELHH records into one latest valid WIND actual per half-hour.

    Non-wind fuels and malformed records are excluded.
    If Elexon supplies multiple valid publications for an interval, the newest
    publication is retained so actual availability remains auditable.
    """
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
    """Parse valid WINDFOR records while preserving every publication vintage.

    Unlike actuals, forecast records are not deduplicated because the history of
    successive publish times is required for cutoff selection and vintage audit.
    """
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
        """Create an Elexon client with an optional injected response cache.

        Tests can inject an isolated cache.
        Normal application use creates the server-side cache from environment
        configuration when one is not supplied.
        """
        self.base_url = base_url.rstrip("/")
        self.cache = cache or DiskResponseCache.from_environment()

    async def _get_dataset(self, dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
        """Fetch one BMRS stream dataset through the persistent response cache.

        The URL and sorted query parameters form the cache key, so equivalent
        requests share a response irrespective of parameter insertion order.
        HTTP, JSON, and incompatible-shape errors are normalised to
        ``ElexonError`` for consistent route-level error handling.
        """
        async def fetch() -> list[dict[str, Any]]:
            """Perform the uncached HTTP request and validate its response shape."""
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
        """Fetch FUELHH WIND actuals for an exclusive UTC delivery window.

        FUELHH accepts calendar settlement dates, so the end date is converted
        from an exclusive timestamp to the final included date before querying.
        The returned records are then precisely filtered by timestamps.
        """
        records = await self._get_dataset(
            "FUELHH",
            {
                "settlementDateFrom": start.date().isoformat(),
                "settlementDateTo": (end - timedelta(microseconds=1)).date().isoformat(),
            },
        )
        return [actual for actual in parse_actuals(records) if start <= actual.start_time < end]

    async def forecasts(self, start: datetime, end: datetime, publish_from: datetime, publish_to: datetime) -> list[Forecast]:
        """Fetch WINDFOR publications and retain only target delivery hours.

        WINDFOR is queried by publication range because a delivery hour has many
        forecast vintages.
        The final delivery-window filter separates source query scope from the
        actual products being evaluated.
        """
        records = await self._get_dataset(
            "WINDFOR",
            {
                "publishDateTimeFrom": publish_from.isoformat().replace("+00:00", "Z"),
                "publishDateTimeTo": publish_to.isoformat().replace("+00:00", "Z"),
            },
        )
        return [forecast for forecast in parse_forecasts(records) if start <= forecast.start_time < end]
