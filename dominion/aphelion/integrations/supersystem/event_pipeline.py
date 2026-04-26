"""Event-driven replay orchestration for the merged APHELION supersystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Protocol

from aphelion.core.config import EventTopic
from aphelion.core.event_bus import Event, EventBus, Priority
from aphelion.events import (
    FeatureComputedEvent,
    MarketContext,
    OrderFilledEvent,
    SignalGeneratedEvent,
    TradeDecisionEvent,
)
from aphelion.feature_engine.integrations.mt5pipe import MT5PipeReplayConfig, replay_mt5pipe_into_engine
from aphelion.feature_engine.snapshot import FeatureSnapshot

from .execution_bridge import SignalRecordLike, SuperExecutionStack
from .feature_bridge import FeatureSnapshotHistoryBridge, extract_market_context


class SignalEngineLike(Protocol):
    def consume(self, snapshot: FeatureSnapshot) -> SignalRecordLike | None:
        """Turn one feature snapshot into an execution-ready signal contract."""


@dataclass(frozen=True, slots=True)
class HeuristicSignal:
    timestamp_utc: datetime
    model_artifact_id: str
    direction_60m: int
    position_fraction: float
    confidence: float
    reason: str

    def is_actionable(self) -> bool:
        return self.direction_60m != 0 and self.position_fraction > 0.0


@dataclass(frozen=True, slots=True)
class HeuristicSignalConfig:
    context_len: int = 12
    lookback_bars: int = 1
    min_abs_return: float = 0.00008
    min_dual_source_ratio: float = 0.0
    min_position_fraction: float = 0.0025
    max_position_fraction: float = 0.02
    confidence_scale: float = 3000.0
    position_scale: float = 150.0
    model_artifact_id: str = "heuristic-momentum-v1"


@dataclass
class HeuristicSignalEngine:
    """Torch-free fallback signal engine for replay validation and smoke tests."""

    history: FeatureSnapshotHistoryBridge = field(default_factory=FeatureSnapshotHistoryBridge)
    config: HeuristicSignalConfig = field(default_factory=HeuristicSignalConfig)

    def __post_init__(self) -> None:
        self.history.context_len = self.config.context_len

    def consume(self, snapshot: FeatureSnapshot) -> HeuristicSignal | None:
        self.history.append(snapshot)
        if not snapshot.warmup_complete or not self.history.is_ready():
            return None

        frame = self.history.to_dataframe(tail=self.config.context_len)
        if frame.height <= self.config.lookback_bars:
            return None
        if "close" not in frame.columns:
            return None

        closes = frame.get_column("close").to_list()
        latest_close = float(closes[-1])
        reference_close = float(closes[-(self.config.lookback_bars + 1)])
        if latest_close <= 0.0 or reference_close <= 0.0:
            return None

        move = (latest_close - reference_close) / reference_close
        metadata = self.history.latest_bar_metadata()
        dual_source_ratio = float(metadata.get("dual_source_ratio", 0.0) or 0.0)
        if abs(move) < self.config.min_abs_return:
            return None
        if dual_source_ratio < self.config.min_dual_source_ratio:
            return None

        direction = 1 if move > 0 else -1
        confidence = min(0.99, max(0.0, abs(move) * self.config.confidence_scale))
        position_fraction = min(
            self.config.max_position_fraction,
            max(self.config.min_position_fraction, abs(move) * self.config.position_scale),
        )
        return HeuristicSignal(
            timestamp_utc=metadata["timestamp_utc"],
            model_artifact_id=self.config.model_artifact_id,
            direction_60m=direction,
            position_fraction=position_fraction,
            confidence=confidence,
            reason=f"lookback_return={move:.6f}",
        )


@dataclass(frozen=True, slots=True)
class EventDrivenReplayResult:
    snapshots_processed: int
    features_emitted: int
    signals_generated: int
    decisions_published: int
    fills: int
    closed_positions: int
    final_equity: float
    event_bus_stats: dict[str, Any]


@dataclass
class EventDrivenSuperSystem:
    """Drive replay through an event bus using feature, signal, and execution boundaries."""

    signal_engine: SignalEngineLike = field(default_factory=HeuristicSignalEngine)
    execution_stack: SuperExecutionStack = field(default_factory=SuperExecutionStack)
    event_bus: EventBus = field(default_factory=EventBus)

    def __post_init__(self) -> None:
        self._subscribed = False
        self._running = False
        self._snapshots_processed = 0
        self._features_emitted = 0
        self._signals_generated = 0
        self._decisions_published = 0
        self._fills = 0
        self._closed_positions = 0
        self._subscribe_once()

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def replay(self, replay_config: MT5PipeReplayConfig) -> EventDrivenReplayResult:
        snapshots = replay_mt5pipe_into_engine(replay_config)
        return await self.run_snapshots(snapshots)

    async def run_snapshots(
        self,
        snapshots: Iterable[FeatureSnapshot],
    ) -> EventDrivenReplayResult:
        await self.start()
        try:
            for snapshot in snapshots:
                await self.publish_snapshot(snapshot)
        finally:
            await self.stop()

        return EventDrivenReplayResult(
            snapshots_processed=self._snapshots_processed,
            features_emitted=self._features_emitted,
            signals_generated=self._signals_generated,
            decisions_published=self._decisions_published,
            fills=self._fills,
            closed_positions=self._closed_positions,
            final_equity=self.execution_stack.portfolio.equity,
            event_bus_stats=self.event_bus.stats,
        )

    async def publish_snapshot(self, snapshot: FeatureSnapshot) -> None:
        if not self._running:
            await self.start()

        context_payload = extract_market_context(snapshot)
        market_context = MarketContext(**context_payload)
        if market_context.current_price is not None:
            closed = self.execution_stack.mark_price(
                market_context.current_price,
                timestamp=market_context.timestamp_utc,
            )
            self._closed_positions += len(closed)

        feature_event = FeatureComputedEvent(
            timestamp_utc=market_context.timestamp_utc,
            source="FEATURE_ENGINE",
            snapshot=snapshot,
            market_context=market_context,
        )
        self._snapshots_processed += 1
        await self.event_bus.dispatch(
            Event(
                topic=EventTopic.FEATURE,
                data=feature_event,
                source="FEATURE_ENGINE",
                priority=Priority.NORMAL,
            )
        )

    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        self.event_bus.subscribe(EventTopic.FEATURE, self._on_feature)
        self.event_bus.subscribe(EventTopic.SIGNAL, self._on_signal)
        self._subscribed = True

    async def _on_feature(self, event: Event) -> None:
        feature_event = event.data
        if not isinstance(feature_event, FeatureComputedEvent):
            return
        self._features_emitted += 1
        signal = self.signal_engine.consume(feature_event.snapshot)
        if signal is None:
            return

        signal_event = SignalGeneratedEvent(
            timestamp_utc=signal.timestamp_utc,
            source=getattr(signal, "model_artifact_id", "SIGNAL_ENGINE"),
            signal=signal,
            market_context=feature_event.market_context,
        )
        self._signals_generated += 1
        await self.event_bus.dispatch(
            Event(
                topic=EventTopic.SIGNAL,
                data=signal_event,
                source="SIGNAL_ENGINE",
                priority=Priority.HIGH,
            )
        )

    async def _on_signal(self, event: Event) -> None:
        signal_event = event.data
        if not isinstance(signal_event, SignalGeneratedEvent):
            return

        market_context = signal_event.market_context
        current_price = market_context.current_price
        if current_price is None:
            return

        order = self.execution_stack.order_adapter.to_order(
            signal_event.signal,
            current_price=current_price,
            equity=self.execution_stack.portfolio.equity,
            atr=market_context.atr,
        )
        approved = order is not None
        decision_reason = "order_created" if approved else "signal_not_actionable"
        self._decisions_published += 1
        await self.event_bus.dispatch(
            Event(
                topic=EventTopic.DECISION,
                data=TradeDecisionEvent(
                    timestamp_utc=market_context.timestamp_utc,
                    source="EXECUTION_BRIDGE",
                    signal=signal_event.signal,
                    approved=approved,
                    order=order,
                    reason=decision_reason,
                    market_context=market_context,
                ),
                source="EXECUTION_BRIDGE",
                priority=Priority.HIGH,
            )
        )

        if order is None:
            return

        fill = self.execution_stack.submit_order(
            order,
            current_price=current_price,
            timestamp=market_context.timestamp_utc,
        )
        if fill is None:
            return

        self._fills += 1
        await self.event_bus.dispatch(
            Event(
                topic=EventTopic.ORDER,
                data=OrderFilledEvent(
                    timestamp_utc=market_context.timestamp_utc,
                    source="PAPER_EXECUTOR",
                    signal=signal_event.signal,
                    order=order,
                    fill=fill,
                    market_context=market_context,
                ),
                source="PAPER_EXECUTOR",
                priority=Priority.HIGH,
            )
        )


__all__ = [
    "EventDrivenReplayResult",
    "EventDrivenSuperSystem",
    "HeuristicSignal",
    "HeuristicSignalConfig",
    "HeuristicSignalEngine",
]
