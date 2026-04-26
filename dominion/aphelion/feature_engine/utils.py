from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def sign(value: float, tolerance: float = 0.0) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return sum((value - avg) ** 2 for value in values) / (len(values) - 1)


def stddev(values: Sequence[float]) -> float:
    return math.sqrt(max(variance(values), 0.0))


def covariance(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mx = mean(xs)
    my = mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) - 1)


def correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    denom = stddev(xs) * stddev(ys)
    return safe_div(covariance(xs, ys), denom)


def log_return(current: float, previous: float) -> float:
    if current <= 0 or previous <= 0:
        return 0.0
    return math.log(current / previous)


def ewma(previous: float, value: float, alpha: float) -> float:
    return alpha * value + (1.0 - alpha) * previous


def shannon_entropy(symbols: Iterable[int]) -> float:
    counts: dict[int, int] = {}
    total = 0
    for item in symbols:
        counts[item] = counts.get(item, 0) + 1
        total += 1
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log(probability)
    return entropy


def normalized_entropy(symbols: Sequence[int], alphabet_size: int) -> float:
    if alphabet_size <= 1:
        return 0.0
    entropy = shannon_entropy(symbols)
    return safe_div(entropy, math.log(alphabet_size))


def ns_to_datetime(ts_event_ns: int, tz: timezone = timezone.utc) -> datetime:
    return datetime.fromtimestamp(ts_event_ns / 1_000_000_000, tz=tz)


def recursive_serialize(value: Any) -> Any:
    if isinstance(value, deque):
        return {"__deque__": list(value), "maxlen": value.maxlen}
    if isinstance(value, tuple):
        return {"__tuple__": [recursive_serialize(item) for item in value]}
    if is_dataclass(value):
        return recursive_serialize(asdict(value))
    if isinstance(value, dict):
        return {str(key): recursive_serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [recursive_serialize(item) for item in value]
    return value


def recursive_restore(value: Any) -> Any:
    if isinstance(value, dict):
        if "__deque__" in value:
            return deque((recursive_restore(item) for item in value["__deque__"]), maxlen=value["maxlen"])
        if "__tuple__" in value:
            return tuple(recursive_restore(item) for item in value["__tuple__"])
        return {key: recursive_restore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [recursive_restore(item) for item in value]
    return value


def ensure_json_serializable(value: Any) -> Any:
    encoded = json.dumps(value, allow_nan=False)
    return json.loads(encoded)


class RollingWindow:
    def __init__(self, maxlen: int):
        self.values: deque[float] = deque(maxlen=maxlen)

    def append(self, value: float) -> None:
        self.values.append(value)

    def to_list(self) -> list[float]:
        return list(self.values)

    @property
    def ready(self) -> bool:
        return len(self.values) == self.values.maxlen

    def mean(self) -> float:
        return mean(self.values)

    def std(self) -> float:
        return stddev(self.to_list())


class WeightedRunningStats:
    def __init__(self) -> None:
        self.weight = 0.0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, value: float, weight: float) -> None:
        if weight <= 0:
            return
        total_weight = self.weight + weight
        delta = value - self.mean
        next_mean = self.mean + (weight / total_weight) * delta
        self.m2 += weight * delta * (value - next_mean)
        self.mean = next_mean
        self.weight = total_weight

    def variance(self) -> float:
        return safe_div(self.m2, self.weight)

    def std(self) -> float:
        return math.sqrt(max(self.variance(), 0.0))

