from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class MissingDataAction(str, Enum):
    EMIT_NONE = "emit_none"
    CARRY_FORWARD = "carry_forward"
    SKIP_SNAPSHOT = "skip_snapshot"
    RAISE = "raise"


@dataclass(slots=True)
class MissingDataPolicy:
    action: MissingDataAction = MissingDataAction.EMIT_NONE
    stale_after_ns: int = 5 * 60 * 1_000_000_000
    allow_partial_cross_asset: bool = True

    def handle_missing(self, previous_value: object | None = None) -> object | None:
        if self.action == MissingDataAction.CARRY_FORWARD:
            return previous_value
        if self.action == MissingDataAction.RAISE:
            raise ValueError("Missing data encountered under strict policy.")
        return None

    def should_skip_snapshot(self, missing_count: int) -> bool:
        return missing_count > 0 and self.action == MissingDataAction.SKIP_SNAPSHOT

    def is_stale(self, latest_event_ns: int, current_event_ns: int) -> bool:
        return current_event_ns - latest_event_ns > self.stale_after_ns


@dataclass(slots=True)
class WarmupManager:
    def feature_ready(self, feature: object, state: dict) -> bool:
        return bool(feature.ready(state))

    def warmup_complete(self, features: Iterable[object], states: Iterable[dict]) -> bool:
        return all(feature.ready(state) for feature, state in zip(features, states))


@dataclass(slots=True)
class FeatureVersionManager:
    prefix: str = "fe"
    separator: str = "|"
    pair_separator: str = "@"
    cached: str | None = field(default=None, init=False)

    def resolve(self, features: Iterable[object]) -> str:
        pairs = sorted(f"{feature.name}{self.pair_separator}{feature.version}" for feature in features)
        self.cached = f"{self.prefix}{self.separator}" + self.separator.join(pairs)
        return self.cached

