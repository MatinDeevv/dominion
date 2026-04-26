from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configure_path() -> None:
    import sys

    src_path = str(ROOT / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


configure_path()

from aphelion.feature_engine.engine import FeatureEngine, FeatureEngineConfig
from aphelion.feature_engine.events import BarCloseEvent, TickEvent
from aphelion.feature_engine.features import MicrostructureFeature, RegimeStateFeature, TechnicalFeature
from aphelion.feature_engine.registry import FeatureRegistry


def make_tick(
    seq_no: int,
    ts_event_ns: int,
    *,
    symbol: str = "XAUUSD",
    last: float = 1900.0,
    spread: float = 0.2,
    volume: float = 10.0,
    bid_size: float = 1.0,
    ask_size: float = 1.0,
    implied_vol: float | None = None,
) -> TickEvent:
    half_spread = spread / 2.0
    return TickEvent(
        seq_no=seq_no,
        ts_event_ns=ts_event_ns,
        ts_receive_ns=ts_event_ns + 100,
        symbol=symbol,
        bid=last - half_spread,
        ask=last + half_spread,
        last=last,
        volume=volume,
        source="pytest",
        bid_size=bid_size,
        ask_size=ask_size,
        implied_vol=implied_vol,
    )


def make_bar(
    seq_no: int,
    ts_event_ns: int,
    *,
    symbol: str = "XAUUSD",
    timeframe: str = "1m",
    open_price: float = 1900.0,
    high: float = 1901.0,
    low: float = 1899.0,
    close: float = 1900.5,
    volume: float = 100.0,
) -> BarCloseEvent:
    return BarCloseEvent(
        seq_no=seq_no,
        ts_event_ns=ts_event_ns,
        symbol=symbol,
        timeframe=timeframe,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        tick_count=10,
        vwap=(high + low + close) / 3.0,
    )


def build_microstructure_engine(*, window: int = 20, bucket_volume: float = 50.0) -> FeatureEngine:
    registry = FeatureRegistry()
    registry.register(MicrostructureFeature(window=window, bucket_volume=bucket_volume, default_timeframe="1m"))
    return FeatureEngine(
        registry=registry,
        config=FeatureEngineConfig(primary_symbol="XAUUSD", default_timeframe="1m"),
    )


def build_technical_feature(period: int = 20) -> TechnicalFeature:
    return TechnicalFeature(
        atr_periods=(5,),
        bollinger_periods=(5,),
        rsi_periods=(5,),
        ladder_periods=(5,),
        stochastic_periods=(5,),
        adx_period=5,
        realized_vol_window=period,
        default_timeframe="1m",
    )


def build_regime_feature(window: int = 20, hurst_window: int = 100) -> RegimeStateFeature:
    return RegimeStateFeature(window=window, hurst_window=hurst_window, default_timeframe="1h")


def trending_prices(length: int, start: float = 1900.0, step: float = 1.0) -> list[float]:
    return [start + idx * step for idx in range(length)]


def sine_prices(length: int, amplitude: float = 10.0, baseline: float = 1900.0) -> list[float]:
    return [baseline + amplitude * math.sin(idx / 5.0) for idx in range(length)]
