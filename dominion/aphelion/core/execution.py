"""Shared execution primitives for the APHELION pipeline.

Centralises logic that was previously duplicated across ``backtest/engine.py``,
``risk/sentinel/execution/paper.py``, ``integrations/supersystem/execution_bridge.py``,
and ``evolution/prometheus/evaluator.py``.

Every execution path — backtest, paper, live — **must** route through these
helpers so that order construction, sizing, and enforcement behave identically.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

from itertools import count
from typing import TYPE_CHECKING

from aphelion.backtest.order import Order, OrderSide, OrderStatus, OrderType
from aphelion.core.config import SENTINEL

if TYPE_CHECKING:
    from aphelion.risk.sentinel.execution.enforcer import ExecutionEnforcer
    from aphelion.risk.sentinel.validator import TradeProposal


# ── Shared counter for order IDs ─────────────────────────────────────────────

_GLOBAL_ORDER_COUNTER = count(1)


def next_order_id(prefix: str = "ORD") -> str:
    """Thread-unsafe but deterministic order-ID generator."""
    return f"{prefix}-{next(_GLOBAL_ORDER_COUNTER):06d}"


# ── TradeProposal factory ────────────────────────────────────────────────────

def build_trade_proposal(order: Order, entry_price: float) -> "TradeProposal":
    """Build a ``TradeProposal`` from an ``Order``.

    Previously this 8-line stanza was copy-pasted in three places.
    """
    log.debug("function_entered", function="build_trade_proposal")
    from aphelion.risk.sentinel.validator import TradeProposal

    direction = "LONG" if order.side == OrderSide.BUY else "SHORT"
    return TradeProposal(
        symbol=order.symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
        size_pct=order.size_pct,
        proposed_by=order.proposed_by,
    )


# ── Enforcement scaling ─────────────────────────────────────────────────────

def apply_enforcement(
    order: Order,
    entry_price: float,
    enforcer: "ExecutionEnforcer",
) -> Order | None:
    """Run an order through the SENTINEL enforcement pipeline.

    Returns the (possibly size-adjusted) order, or ``None`` if rejected.
    This logic was duplicated in ``BacktestEngine._apply_execution_enforcement``
    and ``PaperExecutor.submit_order``.
    """
    log.debug("function_entered", function="apply_enforcement")
    proposal = build_trade_proposal(order, entry_price)
    approved, _reason, final_size_pct = enforcer.approve_order(proposal)

    if not approved or final_size_pct <= 0:
        order.status = OrderStatus.REJECTED
        return None

    if order.size_pct > 0 and final_size_pct != order.size_pct:
        scale = final_size_pct / order.size_pct
        order.size_lots = max(0.01, round(order.size_lots * scale, 2))

    order.size_pct = final_size_pct
    return order


# ── Commission helper ────────────────────────────────────────────────────────

def compute_commission(size_lots: float, commission_per_lot: float) -> float:
    """Single source of truth for commission calculation."""
    return commission_per_lot * size_lots


# ── Order factory ────────────────────────────────────────────────────────────

def build_order_from_signal(
    *,
    direction: int,
    current_price: float,
    atr: float,
    equity: float,
    size_pct: float,
    atr_sl_multiplier: float = 2.0,
    rr_ratio: float = 2.0,
    lot_size_oz: float = 100.0,
    symbol: str = "XAUUSD",
    proposed_by: str = "SYSTEM",
    order_id: str | None = None,
) -> Order | None:
    """Construct a market order from a directional signal.

    This consolidates the order-creation logic that was duplicated in
    ``GenomeStrategy.__call__``, ``SignalOrderAdapter.to_order``, and
    inline in various strategy callbacks.

    Parameters
    ----------
    direction : int
        ``1`` for BUY, ``-1`` for SELL, ``0`` → returns ``None``.
    """
    log.debug("function_entered", function="build_order_from_signal")
    if direction == 0:
        return None

    size_pct = min(max(size_pct, 0.0), SENTINEL.max_position_pct)
    if size_pct <= 0:
        return None

    if atr <= 0:
        atr = abs(current_price) * 0.005

    sl_distance = max(atr * atr_sl_multiplier, 0.01)
    tp_distance = sl_distance * rr_ratio

    if direction > 0:
        side = OrderSide.BUY
        stop_loss = current_price - sl_distance
        take_profit = current_price + tp_distance
    else:
        side = OrderSide.SELL
        stop_loss = current_price + sl_distance
        take_profit = current_price - tp_distance

    risk_dollars = max(equity * size_pct, 0.0)
    lot_size = risk_dollars / (sl_distance * lot_size_oz) if sl_distance > 0 else 0.0
    lot_size = max(0.01, round(lot_size, 2))

    return Order(
        order_id=order_id or next_order_id(proposed_by.split("_")[0][:6] if proposed_by else "ORD"),
        symbol=symbol,
        order_type=OrderType.MARKET,
        side=side,
        size_lots=lot_size,
        entry_price=0.0,
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        size_pct=size_pct,
        proposed_by=proposed_by,
    )
