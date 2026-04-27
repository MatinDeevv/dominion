"""
Multi-broker MT5 data exporter — download all bars from all open accounts.

Usage:
    python scripts/export_mt5_all_brokers.py \
        --output data/raw \
        --timeframes M1 M5 M15 H1 H4 D1 W1 MN1 \
        --symbols XAUUSD EURUSD GBPUSD USDJPY \
        --days 365

This will:
1. Find all open MT5 accounts on your PC
2. Connect to each broker sequentially
3. Download specified symbols/timeframes
4. Save as Parquet with broker + symbol + timeframe partitioning
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import structlog

log = structlog.get_logger(__name__)

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None
    log.warning("MetaTrader5 not installed — install with: pip install MetaTrader5")


# ═══════════════════════════════════════════════════════════════
#  MT5 CONNECTION MANAGEMENT
# ═══════════════════════════════════════════════════════════════


def get_all_mt5_accounts() -> list[dict]:
    """
    Find all open MT5 terminals on this PC.
    Returns list of {account, login, server, balance, ...}
    """
    if mt5 is None:
        raise ImportError("MetaTrader5 required")

    accounts = []
    try:
        # Initialize without specifying path — uses default MT5 installation
        if not mt5.initialize():
            log.warning("mt5_init_failed", error=mt5.last_error())
            return []

        # Get current account info
        info = mt5.account_info()
        if info:
            accounts.append(
                {
                    "account": info.login,
                    "login": info.login,
                    "server": info.server,
                    "broker": info.name,
                    "balance": info.balance,
                    "equity": info.equity,
                }
            )
            log.info("mt5_account_found", login=info.login, server=info.server)
        else:
            log.warning("mt5_account_info_failed", error=mt5.last_error())

        mt5.shutdown()
    except Exception as e:
        log.error("mt5_scan_error", error=str(e))

    return accounts


def download_symbol_timeframe(
    symbol: str,
    timeframe_str: str,
    days: int,
    path: Path,
    broker_id: str,
) -> int:
    """
    Download all bars for symbol/timeframe over last N days.
    Save as Parquet. Return bar count.
    """
    if mt5 is None:
        return 0

    try:
        if not mt5.initialize():
            log.warning("mt5_init_failed", symbol=symbol, timeframe=timeframe_str)
            return 0

        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
        if timeframe_str not in tf_map:
            log.warning("unknown_timeframe", timeframe=timeframe_str)
            return 0

        tf = tf_map[timeframe_str]

        # Download bars
        utc_from = datetime.utcnow() - timedelta(days=days)
        rates = mt5.copy_rates_from(symbol, tf, utc_from, 100000)

        if rates is None or len(rates) == 0:
            log.warning(
                "no_bars_downloaded",
                symbol=symbol,
                timeframe=timeframe_str,
                error=mt5.last_error(),
            )
            mt5.shutdown()
            return 0

        # Convert to DataFrame
        df = pl.DataFrame(rates)
        df = df.with_columns(
            [
                (pl.col("time") * 1000).alias("time_ms"),
                pl.lit(symbol).alias("symbol"),
                pl.lit(timeframe_str).alias("timeframe"),
                pl.lit(broker_id).alias("broker_id"),
            ]
        )

        # Output path: {root}/broker={id}/symbol={sym}/timeframe={tf}/data.parquet
        out_dir = (
            path
            / f"broker={broker_id}"
            / f"symbol={symbol}"
            / f"timeframe={timeframe_str}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "data.parquet"

        df.write_parquet(out_file, compression="snappy")

        log.info(
            "bars_downloaded",
            symbol=symbol,
            timeframe=timeframe_str,
            count=len(rates),
            size_mb=round(out_file.stat().st_size / 1e6, 2),
            path=str(out_file),
        )

        mt5.shutdown()
        return len(rates)

    except Exception as e:
        log.error(
            "download_error",
            symbol=symbol,
            timeframe=timeframe_str,
            error=str(e),
        )
        try:
            mt5.shutdown()
        except Exception:
            pass
        return 0


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser("Multi-broker MT5 exporter")
    parser.add_argument(
        "--output",
        default="data/raw",
        help="Output directory for Parquet files",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["M1", "M5", "M15", "H1", "H4", "D1"],
        help="Timeframes to export",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"],
        help="Symbols to export",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Days of history to download",
    )
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info(
        "export_start",
        output=str(out_dir),
        symbols=args.symbols,
        timeframes=args.timeframes,
        days=args.days,
    )

    if mt5 is None:
        log.error("mt5_not_available")
        return

    # Find all open accounts
    accounts = get_all_mt5_accounts()
    if not accounts:
        log.warning("no_mt5_accounts_found")
        return

    log.info("found_accounts", count=len(accounts))

    # Download from each account
    total_bars = 0
    for acc in accounts:
        broker_id = acc["broker"].replace(" ", "_").lower()
        log.info("processing_account", login=acc["login"], broker=broker_id)

        for symbol in args.symbols:
            for timeframe in args.timeframes:
                bars = download_symbol_timeframe(
                    symbol, timeframe, args.days, out_dir, broker_id
                )
                total_bars += bars

    # Summary
    log.info(
        "export_complete",
        total_bars=total_bars,
        output=str(out_dir),
        accounts=len(accounts),
        symbols=len(args.symbols),
        timeframes=len(args.timeframes),
    )

    print("\n" + "═" * 60)
    print(f"  Downloaded {total_bars:,} bars from {len(accounts)} broker(s)")
    print(f"  Saved to: {out_dir}")
    print("═" * 60)


if __name__ == "__main__":
    main()
