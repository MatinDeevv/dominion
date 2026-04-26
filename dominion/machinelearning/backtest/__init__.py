"""Canonical vectorized backtest package for the machinelearning stack."""

from .engine import BacktestEngine, BacktestResult
from .metrics import BacktestMetrics, compute_metrics
from .report import BacktestReport

__all__ = [
    "BacktestEngine",
    "BacktestMetrics",
    "BacktestReport",
    "BacktestResult",
    "compute_metrics",
]
