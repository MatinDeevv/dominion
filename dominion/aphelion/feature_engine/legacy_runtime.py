"""
Canonical-engine adapter with legacy ``on_bar``/``on_tick`` API surface.

The old parallel "legacy" feature sub-engines (cointegration, halftrend,
microstructure, …) have been retired.  This module now exposes
``LegacyFeatureEngine`` as a thin adapter over the canonical event-driven
``FeatureEngine`` so that backtest and paper trading compute features through
**identical logic** to live inference, eliminating the train/live gap.

Callers keep the same ``LegacyFeatureEngine(data_layer, clock)`` constructor
and ``on_bar(bar) -> dict`` / ``on_tick(tick) -> dict`` API surface; no
changes are required in ``backtest.engine`` or ``paper.session``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .defaults import build_default_registry
from .engine import FeatureEngine, FeatureEngineConfig
from .events import BarCloseEvent, TickEvent
from aphelion.inference.feature_schema import flatten_snapshot

logger = logging.getLogger(__name__)


class LegacyFeatureEngine:
    """
    Canonical-engine adapter that preserves the legacy ``on_bar``/``on_tick``
    API surface.

    Internally delegates all feature computation to the canonical event-driven
    ``FeatureEngine`` (``aphelion.feature_engine.engine``), so backtest and
    paper trading produce **identical** features to live inference.

    The ``data_layer`` and ``clock`` constructor arguments are retained for
    drop-in compatibility with existing call-sites but are not used; the
    canonical engine is self-contained and builds its state from the event
    stream.
    """

    def __init__(self, data_layer: Any = None, clock: Any = None, *, symbol: str = "XAUUSD", timeframe: str = "1m"):
        self._symbol = symbol
        self._timeframe = timeframe
        self._seq_no: int = 0
        registry = build_default_registry(
            primary_symbol=symbol,
            default_timeframe=timeframe,
        )
        self._engine = FeatureEngine(
            registry=registry,
            config=FeatureEngineConfig(
                primary_symbol=symbol,
                default_timeframe=timeframe,
            ),
        )

    def on_tick(self, tick: Any) -> dict:
        """Pass the tick through the canonical engine for microstructure state accumulation.

        Returns an empty dict.  The canonical engine accumulates tick data
        internally so that microstructure features are available at the next
        ``on_bar`` call.  Unlike the old implementation, raw VPIN is not
        returned here; it is included in the bar-level snapshot under the
        ``microstructure_*`` keys.
        """
        self._seq_no += 1
        ts_ns = self._to_ns(getattr(tick, "timestamp", None))
        event = TickEvent(
            seq_no=self._seq_no,
            ts_event_ns=ts_ns,
            ts_receive_ns=ts_ns,
            symbol=self._symbol,
            bid=float(getattr(tick, "bid", 0.0) or 0.0),
            ask=float(getattr(tick, "ask", 0.0) or 0.0),
            last=float(getattr(tick, "last", 0.0) or 0.0),
            volume=float(getattr(tick, "volume", 0.0) or 0.0),
            source="legacy_adapter",
        )
        try:
            self._engine.on_event(event)
        except Exception:
            logger.debug("LegacyFeatureEngine.on_tick error", exc_info=True)
        return {}

    def on_bar(self, bar: Any) -> dict:
        """Process a completed bar through the canonical engine and return the flattened feature dict."""
        self._seq_no += 1
        ts_ns = self._to_ns(getattr(bar, "timestamp", None))
        timeframe_str: str = getattr(bar.timeframe, "value", str(bar.timeframe))
        event = BarCloseEvent(
            seq_no=self._seq_no,
            ts_event_ns=ts_ns,
            symbol=self._symbol,
            timeframe=timeframe_str,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
            tick_count=int(getattr(bar, "tick_volume", 0) or 0),
            vwap=None,
        )
        try:
            snapshots = self._engine.on_event(event)
        except Exception:
            logger.debug("LegacyFeatureEngine.on_bar error", exc_info=True)
            return {}

        if not snapshots:
            return {}

        return flatten_snapshot(snapshots[-1].features)

    # ── No-op stubs for legacy callers ───────────────────────────────────────

    def set_external_prices(self, symbol: str, prices: Any) -> None:
        pass

    def set_external_order_flow(self, symbol: str, signed_flow: Any) -> None:
        pass

    def set_mtf_weights(self, weights: Any) -> None:
        pass

    def reset_session(self) -> None:
        pass

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _to_ns(ts: Any) -> int:
        """Convert a timestamp to integer nanoseconds."""
        if ts is None:
            return 0
        if isinstance(ts, datetime):
            return int(ts.timestamp() * 1_000_000_000)
        try:
            return int(float(ts) * 1_000_000_000)
        except Exception:
            return 0
