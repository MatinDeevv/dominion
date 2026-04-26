#!/usr/bin/env python3
"""Materialize the feature engine over stored bars → FeatureSnapshot parquet set.

Replaces the feature-build section of the retired `aphelion_data.py` monolith.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import structlog

log = structlog.get_logger("dominion.build_features")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay bars through aphelion.feature_engine")
    p.add_argument("--config", type=Path, required=True, help="Strategy YAML config")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--bars-root", type=Path, default=Path("data/bars"))
    p.add_argument("--out", type=Path, default=Path("data/features"))
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--workers", type=int, default=1)
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = parse_args()

    from aphelion.feature_engine.integrations.mt5pipe import run_replay

    log.info("build_features.start", config=str(args.config), symbol=args.symbol)

    result = run_replay(
        config_path=args.config,
        symbol=args.symbol,
        bars_root=args.bars_root,
        out_dir=args.out,
        start=args.start,
        end=args.end,
        workers=args.workers,
    )

    log.info(
        "build_features.done",
        snapshots_written=getattr(result, "snapshots_written", None),
        duration_s=getattr(result, "duration_s", None),
        out=str(args.out),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
