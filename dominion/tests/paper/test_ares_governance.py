"""Tests for ARES per-order governance in paper trading."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aphelion.ares.coordinator import AggregatedSignal, SignalSource, StrategyVote
from aphelion.backtest.order import Order, OrderSide, OrderType
from aphelion.core.config import Tier
from aphelion.paper.session import PaperSession, PaperSessionConfig


def _make_order(order_id: str, side: OrderSide) -> Order:
    return Order(
        order_id=order_id,
        symbol="XAUUSD",
        order_type=OrderType.MARKET,
        side=side,
        size_lots=0.10,
        entry_price=0.0,
        stop_loss=1940.0,
        take_profit=1960.0,
        size_pct=0.01,
        proposed_by="TEST_STRATEGY",
    )


def _make_session() -> PaperSession:
    session = PaperSession(
        PaperSessionConfig(initial_capital=10_000.0, warmup_bars=0, monitor_enabled=False),
        feed=MagicMock(),
        ares=MagicMock(),
    )
    session._ledger = MagicMock()
    session._clock = MagicMock()
    session._clock.current_session.return_value = SimpleNamespace(name="LONDON")
    session._sentinel_core = MagicMock()
    session._sentinel_core.l3_triggered = False
    session._strategy = MagicMock()
    session._strategy.last_signal = None
    return session


def test_ares_approves_single_order() -> None:
    session = _make_session()
    order = _make_order("ORD-001", OrderSide.BUY)
    session._ares.aggregate.return_value = AggregatedSignal(
        direction=1,
        consensus_score=0.95,
        confidence=0.80,
        agreement_ratio=1.0,
    )

    governed = session._govern_orders_with_ares([order], datetime.now(timezone.utc))

    assert governed == [order]
    session._ares.aggregate.assert_called_once()
    session._ledger.log_event.assert_not_called()


def test_ares_rejects_single_order() -> None:
    session = _make_session()
    order = _make_order("ORD-002", OrderSide.BUY)
    session._ares.aggregate.return_value = AggregatedSignal(
        direction=0,
        consensus_score=0.10,
        confidence=0.10,
        agreement_ratio=0.25,
        reasoning="No consensus",
        vetoed=True,
        veto_reason="Exposure too high",
    )

    governed = session._govern_orders_with_ares([order], datetime.now(timezone.utc))

    assert governed == []
    assert session._ares_veto_count == 1
    session._ledger.log_event.assert_called_once()


def test_ares_multiple_orders_only_keeps_first(caplog: pytest.LogCaptureFixture) -> None:
    session = _make_session()
    order_one = _make_order("ORD-003", OrderSide.BUY)
    order_two = _make_order("ORD-004", OrderSide.SELL)
    session._ares.aggregate.return_value = AggregatedSignal(
        direction=1,
        consensus_score=0.85,
        confidence=0.75,
        agreement_ratio=1.0,
    )

    with caplog.at_level(logging.WARNING):
        governed = session._govern_orders_with_ares(
            [order_one, order_two],
            datetime.now(timezone.utc),
        )

    assert governed == [order_one]
    assert any("ARES only governs first" in record.message for record in caplog.records)


def test_ares_empty_orders_is_noop() -> None:
    session = _make_session()

    governed = session._govern_orders_with_ares([], datetime.now(timezone.utc))

    assert governed == []
    session._ares.aggregate.assert_not_called()


def test_ares_vote_construction_uses_strategy_confidence() -> None:
    session = _make_session()
    order = _make_order("ORD-005", OrderSide.BUY)
    session._strategy.last_signal = SimpleNamespace(confidence=0.92)
    session._ares.aggregate.return_value = AggregatedSignal(
        direction=1,
        consensus_score=0.95,
        confidence=0.92,
        agreement_ratio=1.0,
    )

    session._govern_orders_with_ares([order], datetime.now(timezone.utc))

    votes = session._ares.aggregate.call_args[0][0]
    assert len(votes) == 1
    vote = votes[0]
    assert isinstance(vote, StrategyVote)
    assert vote.source == SignalSource.HYDRA
    assert vote.direction == 1
    assert vote.confidence == 0.92
    assert vote.tier == Tier.ORACLE
