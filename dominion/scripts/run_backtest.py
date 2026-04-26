#!/usr/bin/env python3
"""Run a full backtest using aphelion.backtest.engine."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DOMINION backtest runner")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--report-dir", type=Path, default=Path("reports"))
    p.add_argument("--walk-forward", action="store_true")
    p.add_argument("--monte-carlo", action="store_true")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = parse_args()

    from aphelion.backtest.engine import run as run_backtest

    args.report_dir.mkdir(parents=True, exist_ok=True)

    result = run_backtest(
        config_path=args.config,
        start=args.start,
        end=args.end,
        report_dir=args.report_dir,
        walk_forward=args.walk_forward,
        monte_carlo=args.monte_carlo,
    )

    print(f"Backtest done. Report: {args.report_dir}")
    if getattr(result, "metrics_path", None):
        print(f"Metrics: {result.metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
