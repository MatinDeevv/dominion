from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .events import (
    BarCloseEvent,
    CrossAssetBarEvent,
    NewsEvent,
    SessionEvent,
    TickEvent,
    event_from_record,
)
from .utils import recursive_restore, recursive_serialize


@dataclass(frozen=True, slots=True)
class FeatureStateKey:
    feature_name: str
    symbol: str
    timeframe: str


@dataclass(slots=True)
class FeatureStateStore:
    feature_states: dict[FeatureStateKey, dict[str, Any]] = field(default_factory=dict)
    latest_ticks: dict[str, TickEvent] = field(default_factory=dict)
    latest_bars: dict[tuple[str, str], BarCloseEvent | CrossAssetBarEvent] = field(default_factory=dict)
    bars_by_timestamp: dict[tuple[str, int], dict[str, BarCloseEvent | CrossAssetBarEvent]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    sessions: dict[str, SessionEvent] = field(default_factory=dict)
    active_news: NewsEvent | None = None
    pending_snapshot_targets: set[tuple[str, str, int]] = field(default_factory=set)
    last_seq_no: int = 0

    def get_or_create(self, key: FeatureStateKey, factory: callable) -> dict[str, Any]:
        if key not in self.feature_states:
            self.feature_states[key] = factory()
        return self.feature_states[key]

    def update_tick(self, event: TickEvent) -> None:
        self.latest_ticks[event.symbol] = event
        self.last_seq_no = max(self.last_seq_no, event.seq_no)

    def update_bar(self, event: BarCloseEvent | CrossAssetBarEvent) -> None:
        self.latest_bars[(event.symbol, event.timeframe)] = event
        self.bars_by_timestamp[(event.timeframe, event.ts_event_ns)][event.symbol] = event
        self.last_seq_no = max(self.last_seq_no, event.seq_no)

    def update_session(self, event: SessionEvent) -> None:
        self.sessions[event.symbol] = event
        self.last_seq_no = max(self.last_seq_no, event.seq_no)

    def update_news(self, event: NewsEvent) -> None:
        self.active_news = event
        self.last_seq_no = max(self.last_seq_no, event.seq_no)

    def latest_tick(self, symbol: str) -> TickEvent | None:
        return self.latest_ticks.get(symbol)

    def latest_bar(self, symbol: str, timeframe: str) -> BarCloseEvent | CrossAssetBarEvent | None:
        return self.latest_bars.get((symbol, timeframe))

    def bars_for_timestamp(self, timeframe: str, ts_event_ns: int) -> dict[str, BarCloseEvent | CrossAssetBarEvent]:
        return dict(self.bars_by_timestamp.get((timeframe, ts_event_ns), {}))

    def add_pending_snapshot(self, symbol: str, timeframe: str, ts_event_ns: int) -> None:
        self.pending_snapshot_targets.add((symbol, timeframe, ts_event_ns))

    def remove_pending_snapshot(self, target: tuple[str, str, int]) -> None:
        self.pending_snapshot_targets.discard(target)

    def export(self, registry: object) -> dict[str, Any]:
        serialized_states: dict[str, Any] = {}
        for key, state in self.feature_states.items():
            serialized_key = f"{key.feature_name}|{key.symbol}|{key.timeframe}"
            serialized_states[serialized_key] = recursive_serialize(state)

        return {
            "feature_states": serialized_states,
            "latest_ticks": {symbol: event.to_record() for symbol, event in self.latest_ticks.items()},
            "latest_bars": {
                f"{symbol}|{timeframe}": event.to_record()
                for (symbol, timeframe), event in self.latest_bars.items()
            },
            "bars_by_timestamp": {
                f"{timeframe}|{ts_event_ns}": {symbol: event.to_record() for symbol, event in bars.items()}
                for (timeframe, ts_event_ns), bars in self.bars_by_timestamp.items()
            },
            "sessions": {symbol: event.to_record() for symbol, event in self.sessions.items()},
            "active_news": self.active_news.to_record() if self.active_news else None,
            "pending_snapshot_targets": list(self.pending_snapshot_targets),
            "last_seq_no": self.last_seq_no,
        }

    def restore(self, payload: dict[str, Any]) -> None:
        self.feature_states.clear()
        for serialized_key, state in payload.get("feature_states", {}).items():
            feature_name, symbol, timeframe = serialized_key.split("|", 2)
            self.feature_states[FeatureStateKey(feature_name, symbol, timeframe)] = recursive_restore(state)

        self.latest_ticks = {
            symbol: event_from_record(record) for symbol, record in payload.get("latest_ticks", {}).items()
        }
        self.latest_bars = {}
        for serialized_key, record in payload.get("latest_bars", {}).items():
            symbol, timeframe = serialized_key.split("|", 1)
            self.latest_bars[(symbol, timeframe)] = event_from_record(record)

        self.bars_by_timestamp = defaultdict(dict)
        for serialized_key, bars in payload.get("bars_by_timestamp", {}).items():
            timeframe, ts_text = serialized_key.split("|", 1)
            self.bars_by_timestamp[(timeframe, int(ts_text))] = {
                symbol: event_from_record(record) for symbol, record in bars.items()
            }

        self.sessions = {symbol: event_from_record(record) for symbol, record in payload.get("sessions", {}).items()}
        active_news = payload.get("active_news")
        self.active_news = event_from_record(active_news) if active_news else None
        self.pending_snapshot_targets = {tuple(item) for item in payload.get("pending_snapshot_targets", [])}
        self.last_seq_no = int(payload.get("last_seq_no", 0))

