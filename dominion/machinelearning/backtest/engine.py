"""Vectorized ML backtest engine for signal-quality evaluation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from machinelearning.signal.records import SignalRecord

from .metrics import BacktestMetrics, compute_metrics


@dataclass(slots=True)
class BacktestResult:
    """Container for vectorized backtest output used by the ML stack."""

    signals: list[SignalRecord]
    realized_returns: np.ndarray
    pnl_series: np.ndarray
    equity_curve: np.ndarray
    trade_mask: np.ndarray
    metrics: BacktestMetrics | None = None
    notional: float = 1000.0
    spread_bps: float = 3.0
    action_horizon_minutes: int = 60


class BacktestEngine:
    """Run a fast signal-quality backtest with a consistent friction model."""

    def __init__(
        self,
        spread_bps: float = 3.0,
        notional: float = 1000.0,
    ) -> None:
        if spread_bps < 0.0:
            raise ValueError("spread_bps must be non-negative")
        if notional <= 0.0:
            raise ValueError("notional must be positive")
        self.spread_bps = float(spread_bps)
        self.notional = float(notional)

    def run(
        self,
        signals: list[SignalRecord],
        realized_returns: np.ndarray,
    ) -> BacktestResult:
        realized = np.asarray(realized_returns, dtype=float).reshape(-1)
        if len(signals) != realized.size:
            raise ValueError("signals and realized_returns must have the same length")

        n_signals = realized.size
        directions = np.fromiter((signal.resolved_action_direction() for signal in signals), dtype=np.int64, count=n_signals)
        positions = np.fromiter((signal.position_fraction for signal in signals), dtype=np.float64, count=n_signals)
        actionable = np.fromiter((signal.is_actionable() for signal in signals), dtype=bool, count=n_signals)

        signed_returns = directions.astype(np.float64) * realized
        net_returns = np.where(actionable, signed_returns - self.spread_bps, 0.0)
        pnl_series = np.where(actionable, net_returns * positions * self.notional, 0.0)
        equity_curve = np.cumsum(pnl_series)

        result = BacktestResult(
            signals=list(signals),
            realized_returns=realized,
            pnl_series=pnl_series,
            equity_curve=equity_curve,
            trade_mask=actionable,
            notional=self.notional,
            spread_bps=self.spread_bps,
            action_horizon_minutes=(
                signals[0].action_horizon_minutes if signals else 60
            ),
        )
        result.metrics = compute_metrics(result)
        return result


__all__ = ["BacktestEngine", "BacktestResult"]
