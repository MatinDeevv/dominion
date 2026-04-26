"""
TITAN — Performance Validator
Checks minimum Sharpe, win rate, profit factor, drawdown.
"""

import structlog

log = structlog.get_logger(__name__)

from aphelion.risk.titan.gate import PerformanceValidator

__all__ = ["PerformanceValidator"]
