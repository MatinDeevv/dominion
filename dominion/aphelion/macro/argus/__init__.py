"""ARGUS — Market anomaly detection."""

import structlog

log = structlog.get_logger(__name__)

from .core import ArgusCore, MarketAnomaly

__all__ = ["ArgusCore", "MarketAnomaly"]
