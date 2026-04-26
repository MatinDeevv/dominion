"""Route neural SignalRecord objects into the APHELION research execution stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from aphelion.backtest.order import Order
from aphelion.backtest.portfolio import Portfolio
from aphelion.core.clock import MarketClock
from aphelion.core.config import SENTINEL
from aphelion.core.event_bus import EventBus
from aphelion.core.execution import build_order_from_signal, next_order_id
from aphelion.risk.sentinel.circuit_breaker import CircuitBreaker
from aphelion.risk.sentinel.core import SentinelCore
from aphelion.risk.sentinel.execution.enforcer import ExecutionEnforcer
from aphelion.risk.sentinel.execution.paper import PaperConfig, PaperExecutor, PaperFill
from aphelion.risk.sentinel.validator import TradeValidator


class SignalRecordLike(Protocol):
    timestamp_utc: datetime
    model_artifact_id: str
    direction_60m: int
    position_fraction: float

    def is_actionable(self) -> bool:
        """Return whether the signal is approved to consume risk."""


@dataclass(frozen=True)
class SignalOrderAdapterConfig:
    symbol: str = "XAUUSD"
    atr_sl_multiplier: float = 2.0
    rr_ratio: float = 2.0
    default_atr_fraction: float = 0.005
    lot_size_oz: float = 100.0


class SignalOrderAdapter:
    """Translate the neural signal contract into research-engine market orders."""

    def __init__(self, config: SignalOrderAdapterConfig | None = None) -> None:
        self._config = config or SignalOrderAdapterConfig()

    def to_order(
        self,
        signal: SignalRecordLike,
        *,
        current_price: float,
        equity: float,
        atr: float | None = None,
    ) -> Order | None:
        if not signal.is_actionable():
            return None

        size_pct = min(max(signal.position_fraction, 0.0), SENTINEL.max_position_pct)
        if size_pct <= 0.0:
            return None

        atr_value = atr if atr is not None and atr > 0.0 else abs(current_price) * self._config.default_atr_fraction

        oid = next_order_id("MLSIG")
        created_time = signal.timestamp_utc
        if created_time.tzinfo is None:
            created_time = created_time.replace(tzinfo=timezone.utc)

        order = build_order_from_signal(
            direction=signal.direction_60m,
            current_price=current_price,
            atr=atr_value,
            equity=equity,
            size_pct=size_pct,
            atr_sl_multiplier=self._config.atr_sl_multiplier,
            rr_ratio=self._config.rr_ratio,
            lot_size_oz=self._config.lot_size_oz,
            symbol=self._config.symbol,
            proposed_by=signal.model_artifact_id,
            order_id=oid,
        )
        if order is not None:
            order.created_time = created_time
        return order


@dataclass
class SuperExecutionStack:
    """Minimal execution control plane for workspace-level signal replay and paper trading."""

    initial_capital: float = 10_000.0
    paper_config: PaperConfig = field(default_factory=PaperConfig)
    order_adapter: SignalOrderAdapter = field(default_factory=SignalOrderAdapter)

    def __post_init__(self) -> None:
        self.event_bus = EventBus()
        self.clock = MarketClock()
        self.sentinel_core = SentinelCore(self.event_bus, self.clock)
        self.validator = TradeValidator(self.sentinel_core, self.clock)
        self.circuit_breaker = CircuitBreaker(self.event_bus)
        self.enforcer = ExecutionEnforcer(self.validator, self.circuit_breaker)
        self.portfolio = Portfolio(self.initial_capital)
        self.executor = PaperExecutor(
            config=self.paper_config,
            enforcer=self.enforcer,
            sentinel_core=self.sentinel_core,
            portfolio=self.portfolio,
            event_bus=self.event_bus,
        )
        self.closed_positions: list[dict[str, Any]] = []

    def mark_price(
        self,
        current_price: float,
        *,
        timestamp: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if timestamp is not None:
            self.clock.set_simulated_time(timestamp)
        self.sentinel_core.update_equity(self.portfolio.equity)
        self.circuit_breaker.update(self.portfolio.equity)
        self.executor.update_price(current_price)
        self.executor.check_pending_orders(current_price)

        closed: list[dict[str, Any]] = []
        for position_id, exit_price, reason in self.executor.check_sl_tp(current_price):
            pnl = self.executor.close_position(position_id, exit_price, reason)
            closed_record = {
                "position_id": position_id,
                "exit_price": exit_price,
                "reason": reason,
                "net_pnl": pnl,
            }
            self.closed_positions.append(closed_record)
            closed.append(closed_record)
        return closed

    def submit_signal(
        self,
        signal: SignalRecordLike,
        *,
        current_price: float,
        atr: float | None = None,
        timestamp: datetime | None = None,
    ) -> PaperFill | None:
        if timestamp is not None:
            self.clock.set_simulated_time(timestamp)
        self.sentinel_core.update_equity(self.portfolio.equity)
        order = self.order_adapter.to_order(
            signal,
            current_price=current_price,
            equity=self.portfolio.equity,
            atr=atr,
        )
        if order is None:
            return None
        return self.submit_order(order, current_price=current_price, timestamp=timestamp)

    def submit_order(
        self,
        order: Order,
        *,
        current_price: float,
        timestamp: datetime | None = None,
    ) -> PaperFill | None:
        if timestamp is not None:
            self.clock.set_simulated_time(timestamp)
        self.sentinel_core.update_equity(self.portfolio.equity)
        return self.executor.submit_order(order, current_price=current_price)


__all__ = [
    "SignalRecordLike",
    "SignalOrderAdapter",
    "SignalOrderAdapterConfig",
    "SuperExecutionStack",
]
