#!/usr/bin/env python3
"""Validate stored bar/tick coverage for a dataset range."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import structlog
import typer
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from mt5pipe.storage.parquet_store import ParquetStore


log = structlog.get_logger(__name__)
app = typer.Typer(add_completion=False)
console = Console()

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M4": 4,
    "M5": 5,
    "M6": 6,
    "M10": 10,
    "M12": 12,
    "M15": 15,
    "M20": 20,
    "M30": 30,
    "H1": 60,
    "H2": 120,
    "H3": 180,
    "H4": 240,
    "H6": 360,
    "H8": 480,
    "H12": 720,
    "D1": 1440,
}


class CoverageConfig(BaseModel):
    dataset: Path
    symbol: str = Field(..., min_length=1)
    date_from: dt.date
    date_to: dt.date
    timeframe: str = Field(..., min_length=1)


def _time_column(frame: pl.DataFrame) -> str:
    for column in ("time_utc", "bar_start", "timestamp", "ts_utc", "time"):
        if column in frame.columns:
            return column
    raise ValueError("Dataset has no recognizable timestamp column.")


def _load_dataset(path: Path) -> pl.DataFrame:
    store = ParquetStore()
    if path.is_file():
        return store.read(path)
    return store.read_dir(path)


def _expected_count(date_from: dt.date, date_to: dt.date, timeframe: str) -> int:
    minutes = TIMEFRAME_MINUTES.get(timeframe.upper())
    if minutes is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    start = dt.datetime.combine(date_from, dt.time.min, tzinfo=dt.timezone.utc)
    end = dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    return int((end - start).total_seconds() // (minutes * 60))


def _filter_frame(frame: pl.DataFrame, config: CoverageConfig) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    time_col = _time_column(frame)
    start = dt.datetime.combine(config.date_from, dt.time.min, tzinfo=dt.timezone.utc)
    end = dt.datetime.combine(config.date_to + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    filtered = frame
    if "symbol" in filtered.columns:
        filtered = filtered.filter(pl.col("symbol") == config.symbol)
    if "timeframe" in filtered.columns:
        filtered = filtered.filter(pl.col("timeframe").str.to_uppercase() == config.timeframe.upper())
    return filtered.filter((pl.col(time_col) >= start) & (pl.col(time_col) < end)).sort(time_col)


def _gap_locations(frame: pl.DataFrame, timeframe: str) -> list[str]:
    if frame.is_empty():
        return []
    time_col = _time_column(frame)
    minutes = TIMEFRAME_MINUTES[timeframe.upper()]
    times = frame[time_col].to_list()
    gaps: list[str] = []
    for previous, current in zip(times, times[1:]):
        delta = current - previous
        if delta > dt.timedelta(minutes=minutes * 1.5):
            gaps.append(f"{previous.isoformat()} -> {current.isoformat()}")
    return gaps


@app.command()
def main(
    dataset: Path = typer.Option(..., "--dataset", exists=True, readable=True),
    symbol: str = typer.Option(..., "--symbol"),
    date_from: dt.date = typer.Option(..., "--from", formats=["%Y-%m-%d"]),
    date_to: dt.date = typer.Option(..., "--to", formats=["%Y-%m-%d"]),
    timeframe: str = typer.Option(..., "--timeframe"),
) -> None:
    config = CoverageConfig(dataset=dataset, symbol=symbol, date_from=date_from, date_to=date_to, timeframe=timeframe)
    frame = _filter_frame(_load_dataset(dataset), config)
    expected = _expected_count(date_from, date_to, timeframe)
    actual = len(frame)
    coverage = (actual / expected * 100.0) if expected else 0.0
    gaps = _gap_locations(frame, timeframe)

    table = Table(title="Dataset Coverage")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Expected bars", f"{expected:,}")
    table.add_row("Actual bars", f"{actual:,}")
    table.add_row("Gap count", f"{len(gaps):,}")
    table.add_row("Coverage", f"{coverage:.2f}%")
    if gaps:
        table.add_row("First gaps", "\n".join(gaps[:5]))
    console.print(table)
    log.info("coverage_validated", expected=expected, actual=actual, gap_count=len(gaps), coverage_pct=coverage)

    if coverage < 95.0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
