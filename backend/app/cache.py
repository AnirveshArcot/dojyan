"""Small persistent cache for upstream Elexon dataset responses."""

from __future__ import annotations

import asyncio
from functools import partial
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Awaitable, Callable, Dict, List


Records = List[Dict[str, object]]
Fetcher = Callable[[], Awaitable[Records]]


async def run_blocking(function: Callable[..., object], *args: object) -> object:
    """Run a synchronous filesystem operation outside FastAPI's event loop.

    Cache reads and writes use standard file APIs.
    Moving those small operations to the default executor prevents one cache
    operation from delaying unrelated asynchronous Elexon requests.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(function, *args))


class DiskResponseCache:
    """Cache JSON response records on disk with fresh and stale lifetimes."""

    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, directory: str | Path, ttl_seconds: int = 21_600, stale_ttl_seconds: int = 86_400, enabled: bool = True) -> None:
        """Initialise cache location and fresh and stale lifetime policy.

        A record is fresh for ``ttl_seconds``.
        If an upstream request fails, it can still be served for the additional
        ``stale_ttl_seconds`` to keep historical analysis available during a
        temporary Elexon outage.
        """
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self.enabled = enabled

    @classmethod
    def from_environment(cls) -> "DiskResponseCache":
        """Create a cache from deploy-time environment variables.

        This centralises cache configuration so routes and Elexon clients do not
        need to know file paths, expiry policy, or the disable switch.
        """
        return cls(
            directory=os.getenv("ELEXON_CACHE_DIR", "/tmp/winddesk-elexon-cache"),
            ttl_seconds=int(os.getenv("ELEXON_CACHE_TTL_SECONDS", "21600")),
            stale_ttl_seconds=int(os.getenv("ELEXON_CACHE_STALE_TTL_SECONDS", "86400")),
            enabled=os.getenv("ELEXON_CACHE_ENABLED", "true").lower() not in {"0", "false", "no"},
        )

    def _path(self, key: str) -> Path:
        """Map an upstream request key to a filesystem-safe, stable cache path.

        SHA-256 avoids unsafe URL characters and keeps query parameters out of
        filenames while ensuring the same request always addresses the same file.
        """
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def _read(self, key: str) -> tuple[float, Records] | None:
        """Read and validate one cached response, returning no value if unusable.

        Corrupt, incomplete, or absent cache files are treated as misses.
        This makes cache recovery safe without exposing malformed cached JSON to
        the data parsing pipeline.
        """
        path = self._path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            created_at = float(payload["created_at"])
            records = payload["records"]
            if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
                return None
            return created_at, records
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write(self, key: str, records: Records) -> None:
        """Persist records atomically with the time at which they were fetched.

        The temporary-file replacement prevents a reader from observing a
        partially written JSON document if a process stops during a write.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"created_at": time.time(), "records": records}, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)

    async def get_or_fetch(self, key: str, fetcher: Fetcher) -> Records:
        """Return fresh data, fetch a replacement, or use bounded stale data.

        A per-key async lock prevents concurrent requests from causing a cache
        stampede against Elexon when the same entry expires.
        If refresh fails, stale data is returned only within its explicit maximum
        lifetime. Beyond that point the upstream error is propagated.
        """
        if not self.enabled:
            return await fetcher()

        cached = await run_blocking(self._read, key)
        now = time.time()
        if cached and now - cached[0] <= self.ttl_seconds:
            return cached[1]

        lock = self._locks.setdefault(str(self._path(key)), asyncio.Lock())
        async with lock:
            cached = await run_blocking(self._read, key)
            now = time.time()
            if cached and now - cached[0] <= self.ttl_seconds:
                return cached[1]
            try:
                records = await fetcher()
            except Exception:
                if cached and now - cached[0] <= self.ttl_seconds + self.stale_ttl_seconds:
                    return cached[1]
                raise
            await run_blocking(self._write, key, records)
            return records
