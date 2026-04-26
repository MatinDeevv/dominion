#!/usr/bin/env python3
"""Backfill MT5 historical bars into the canonical parquet store."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import structlog
import typer
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from mt5pipe.config.loader import load_config
from mt5pipe.ingestion.history import fetch_history_bars, store_history_bars_by_date
from mt5pipe.mt5.connection import MT5Connection
from mt5pipe.quality.gaps import detect_gaps
from mt5pipe.storage.parquet_store import ParquetStore
from mt5pipe.storage.paths import StoragePaths


log = structlog.get_logger(__name__)
app = typer.Typer(add_completion=False)
console = Console()
TIMEFRAME_SECONDS = {
    "M1": 60,
    "M2": 120,
    "M3": 180,
    "M4": 240,
    "M5": 300,
    "M6": 360,
    "M10": 600,
    "M12": 720,
    "M15": 900,
    "M20": 1200,
    "M30": 1800,
    "H1": 3600,
    "H2": 7200,
    "H3": 10800,
    "H4": 14400,
    "H6": 21600,
    "H8": 28800,
    "H12": 43200,
    "D1": 86400,
}


class BackfillConfig(BaseModel):
    symbol: str = Field(default="XAUUSD", min_length=1)
    timeframe: str = Field(default="M1", min_length=1)
    date_from: dt.date
    date_to: dt.date
    broker_config: Path


def _utc_bounds(start: dt.date, end: dt.date) -> tuple[dt.datetime, dt.datetime]:
    return (
        dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc),
        dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc),
    )


@app.command()
def main(
    symbol: str = typer.Option("XAUUSD", "--symbol"),
    timeframe: str = typer.Option("M1", "--timeframe"),
    date_from: dt.date = typer.Option(..., "--from", formats=["%Y-%m-%d"]),
    date_to: dt.date = typer.Option(dt.date.today(), "--to", formats=["%Y-%m-%d"]),
    broker_config: Path = typer.Option(Path("config/pipeline.yaml"), "--broker-config", exists=True, readable=True),
) -> None:
    config = BackfillConfig(symbol=symbol, timeframe=timeframe, date_from=date_from, date_to=date_to, broker_config=broker_config)
    pipeline = load_config(config.broker_config)
    broker_id = pipeline.broker_ids()[0]
    broker = pipeline.get_broker(broker_id)
    paths = StoragePaths(pipeline.storage.root)
    store = ParquetStore(pipeline.storage.compression, pipeline.storage.parquet_row_group_size)
    start_dt, end_dt = _utc_bounds(config.date_from, config.date_to)

    log.info("history_backfill_started", symbol=symbol, timeframe=timeframe, broker=broker_id, date_from=str(date_from), date_to=str(date_to))
    with MT5Connection(broker).connect() as conn:
        frame = fetch_history_bars(conn, symbol, timeframe, start_dt, end_dt)

    written = store_history_bars_by_date(frame, broker_id, symbol, timeframe, paths, store)
    gap_report = (
        detect_gaps(frame, timeframe, TIMEFRAME_SECONDS[timeframe.upper()])
        if not frame.is_empty()
        else None
    )
    gap_count = len(gap_report.gaps) if gap_report is not None else 0
    storage_path = paths.native_bars_dir(broker_id, symbol, timeframe, date_from).parent

    table = Table(title="MT5 History Backfill")
    table.add_column("Field")
    table.add_column("Value", justify="right")
    table.add_row("Broker", broker_id)
    table.add_row("Symbol", symbol)
    table.add_row("Timeframe", timeframe)
    table.add_row("Bars fetched", f"{len(frame):,}")
    table.add_row("Rows written", f"{written:,}")
    table.add_row("Gaps detected", f"{gap_count:,}")
    table.add_row("Storage path", str(storage_path))
    console.print(table)
    log.info("history_backfill_completed", bars_fetched=len(frame), rows_written=written, gap_count=gap_count, storage_path=str(storage_path))


if __name__ == "__main__":
    app()
