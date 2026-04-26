#!/usr/bin/env python3
"""Ingest all historical MT5 data (ticks + bars) via mt5pipe.backfill.

Replaces the fetch section of the retired `aphelion_data.py` monolith.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

log = structlog.get_logger("dominion.fetch_all")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill ticks+bars via mt5pipe")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--end", default=None, help="ISO date or None = now")
    p.add_argument("--storage", type=Path, default=Path("data"))
    p.add_argument("--timeframes", default="M1,M5,M15,H1,H4,D1")
    p.add_argument("--resume", action="store_true", help="Skip existing files")
    p.add_argument("--no-ticks", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    from mt5pipe.cli.app import app as mt5pipe_app  # lazy import

    argv = [
        "backfill",
        "--symbol",
        args.symbol,
        "--start",
        args.start,
        "--storage",
        str(args.storage),
        "--timeframes",
        args.timeframes,
    ]
    if args.end:
        argv += ["--end", args.end]
    if args.resume:
        argv.append("--resume")
    if args.no_ticks:
        argv.append("--no-ticks")

    log.info("fetch_all.start", args=vars(args))
    try:
        mt5pipe_app(argv, standalone_mode=False)
    except SystemExit as exit_exc:
        return int(exit_exc.code or 0)
    log.info("fetch_all.done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
