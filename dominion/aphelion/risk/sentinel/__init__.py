"""SENTINEL risk authority package."""

import structlog

log = structlog.get_logger(__name__)

from aphelion.risk.sentinel.core import Position, SentinelCore
from aphelion.risk.sentinel.position_sizer import PositionSizer
from aphelion.risk.sentinel.validator import (
    TradeProposal,
    TradeValidator,
    ValidationResult,
)
from aphelion.risk.sentinel.circuit_breaker import CircuitBreaker
from aphelion.risk.sentinel.execution.enforcer import ExecutionEnforcer

__all__ = [
    "Position",
    "SentinelCore",
    "PositionSizer",
    "TradeProposal",
    "TradeValidator",
    "ValidationResult",
    "CircuitBreaker",
    "ExecutionEnforcer",
]
