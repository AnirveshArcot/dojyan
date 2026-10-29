"""Energy-based product metrics and day summaries."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from math import sqrt
from typing import Any, Dict, List


def energy_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    comparable = [row for row in rows if row["status"] in {"matched", "source_allocated"}]
    forecast_total = sum(row["forecast_mwh"] for row in rows if row["forecast_mwh"] is not None)
    actual_total = sum(row["actual_mwh"] for row in rows if row["actual_mwh"] is not None)
    if not comparable:
        return {"matched_products": 0, "forecast_energy_mwh": round(forecast_total, 1) if forecast_total else None, "actual_energy_mwh": round(actual_total, 1) if actual_total else None, "signed_error_mwh": None, "absolute_error_mwh": None, "mae_mwh": None, "rmse_mwh": None, "bias_mwh": None, "wape_percent": None}
    errors = [row["signed_error_mwh"] for row in comparable]
    absolute_total = sum(abs(error) for error in errors)
    actual_total = sum(row["actual_mwh"] for row in comparable)
    return {"matched_products": len(comparable), "forecast_energy_mwh": round(sum(row["forecast_mwh"] for row in comparable), 1), "actual_energy_mwh": round(actual_total, 1), "signed_error_mwh": round(sum(errors), 1), "absolute_error_mwh": round(absolute_total, 1), "mae_mwh": round(absolute_total / len(errors), 1), "rmse_mwh": round(sqrt(sum(error * error for error in errors) / len(errors)), 1), "bias_mwh": round(sum(errors) / len(errors), 1), "wape_percent": round(absolute_total / actual_total * 100, 1) if actual_total else None}


def daily_summaries(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[date, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[datetime.fromisoformat(row["start_time"].replace("Z", "+00:00")).date()].append(row)
    return [{"date": day.isoformat(), **energy_metrics(day_rows)} for day, day_rows in sorted(grouped.items())]
