#!/usr/bin/env python3
"""Benchmark feature-engine replay plus HYDRA-style inference throughput."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Any

import structlog
import typer
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from aphelion.feature_engine.defaults import build_default_registry
from aphelion.feature_engine.engine import FeatureEngine, FeatureEngineConfig
from aphelion.feature_engine.events import BarCloseEvent, TickEvent
from aphelion.feature_engine.snapshot import FeatureSnapshot

try:
    from aphelion.intelligence.hydra.dataset import CATEGORICAL_FEATURES, CONTINUOUS_FEATURES
    from aphelion.intelligence.hydra.inference import HydraInference
except Exception:  # pragma: no cover - optional ML runtime can be absent.
    CATEGORICAL_FEATURES = []
    CONTINUOUS_FEATURES = []
    HydraInference = None  # type: ignore[assignment]


log = structlog.get_logger(__name__)
app = typer.Typer(add_completion=False)
console = Console()


class BenchmarkConfig(BaseModel):
    snapshot_count: int = Field(default=1000, ge=1)
    warmup: int = Field(default=100, ge=0)
    symbol: str = Field(default="XAUUSD", min_length=1)
    checkpoint: str | None = None


@dataclass(slots=True)
class SyntheticHydraAdapter:
    """Small deterministic fallback when no HYDRA checkpoint is available."""

    symbol: str

    def predict(self, snapshot: FeatureSnapshot) -> dict[str, Any]:
        features = snapshot.features
        metadata = snapshot.metadata
        close = float(metadata.get("close") or features.get("close") or 0.0)
        vwap = float(features.get("vwap", {}).get("vwap", close) if isinstance(features.get("vwap"), dict) else close)
        pressure = float(features.get("microstructure", {}).get("ms_order_flow_imbalance", 0.0) if isinstance(features.get("microstructure"), dict) else 0.0)
        score = max(-1.0, min(1.0, ((close - vwap) * 0.05) + pressure))
        return {
            "direction": 1 if score > 0.05 else -1 if score < -0.05 else 0,
            "confidence": min(0.99, 0.5 + abs(score) * 0.4),
            "uncertainty": max(0.01, 0.5 - abs(score) * 0.2),
            "backend": "synthetic_hydra_adapter",
        }


class HydraAdapter:
    """Optional wrapper around the real HYDRA inference class."""

    def __init__(self, checkpoint: str | None, symbol: str) -> None:
        self._fallback = SyntheticHydraAdapter(symbol)
        self._hydra = None
        if checkpoint and HydraInference is not None:
            self._hydra = HydraInference(checkpoint_path=checkpoint)
            log.info("hydra_checkpoint_loaded", checkpoint=checkpoint)
        else:
            log.warning("hydra_checkpoint_missing_using_synthetic_adapter", symbol=symbol)

    def predict(self, snapshot: FeatureSnapshot) -> dict[str, Any]:
        features = dict(snapshot.features)
        features.update(snapshot.metadata)
        features.setdefault("timestamp_ms", snapshot.ts_event_ns // 1_000_000)
        if self._hydra is not None:
            signal = self._hydra.process_bar(features)
            if signal is not None:
                return {
                    "direction": signal.direction,
                    "confidence": signal.confidence,
                    "uncertainty": signal.uncertainty,
                    "backend": "hydra_checkpoint",
                }
        return self._fallback.predict(snapshot)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _build_engine(symbol: str) -> FeatureEngine:
    registry = build_default_registry(primary_symbol=symbol, default_timeframe="1m")
    return FeatureEngine(
        registry=registry,
        config=FeatureEngineConfig(primary_symbol=symbol, default_timeframe="1m"),
    )


def _next_snapshot(engine: FeatureEngine, symbol: str, index: int) -> FeatureSnapshot | None:
    ts_event_ns = 1_700_000_000_000_000_000 + index * 60_000_000_000
    base = 2300.0 + (index % 47) * 0.07
    bid = base + (index % 5) * 0.01
    ask = bid + 0.10
    last = (bid + ask) / 2.0
    seq = index * 2 + 1

    engine.on_event(
        TickEvent(
            seq_no=seq,
            ts_event_ns=ts_event_ns,
            ts_receive_ns=ts_event_ns,
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            volume=1.0 + (index % 11),
            source="benchmark",
        )
    )
    snapshots = engine.on_event(
        BarCloseEvent(
            seq_no=seq + 1,
            ts_event_ns=ts_event_ns + 59_000_000_000,
            symbol=symbol,
            timeframe="1m",
            open=last - 0.08,
            high=last + 0.14,
            low=last - 0.13,
            close=last + ((index % 9) - 4) * 0.01,
            volume=100.0 + (index % 50),
            tick_count=10 + index % 10,
            vwap=None,
        )
    )
    return snapshots[-1] if snapshots else None


def run_benchmark(config: BenchmarkConfig) -> dict[str, float]:
    engine = _build_engine(config.symbol)
    hydra = HydraAdapter(config.checkpoint, config.symbol)
    timings_ms: list[float] = []
    predictions = 0

    total = config.snapshot_count + config.warmup
    log.info("inference_benchmark_started", snapshot_count=config.snapshot_count, warmup=config.warmup, symbol=config.symbol)
    started = time.perf_counter()
    for index in range(total):
        tick = time.perf_counter()
        snapshot = _next_snapshot(engine, config.symbol, index)
        if snapshot is not None:
            hydra.predict(snapshot)
        elapsed_ms = (time.perf_counter() - tick) * 1000.0
        if index >= config.warmup:
            timings_ms.append(elapsed_ms)
            predictions += 1
    wall_s = max(time.perf_counter() - started, 1e-9)

    return {
        "mean_ms": statistics.fmean(timings_ms) if timings_ms else 0.0,
        "p50_ms": _percentile(timings_ms, 0.50),
        "p95_ms": _percentile(timings_ms, 0.95),
        "p99_ms": _percentile(timings_ms, 0.99),
        "throughput": predictions / wall_s,
        "snapshots": float(predictions),
    }


@app.command()
def main(
    snapshot_count: int = typer.Option(1000, "--snapshot-count", min=1),
    warmup: int = typer.Option(100, "--warmup", min=0),
    symbol: str = typer.Option("XAUUSD", "--symbol"),
    checkpoint: str | None = typer.Option(None, "--checkpoint", help="Optional HYDRA checkpoint path."),
) -> None:
    config = BenchmarkConfig(snapshot_count=snapshot_count, warmup=warmup, symbol=symbol, checkpoint=checkpoint)
    metrics = run_benchmark(config)

    table = Table(title="DOMINION Inference Benchmark")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Snapshots", f"{int(metrics['snapshots']):,}")
    table.add_row("Mean latency", f"{metrics['mean_ms']:.3f} ms")
    table.add_row("p50 latency", f"{metrics['p50_ms']:.3f} ms")
    table.add_row("p95 latency", f"{metrics['p95_ms']:.3f} ms")
    table.add_row("p99 latency", f"{metrics['p99_ms']:.3f} ms")
    table.add_row("Throughput", f"{metrics['throughput']:.1f} snapshots/sec")
    console.print(table)
    log.info("inference_benchmark_completed", **metrics)


if __name__ == "__main__":
    app()
