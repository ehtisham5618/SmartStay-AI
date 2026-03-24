"""Dependency-free evaluation metrics and summary statistics."""

from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def precision_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    return safe_divide(sum(item in relevant for item in retrieved[:k]), k)


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    return safe_divide(sum(item in relevant for item in retrieved[:k]), len(relevant))


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def confidence_interval_95(values: Sequence[float]) -> list[float]:
    if not values:
        return [0.0, 0.0]
    mean = statistics.mean(values)
    if len(values) == 1:
        return [mean, mean]
    margin = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return [mean - margin, mean + margin]


def summarize(values: Iterable[float]) -> dict:
    data = [float(value) for value in values]
    if not data:
        return {key: 0.0 for key in ("count", "mean", "median", "p90", "p99", "min", "max")}
    low, high = confidence_interval_95(data)
    return {
        "count": len(data),
        "mean": statistics.mean(data),
        "median": statistics.median(data),
        "p90": percentile(data, 90),
        "p99": percentile(data, 99),
        "min": min(data),
        "max": max(data),
        "mean_ci95": [low, high],
    }
