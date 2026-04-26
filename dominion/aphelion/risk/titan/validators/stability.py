"""
TITAN — Stability Validator
Checks walk-forward fold stability.
"""

import structlog

log = structlog.get_logger(__name__)

from aphelion.risk.titan.gate import StabilityValidator

__all__ = ["StabilityValidator"]
