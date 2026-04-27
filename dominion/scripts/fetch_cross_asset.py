"""
Fetch cross-asset data for HYDRA features via yfinance.

Downloads M5-resolution context series when Yahoo makes that interval
available. The feature builder is also importable by dataset scripts and
joins downloaded series to M5 bar timestamps with a backward as-of join.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import polars as pl
import structlog

log = structlog.get_logger(__name__)

TICKERS = {
    "DXY": "DX-Y.NYB",
    "SILVER": "SI=F",
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "SP500": "^GSPC",
}

FEATURE_COLUMNS = ["ret_1", "ret_5", "ret_12", "zscore_50", "rsi_14"]
INTERVAL_FALLBACKS = ("5m", "1h", "1d")


def _ensure_yfinance():
    try:
        import yfinance as yf

        return yf
    except ImportError:
        print("Installing yfinance...")
        subprocess.run(["pip", "install", "yfinance", "--quiet"], check=True)
        import yfinance as yf

        return yf


def _download_with_fallbacks(yf, symbol: str, from_date: str, to_date: str):
    for interval in INTERVAL_FALLBACKS:
        df = yf.download(
            symbol,
            start=from_date,
            end=to_date,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if not df.empty:
            return df, interval
        log.warning("cross_asset_interval_empty", ticker=symbol, interval=interval)
    return df, INTERVAL_FALLBACKS[-1]


def fetch_and_save(name: str, symbol: str, from_date: str, to_date: str, output: Path) -> bool:
    """Fetch one cross-asset series and save engineered M5 features."""

    try:
        yf = _ensure_yfinance()
        df, interval = _download_with_fallbacks(yf, symbol, from_date, to_date)
        if df.empty:
            log.warning("cross_asset_empty", asset=name, ticker=symbol)
            return False

        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = [str(col[0]).lower() for col in df.columns]
        else:
            df.columns = [str(col).lower() for col in df.columns]

        if "close" not in df.columns:
            log.warning("cross_asset_close_missing", asset=name, ticker=symbol)
            return False

        df = df[["close"]].copy()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df["time_ms"] = df.index.astype("int64") // 1_000_000

        pl_df = pl.from_pandas(df.reset_index(drop=True)).select(
            pl.col("time_ms").cast(pl.Int64),
            pl.col("close").cast(pl.Float64),
        )

        close = pl.col("close")
        pl_df = pl_df.with_columns(
            [
                ((close - close.shift(1)) / (close.shift(1) + 1e-10)).alias("ret_1"),
                ((close - close.shift(5)) / (close.shift(5) + 1e-10)).alias("ret_5"),
                ((close - close.shift(12)) / (close.shift(12) + 1e-10)).alias("ret_12"),
                ((close - close.rolling_mean(50)) / (close.rolling_std(50) + 1e-10)).alias(
                    "zscore_50"
                ),
                close.ewm_mean(span=14).alias("ema_14"),
            ]
        )

        delta = close.diff(1)
        gain = pl.when(delta > 0).then(delta).otherwise(0.0)
        loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
        rsi = 100.0 - 100.0 / (1.0 + gain.ewm_mean(span=14) / (loss.ewm_mean(span=14) + 1e-10))
        pl_df = (
            pl_df.with_columns(rsi.alias("rsi_14"))
            .fill_null(0.0)
            .fill_nan(0.0)
            .with_columns(pl.col("time_ms").cast(pl.Int64, strict=False))
        )

        output.mkdir(parents=True, exist_ok=True)
        out = output / f"{name}_M5.parquet"
        pl_df.write_parquet(out)
        log.info("cross_asset_saved", asset=name, rows=len(pl_df), interval=interval, path=str(out))
        return True
    except Exception as exc:
        log.error("cross_asset_failed", asset=name, ticker=symbol, error=str(exc))
        return False


def build_cross_asset_feature_block(
    m5_timestamps_ms: np.ndarray,
    cross_asset_dir: Path,
) -> pl.DataFrame:
    """
    Join all cross-asset series to M5 bar timestamps via as-of join.

    Returns a DataFrame with one row per M5 bar. All joined columns are
    prefixed by asset name, and missing assets are represented by zero-filled
    feature columns so downstream tensors keep a stable shape.
    """

    result = pl.DataFrame({"time_ms": pl.Series(m5_timestamps_ms, dtype=pl.Int64)}).sort("time_ms")

    for name in TICKERS:
        fpath = Path(cross_asset_dir) / f"{name}_M5.parquet"
        prefix = name.lower()
        if not fpath.exists():
            log.warning("missing_cross_asset", asset=name, path=str(fpath))
            result = result.with_columns(
                [pl.lit(0.0).cast(pl.Float64).alias(f"{prefix}_{col}") for col in FEATURE_COLUMNS]
            )
            continue

        df = pl.read_parquet(fpath).with_columns(pl.col("time_ms").cast(pl.Int64, strict=False)).sort("time_ms")
        rename = {col: f"{prefix}_{col}" for col in df.columns if col != "time_ms"}
        df = df.rename(rename)
        result = result.join_asof(df, on="time_ms", strategy="backward")

    if "dxy_ret_1" in result.columns:
        result = result.with_columns(
            [
                (-pl.col("dxy_ret_1")).alias("dxy_inverse_1"),
                (-pl.col("dxy_ret_5")).alias("dxy_inverse_5"),
            ]
        )

    if "dxy_ret_1" in result.columns and "silver_ret_1" in result.columns:
        result = result.with_columns(
            (pl.col("silver_ret_1") - pl.col("dxy_ret_1")).alias("silver_dxy_spread")
        )

    if "vix_zscore_50" in result.columns:
        result = result.with_columns((pl.col("vix_zscore_50") > 1.5).cast(pl.Float64).alias("vix_spike"))

    return result.fill_null(0.0).fill_nan(0.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default="2022-01-01")
    parser.add_argument("--to-date", default="2026-04-01")
    parser.add_argument("--output", default="data/processed/cross_asset")
    args = parser.parse_args()

    output = Path(args.output)
    results = {}
    for name, ticker in TICKERS.items():
        log.info("cross_asset_fetching", asset=name, ticker=ticker)
        results[name] = fetch_and_save(name, ticker, args.from_date, args.to_date, output)

    print(f"\nCross-asset data -> {output}")
    for name, ok in results.items():
        print(f"  {name:8s}  {'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
