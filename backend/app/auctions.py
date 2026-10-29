"""Declared day-ahead auction product contracts used by the dashboard.

These definitions choose how already-published WINDFOR values are displayed.
They do not create a new forecast or infer a trading recommendation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import time
from typing import Dict


@dataclass(frozen=True)
class Auction:
    identifier: str
    label: str
    cutoff_time_utc: time
    product_minutes: int

    def serialise(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["cutoff_time_utc"] = self.cutoff_time_utc.strftime("%H:%M")
        return payload


AUCTIONS: Dict[str, Auction] = {
    "epex_60": Auction("epex_60", "EPEX SPOT GB DAY-AHEAD 60 MIN", time(9, 20), 60),
    "n2ex_60": Auction("n2ex_60", "N2EX DAY-AHEAD 60 MIN", time(9, 50), 60),
    "epex_30": Auction("epex_30", "EPEX SPOT GB DAY-AHEAD 30 MIN", time(15, 30), 30),
}


def get_auction(identifier: str) -> Auction:
    try:
        return AUCTIONS[identifier]
    except KeyError as exc:
        raise ValueError("Unknown auction.") from exc
