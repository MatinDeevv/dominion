"""ORACLE — Macro forecasting."""

import structlog

log = structlog.get_logger(__name__)

from .core import OracleCore, Forecast

__all__ = ["OracleCore", "Forecast"]
