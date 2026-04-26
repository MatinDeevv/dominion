"""
TITAN — Regression Validator
Ensures new changes don't degrade existing performance.
"""

import structlog

log = structlog.get_logger(__name__)

from aphelion.risk.titan.gate import RegressionValidator

__all__ = ["RegressionValidator"]
