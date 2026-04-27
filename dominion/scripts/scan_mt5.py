#!/usr/bin/env python3
"""
Interactive MT5 broker data downloader — uses sensible defaults for your setup.

Run this to see what accounts/symbols are available, then customize.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import MetaTrader5 as mt5
    import structlog
except ImportError as e:
    print(f"ERROR: {e}")
    print("Install with: pip install MetaTrader5 structlog")
    sys.exit(1)

log = structlog.get_logger(__name__)


def scan_mt5_setup() -> None:
    """Scan current MT5 setup and print what's available."""
    print("\n" + "=" * 70)
    print("  MT5 BROKER DATA SCANNER")
    print("=" * 70)

    if not mt5.initialize():
        print("  ✗ MT5 not running or no account logged in")
        print("    Start MT5 and log in to at least one account first.")
        sys.exit(1)

    info = mt5.account_info()
    if not info:
        print("  ✗ Could not read account info")
        sys.exit(1)

    print(f"\n  Active Account:")
    print(f"    Login:    {info.login}")
    print(f"    Broker:   {info.name}")
    print(f"    Server:   {info.server}")
    print(f"    Balance:  ${info.balance:,.0f}")
    print(f"    Equity:   ${info.equity:,.0f}")

    print(f"\n  Available Timeframes:")
    tfs = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
    print(f"    {', '.join(tfs)}")

    print(f"\n  Suggested Download:")
    print(f"    python scripts/export_mt5_all_brokers.py \\")
    print(f"        --symbols XAUUSD EURUSD GBPUSD \\")
    print(f"        --timeframes M1 M5 H1 D1 \\")
    print(f"        --days 365 \\")
    print(f"        --output data/raw")

    print(f"\n  Or download everything:")
    print(f"    python scripts/export_mt5_all_brokers.py --output data/raw")

    mt5.shutdown()
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    scan_mt5_setup()
