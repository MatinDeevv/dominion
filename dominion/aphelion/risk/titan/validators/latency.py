"""
TITAN — Latency Validator
Ensures system pipeline latency meets requirements.
"""

import structlog

log = structlog.get_logger(__name__)

from aphelion.risk.titan.gate import LatencyValidator

__all__ = ["LatencyValidator"]
