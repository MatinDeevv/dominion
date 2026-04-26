from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, cast

from .events import (
    BarCloseEvent,
    CrossAssetAlignedEvent,
    CrossAssetBarEvent,
    MarketEvent,
    NewsEvent,
    SessionEvent,
    TickEvent,
)
from .features.base import FeatureContext
from .observability import FeatureEngineObserver
from .policies import FeatureVersionManager, MissingDataPolicy, WarmupManager
from .registry import FeatureRegistry
from .snapshot import FeatureSnapshot, build_feature_snapshot
from .state import FeatureStateKey, FeatureStateStore


@dataclass(slots=True)
class FeatureEngineConfig:
    primary_symbol: str = "XAUUSD"
    default_timeframe: str = "1m"
    time_zone: str = "UTC"
    emit_bar_snapshots: bool = True
    emit_tick_snapshots: bool = False
    require_monotonic_seq: bool = True
    cross_asset_emit_timeout_bars: int = 1


@dataclass(slots=True)
class FeatureEngine:
    registry: FeatureRegistry
    config: FeatureEngineConfig = field(default_factory=FeatureEngineConfig)
    state_store: FeatureStateStore = field(default_factory=FeatureStateStore)
    missing_data_policy: MissingDataPolicy = field(default_factory=MissingDataPolicy)
    warmup_manager: WarmupManager = field(default_factory=WarmupManager)
    version_manager: FeatureVersionManager = field(default_factory=FeatureVersionManager)
    observer: FeatureEngineObserver = field(default_factory=FeatureEngineObserver)
    latest_snapshots: dict[tuple[str, str], FeatureSnapshot] = field(default_factory=dict)

    def on_event(self, event: MarketEvent) -> list[FeatureSnapshot]:
        self._guard_sequence(event)
        self._ingest_event(event)

        snapshots: list[FeatureSnapshot] = []
        context = FeatureContext(
            state_store=self.state_store,
            primary_symbol=self.config.primary_symbol,
            event=event,
            default_timeframe=self.config.default_timeframe,
            time_zone=self.config.time_zone,
        )
        self._route_event(event, context)

        if isinstance(event, (BarCloseEvent, CrossAssetBarEvent)):
            aligned = self._maybe_build_cross_asset_aligned_event(event)
            if aligned is not None:
                aligned_context = FeatureContext(
                    state_store=self.state_store,
                    primary_symbol=self.config.primary_symbol,
                    event=aligned,
                    default_timeframe=self.config.default_timeframe,
                    time_zone=self.config.time_zone,
                )
                self._route_event(aligned, aligned_context)
            snapshots.extend(self._handle_bar_event(event))
        elif isinstance(event, TickEvent) and self.config.emit_tick_snapshots:
            snapshot = self.build_latest_snapshot(symbol=event.symbol, timeframe=self.config.default_timeframe)
            if snapshot is not None:
                snapshots.append(snapshot)

        return snapshots

    def build_latest_snapshot(self, *, symbol: str, timeframe: str, ts_event_ns: int | None = None) -> FeatureSnapshot | None:
        applicable_features = [
            feature for feature in self.registry.features if feature.enabled and feature.supports_timeframe(timeframe)
        ]
        if not applicable_features:
            return None

        features_payload: dict[str, Any] = {}
        ready_pairs: list[tuple[Any, dict[str, Any]]] = []
        previous_snapshot = self.latest_snapshots.get((symbol, timeframe))
        missing_count = 0
        for feature in applicable_features:
            key = FeatureStateKey(feature.name, symbol, timeframe)
            state = self.state_store.feature_states.get(key)
            if state is None:
                missing_count += 1
                self.observer.record_missing(feature.name)
                previous_value = previous_snapshot.features.get(feature.name) if previous_snapshot else None
                features_payload[feature.name] = self.missing_data_policy.handle_missing(previous_value)
                continue
            ready_pairs.append((feature, state))
            features_payload[feature.name] = feature.value(state)

        microstructure_feature = next((feature for feature, _ in ready_pairs if feature.name == "microstructure"), None)
        microstructure_state = self.state_store.feature_states.get(FeatureStateKey("microstructure", symbol, timeframe))
        microstructure_values = (
            microstructure_feature.value(microstructure_state)
            if microstructure_feature is not None and microstructure_state is not None
            else None
        )
        if isinstance(microstructure_values, dict):
            for key, value in microstructure_values.items():
                if key.startswith("ms_"):
                    features_payload[key] = value

        warmup_complete = all(feature.ready(state) for feature, state in ready_pairs) if ready_pairs else False
        if self.missing_data_policy.should_skip_snapshot(missing_count):
            return None
        feature_version = self.version_manager.resolve(applicable_features)
        latest_bar = self.state_store.latest_bar(symbol, timeframe)
        latest_tick = self.state_store.latest_tick(symbol)
        resolved_ts_event_ns = ts_event_ns
        if resolved_ts_event_ns is None:
            resolved_ts_event_ns = cast(int, getattr(latest_bar, "ts_event_ns", getattr(latest_tick, "ts_event_ns", 0)))
        snapshot = build_feature_snapshot(
            ts_event_ns=resolved_ts_event_ns,
            symbol=symbol,
            timeframe=timeframe,
            feature_version=feature_version,
            warmup_complete=warmup_complete,
            missing_count=missing_count,
            features=features_payload,
            metadata={
                "primary_symbol": self.config.primary_symbol,
                "latest_news_state": getattr(self.state_store.active_news, "active_window_state", None),
                "engine_seq_no": self.state_store.last_seq_no,
                "open": getattr(latest_bar, "open", None),
                "high": getattr(latest_bar, "high", None),
                "low": getattr(latest_bar, "low", None),
                "close": getattr(latest_bar, "close", None),
                "volume": getattr(latest_bar, "volume", None),
                "bid": getattr(latest_tick, "bid", None),
                "ask": getattr(latest_tick, "ask", None),
                "mid": (
                    ((float(getattr(latest_tick, "bid", 0.0) or 0.0) + float(getattr(latest_tick, "ask", 0.0) or 0.0)) / 2.0)
                    if latest_tick is not None
                    else None
                ),
                "ms_microstructure_ready": bool(
                    microstructure_feature is not None
                    and microstructure_state is not None
                    and microstructure_feature.ready(microstructure_state)
                    and int((microstructure_values or {}).get("ms_vpin_buckets_completed", 0) or 0) >= 1
                ),
            },
        )
        self.latest_snapshots[(symbol, timeframe)] = snapshot
        self.observer.record_snapshot_emission(symbol, timeframe)
        return snapshot

    def ready_for_inference(self, *, symbol: str, timeframe: str, tick_sensitive: bool = False) -> bool:
        snapshot = self.latest_snapshots.get((symbol, timeframe))
        if not snapshot:
            return False
        if tick_sensitive and not snapshot.metadata.get("ms_microstructure_ready", False):
            return False
        return bool(snapshot.warmup_complete and snapshot.missing_count == 0)

    def export_engine_state(self) -> dict[str, Any]:
        return {
            "config": {
                "primary_symbol": self.config.primary_symbol,
                "default_timeframe": self.config.default_timeframe,
                "time_zone": self.config.time_zone,
                "emit_bar_snapshots": self.config.emit_bar_snapshots,
                "emit_tick_snapshots": self.config.emit_tick_snapshots,
                "require_monotonic_seq": self.config.require_monotonic_seq,
                "cross_asset_emit_timeout_bars": self.config.cross_asset_emit_timeout_bars,
            },
            "state_store": self.state_store.export(self.registry),
            "latest_snapshots": {f"{symbol}|{timeframe}": snapshot.to_record() for (symbol, timeframe), snapshot in self.latest_snapshots.items()},
        }

    def restore_engine_state(self, payload: dict[str, Any]) -> None:
        self.state_store.restore(payload["state_store"])
        self.latest_snapshots.clear()
        for serialized_key, record in payload.get("latest_snapshots", {}).items():
            symbol, timeframe = serialized_key.split("|", 1)
            self.latest_snapshots[(symbol, timeframe)] = FeatureSnapshot(
                ts_event_ns=record["ts_event_ns"],
                symbol=record["symbol"],
                timeframe=record["timeframe"],
                feature_version=record["feature_version"],
                warmup_complete=record["warmup_complete"],
                missing_count=record["missing_count"],
                features=record["features"],
                metadata=record["metadata"],
            )

    def _ingest_event(self, event: MarketEvent) -> None:
        if isinstance(event, TickEvent):
            self.state_store.update_tick(event)
        elif isinstance(event, (BarCloseEvent, CrossAssetBarEvent)):
            self.state_store.update_bar(event)
        elif isinstance(event, SessionEvent):
            self.state_store.update_session(event)
        elif isinstance(event, NewsEvent):
            self.state_store.update_news(event)

    def _route_event(self, event: MarketEvent, context: FeatureContext) -> None:
        for feature in self.registry.features_for_event(event):
            scope = feature.scope(event, context)
            key = FeatureStateKey(feature.name, scope.symbol, scope.timeframe)
            state = self.state_store.get_or_create(key, feature.initialize_state)
            start_ns = time.perf_counter_ns()
            try:
                feature.update(event, state, context)
            except Exception:
                self.observer.record_error(feature.name)
                raise
            finally:
                self.observer.record_feature_latency(feature.name, time.perf_counter_ns() - start_ns)

    def _maybe_build_cross_asset_aligned_event(
        self, event: BarCloseEvent | CrossAssetBarEvent
    ) -> CrossAssetAlignedEvent | None:
        required_symbols = self.registry.required_cross_asset_symbols()
        if not required_symbols:
            return None
        if self.config.primary_symbol not in required_symbols:
            required_symbols.add(self.config.primary_symbol)
        bars = self.state_store.bars_for_timestamp(event.timeframe, event.ts_event_ns)
        if not required_symbols.issubset(bars.keys()):
            return None
        return CrossAssetAlignedEvent(
            seq_no=event.seq_no,
            ts_event_ns=event.ts_event_ns,
            symbol=self.config.primary_symbol,
            timeframe=event.timeframe,
            bars=bars,
        )

    def _handle_bar_event(self, event: BarCloseEvent | CrossAssetBarEvent) -> list[FeatureSnapshot]:
        if not self.config.emit_bar_snapshots:
            return []
        if event.symbol == self.config.primary_symbol:
            self.state_store.add_pending_snapshot(event.symbol, event.timeframe, event.ts_event_ns)
        return self._flush_pending_snapshots(event.timeframe)

    def _flush_pending_snapshots(self, timeframe: str) -> list[FeatureSnapshot]:
        emitted: list[FeatureSnapshot] = []
        required_symbols = self.registry.required_cross_asset_symbols()
        if required_symbols and self.config.primary_symbol not in required_symbols:
            required_symbols = set(required_symbols)
            required_symbols.add(self.config.primary_symbol)

        for target in sorted(self.state_store.pending_snapshot_targets, key=lambda item: item[2]):
            symbol, target_timeframe, ts_event_ns = target
            if target_timeframe != timeframe:
                continue
            bars = self.state_store.bars_for_timestamp(timeframe, ts_event_ns)
            missing_required = [req_symbol for req_symbol in required_symbols if req_symbol not in bars]
            if missing_required and not self.missing_data_policy.allow_partial_cross_asset:
                continue

            snapshot = self.build_latest_snapshot(symbol=symbol, timeframe=timeframe, ts_event_ns=ts_event_ns)
            if snapshot is not None:
                emitted.append(snapshot)
                self.state_store.remove_pending_snapshot(target)
        return emitted

    def _guard_sequence(self, event: MarketEvent) -> None:
        if self.config.require_monotonic_seq and event.seq_no < self.state_store.last_seq_no:
            raise ValueError(
                f"Out-of-order journal event: seq={event.seq_no} last_seq={self.state_store.last_seq_no}"
            )

    def _snapshot_probe(self, symbol: str, timeframe: str, ts_event_ns: int | None) -> BarCloseEvent:
        return BarCloseEvent(
            seq_no=self.state_store.last_seq_no,
            ts_event_ns=ts_event_ns or 0,
            symbol=symbol,
            timeframe=timeframe,
            open=0.0,
            high=0.0,
            low=0.0,
            close=0.0,
            volume=0.0,
            tick_count=0,
            vwap=None,
        )

    def _context_stub(self) -> FeatureContext:
        event = self._snapshot_probe(self.config.primary_symbol, self.config.default_timeframe, 0)
        return FeatureContext(
            state_store=self.state_store,
            primary_symbol=self.config.primary_symbol,
            event=event,
            default_timeframe=self.config.default_timeframe,
            time_zone=self.config.time_zone,
        )
