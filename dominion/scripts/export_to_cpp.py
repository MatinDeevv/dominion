"""
Export mt5pipe bars to C++ engine format.

Usage:
    python scripts/export_to_cpp.py \
        --mt5pipe-root "C:\\Users\\marti\\AppData\\Local\\Aphelion\\data" \
        --cpp-data-root "C:\\Users\\marti\\LLM\\data_sim_ready" \
        --symbol XAUUSD \
        --broker-id your_broker_id \
        --timeframes H1 H4 D1

Run this after every mt5pipe backfill. It's fast - just reads Parquet,
renames one column, and writes a single flat file per timeframe.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
import structlog

from mt5pipe.export.cpp_exporter import export_all_timeframes_for_cpp

app = typer.Typer()
log = structlog.get_logger(__name__)


@app.command()
def main(
    mt5pipe_root: Path = typer.Option(..., help="mt5pipe storage root"),
    cpp_data_root: Path = typer.Option(..., help="C++ data root (data_sim_ready)"),
    symbol: str = typer.Option("XAUUSD"),
    broker_id: str = typer.Option(..., help="Broker ID used in mt5pipe backfill"),
    timeframes: list[str] = typer.Option(["H1"], help="Timeframes to export (repeatable)"),
    date_from: date | None = typer.Option(None, help="Start date filter YYYY-MM-DD"),
    date_to: date | None = typer.Option(None, help="End date filter YYYY-MM-DD"),
    overwrite: bool = typer.Option(False, help="Overwrite existing exports"),
    all_timeframes: bool = typer.Option(False, help="Auto-discover and export all timeframes"),
) -> None:

    tfs = None if all_timeframes else timeframes

    log.info(
        "export_start",
        symbol=symbol,
        broker_id=broker_id,
        timeframes=tfs or "all",
        mt5pipe_root=str(mt5pipe_root),
        cpp_data_root=str(cpp_data_root),
    )

    results = export_all_timeframes_for_cpp(
        mt5pipe_root=mt5pipe_root,
        cpp_data_root=cpp_data_root,
        symbol=symbol,
        broker_id=broker_id,
        timeframes=tfs,
        date_from=date_from,
        date_to=date_to,
        overwrite=overwrite,
    )

    if not results:
        typer.echo("No timeframes exported. Check that mt5pipe backfill has run.", err=True)
        raise typer.Exit(1)

    typer.echo(f"\nExported {len(results)} timeframe(s) for {symbol}:")
    for tf, path in sorted(results.items()):
        size_mb = round(path.stat().st_size / 1_048_576, 2)
        typer.echo(f"  {tf:6s}  ->  {path}  ({size_mb} MB)")

    typer.echo(f"\nC++ data root: {cpp_data_root}")
    typer.echo("Ready to run: aphelion.exe --data-root <cpp_data_root> --symbol XAUUSD")


if __name__ == "__main__":
    app()
