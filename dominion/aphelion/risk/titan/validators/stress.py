"""
TITAN — Stress Validator
Checks Monte Carlo worst-case and stress test results.
"""

import structlog

log = structlog.get_logger(__name__)

from aphelion.risk.titan.gate import StressValidator

__all__ = ["StressValidator"]
