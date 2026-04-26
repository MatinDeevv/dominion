"""SPECTER — Stealth accumulation/distribution detection."""

import structlog

log = structlog.get_logger(__name__)

from .core import SpecterCore, StealthSignal

__all__ = ["SpecterCore", "StealthSignal"]
