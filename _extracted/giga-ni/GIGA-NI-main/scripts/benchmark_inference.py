from __future__ import annotations

import argparse
import time
from pathlib import Path

from aphelion.feature_engine.defaults import build_default_registry
from aphelion.feature_engine.engine import FeatureEngine, FeatureEngineConfig
from aphelion.feature_engine.events import BarCloseEvent, TickEvent


def run_benchmark(samples: int) -> tuple[float, float, float]:
    registry = build_default_registry(primary_symbol="XAUUSD", default_timeframe="1m")
    engine = FeatureEngine(
        registry=registry,
        config=FeatureEngineConfig(primary_symbol="XAUUSD", default_timeframe="1m"),
    )

    seq_no = 0
    base_ns = 1_700_000_000_000_000_000
    timings_ms: list[float] = []

    for index in range(samples):
        seq_no += 1
        ts_event_ns = base_ns + index * 1_000_000_000
        bid = 2000.0 + (index % 17) * 0.01
        ask = bid + 0.10
        last = (bid + ask) / 2.0

        engine.on_event(
            TickEvent(
                seq_no=seq_no,
                ts_event_ns=ts_event_ns,
                ts_receive_ns=ts_event_ns,
                symbol="XAUUSD",
                bid=bid,
                ask=ask,
                last=last,
                volume=1.0,
                source="benchmark",
            )
        )

        seq_no += 1
        start = time.perf_counter()
        engine.on_event(
            BarCloseEvent(
                seq_no=seq_no,
                ts_event_ns=ts_event_ns + 500_000_000,
                symbol="XAUUSD",
                timeframe="1m",
                open=last - 0.05,
                high=last + 0.10,
                low=last - 0.10,
                close=last + 0.02,
                volume=100.0,
                tick_count=10,
                vwap=None,
            )
        )
        timings_ms.append((time.perf_counter() - start) * 1000.0)

    avg_latency = sum(timings_ms) / len(timings_ms)
    return avg_latency, max(timings_ms), min(timings_ms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark feature-engine inference latency.")
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    avg_latency, max_latency, min_latency = run_benchmark(args.samples)
    args.output.write_text(
        "\n".join(
            [
                f"Average latency: {avg_latency:.2f}ms",
                f"Max latency: {max_latency:.2f}ms",
                f"Min latency: {min_latency:.2f}ms",
                f"Samples: {args.samples}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Average latency: {avg_latency:.2f}ms")
    print(f"Max latency: {max_latency:.2f}ms")
    print(f"Min latency: {min_latency:.2f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
