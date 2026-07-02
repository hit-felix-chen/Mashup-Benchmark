from __future__ import annotations

from typing import Any

from eval.config import weights_from_config

METRICS = ["IF", "BCS", "AEC", "VQ", "TC", "NC", "OQ"]
LIKERT_METRICS = {"IF", "VQ", "TC", "NC", "OQ"}


def normalize_score_for_quality(metric: str, value: float | int | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if metric in LIKERT_METRICS:
        likert = max(1.0, min(5.0, value))
        return (likert - 1.0) / 4.0 * 100.0
    return value


def compute_quality(scores: dict[str, float | None], config: dict[str, Any]) -> float | None:
    weights = weights_from_config(config)
    available = {
        metric: normalize_score_for_quality(metric, scores.get(metric))
        for metric in METRICS
        if scores.get(metric) is not None
    }
    if not available:
        return None
    weight_sum = sum(weights[m] for m in available)
    if weight_sum <= 0:
        return None
    return sum(float(available[m]) * weights[m] for m in available) / weight_sum


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = METRICS + ["Quality"]
    summary: dict[str, Any] = {"num_records": len(records), "metrics": {}}
    for metric in metric_names:
        values = [r.get("scores", {}).get(metric) for r in records]
        values = [float(v) for v in values if v is not None]
        if values:
            summary["metrics"][metric] = {
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }
        else:
            summary["metrics"][metric] = {"mean": None, "min": None, "max": None, "count": 0}
    costs = [r.get("cost", {}).get("api_cost_usd") for r in records]
    costs = [float(v) for v in costs if v is not None]
    latencies = [r.get("efficiency", {}).get("wall_clock_sec") for r in records]
    latencies = [float(v) for v in latencies if v is not None]
    summary["efficiency"] = {
        "total_api_cost_usd": sum(costs) if costs else None,
        "mean_wall_clock_sec": sum(latencies) / len(latencies) if latencies else None,
    }
    return summary
