"""HERALD — News impact classification."""

import structlog

log = structlog.get_logger(__name__)

from .core import HeraldCore, NewsEvent

__all__ = ["HeraldCore", "NewsEvent"]
