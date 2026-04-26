from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(slots=True)
class MetricsBook:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latencies_ns: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))

    def incr(self, key: str, amount: int = 1) -> None:
        self.counters[key] += amount

    def observe_ns(self, key: str, value: int) -> None:
        self.latencies_ns[key].append(value)


@dataclass(slots=True)
class FeatureEngineObserver:
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("aphelion.feature_engine"))
    metrics: MetricsBook = field(default_factory=MetricsBook)

    def record_feature_latency(self, feature_name: str, latency_ns: int) -> None:
        self.metrics.observe_ns(f"feature_latency_ns.{feature_name}", latency_ns)

    def record_snapshot_emission(self, symbol: str, timeframe: str) -> None:
        self.metrics.incr(f"snapshot_emitted.{symbol}.{timeframe}")

    def record_missing(self, feature_name: str) -> None:
        self.metrics.incr(f"missing_data.{feature_name}")

    def record_error(self, feature_name: str) -> None:
        self.metrics.incr(f"errors.{feature_name}")

    def warn_stale_feed(self, symbol: str, timeframe: str, current_event_ns: int, latest_event_ns: int) -> None:
        self.metrics.incr(f"stale_feed.{symbol}.{timeframe}")
        self.logger.warning(
            "stale_feed symbol=%s timeframe=%s current_event_ns=%s latest_event_ns=%s",
            symbol,
            timeframe,
            current_event_ns,
            latest_event_ns,
        )

