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
    """Run small filesystem operations without blocking the API event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(function, *args))


class DiskResponseCache:
    """Cache JSON response records on disk with fresh and stale lifetimes."""

    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, directory: str | Path, ttl_seconds: int = 21_600, stale_ttl_seconds: int = 86_400, enabled: bool = True) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self.enabled = enabled

    @classmethod
    def from_environment(cls) -> "DiskResponseCache":
        return cls(
            directory=os.getenv("ELEXON_CACHE_DIR", "/tmp/winddesk-elexon-cache"),
            ttl_seconds=int(os.getenv("ELEXON_CACHE_TTL_SECONDS", "21600")),
            stale_ttl_seconds=int(os.getenv("ELEXON_CACHE_STALE_TTL_SECONDS", "86400")),
            enabled=os.getenv("ELEXON_CACHE_ENABLED", "true").lower() not in {"0", "false", "no"},
        )

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def _read(self, key: str) -> tuple[float, Records] | None:
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
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"created_at": time.time(), "records": records}, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)

    async def get_or_fetch(self, key: str, fetcher: Fetcher) -> Records:
        """Return a fresh entry, otherwise refresh it and use bounded stale data on outage."""
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
