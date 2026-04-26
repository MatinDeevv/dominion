"""Unified CLI entry point for the merged APHELION runtime."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from aphelion.app import Aphelion, AphelionConfig


app = typer.Typer(no_args_is_help=True, help="Unified APHELION trading runtime.")
config_app = typer.Typer(help="Configuration helpers.")
app.add_typer(config_app, name="config")


def _load_runtime(config_path: Path) -> Aphelion:
    return Aphelion.from_yaml(config_path)


def _emit(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


@app.command()
def status(
    config: Path = typer.Option(Path("config/backtest.yaml"), exists=True, readable=True, help="Config file path."),
) -> None:
    """Show runtime status for the selected config."""
    runtime = _load_runtime(config)
    _emit(runtime.status())


@app.command()
def backtest(
    config: Path = typer.Option(Path("config/backtest.yaml"), exists=True, readable=True, help="Config file path."),
) -> None:
    """Replay MT5Pipe data through the event-driven supersystem."""
    runtime = _load_runtime(config)
    result = asyncio.run(runtime.run_backtest())
    _emit(
        {
            "snapshots_processed": result.snapshots_processed,
            "features_emitted": result.features_emitted,
            "signals_generated": result.signals_generated,
            "decisions_published": result.decisions_published,
            "fills": result.fills,
            "closed_positions": result.closed_positions,
            "final_equity": result.final_equity,
            "event_bus_stats": result.event_bus_stats,
        }
    )


@app.command()
def paper(
    config: Path = typer.Option(Path("config/paper.yaml"), exists=True, readable=True, help="Config file path."),
) -> None:
    """Run the merged paper-trading stack."""
    runtime = _load_runtime(config)
    result = asyncio.run(runtime.run_paper())
    summary = result.summary() if hasattr(result, "summary") else str(result)
    typer.echo(summary)


@app.command()
def live(
    config: Path = typer.Option(Path("config/live.yaml"), exists=True, readable=True, help="Config file path."),
) -> None:
    """Run the live-mode stack using MT5 settings from config."""
    runtime = _load_runtime(config)
    result = asyncio.run(runtime.run_live())
    summary = result.summary() if hasattr(result, "summary") else str(result)
    typer.echo(summary)


@config_app.command("validate")
def validate_config(
    config: Path = typer.Option(Path("config/backtest.yaml"), exists=True, readable=True, help="Config file path."),
) -> None:
    """Load and validate a config file."""
    loaded = AphelionConfig.from_yaml(config)
    _emit(
        {
            "config_path": str(config.resolve()),
            "valid": True,
            "summary": loaded.summary(),
        }
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
