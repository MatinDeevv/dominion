#!/usr/bin/env python3
"""Compare two backtest result artifacts side by side."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
import typer
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table


log = structlog.get_logger(__name__)
app = typer.Typer(add_completion=False)
console = Console()

METRICS = {
    "sharpe": True,
    "sortino": True,
    "max_drawdown": False,
    "win_rate": True,
    "cagr": True,
    "total_trades": True,
}


class CompareConfig(BaseModel):
    baseline: Path = Field(...)
    candidate: Path = Field(...)


def _normalize_key(key: str) -> str:
    return key.lower().replace(" ", "_").replace("-", "_").replace("%", "pct")


def _read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".json", ".jsn"}:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict):
            return pd.DataFrame([payload])
    raise ValueError(f"Unsupported backtest artifact: {path}")


def _candidate_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    patterns = ["*metrics*.parquet", "*summary*.parquet", "*result*.parquet", "*.parquet", "*.json", "*.csv"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(path.glob(pattern)))
        if files:
            break
    return files


def load_metrics(path: Path) -> dict[str, float]:
    files = _candidate_files(path)
    if not files:
        raise FileNotFoundError(f"No readable backtest result files found under {path}")

    merged: dict[str, float] = {}
    for file in files:
        frame = _read_frame(file)
        if frame.empty:
            continue
        record: dict[str, Any] = frame.tail(1).iloc[0].to_dict()
        for key, value in record.items():
            normalized = _normalize_key(str(key))
            if normalized in {"max_drawdown_pct", "max_dd", "drawdown"}:
                normalized = "max_drawdown"
            elif normalized in {"cagr_pct", "annual_return", "annualized_return"}:
                normalized = "cagr"
            elif normalized in {"trades", "n_trades", "trade_count"}:
                normalized = "total_trades"
            if normalized in METRICS and pd.notna(value):
                merged[normalized] = float(value)
    return merged


def _delta_style(metric: str, baseline: float, candidate: float) -> str:
    higher_is_better = METRICS[metric]
    improved = candidate >= baseline if higher_is_better else candidate <= baseline
    return "green" if improved else "red"


@app.command()
def main(
    baseline: Path = typer.Option(..., "--baseline", exists=True, readable=True),
    candidate: Path = typer.Option(..., "--candidate", exists=True, readable=True),
) -> None:
    config = CompareConfig(baseline=baseline, candidate=candidate)
    baseline_metrics = load_metrics(config.baseline)
    candidate_metrics = load_metrics(config.candidate)
    log.info("backtest_results_loaded", baseline=str(baseline), candidate=str(candidate))

    table = Table(title="Backtest Comparison")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Delta", justify="right")

    for metric in METRICS:
        base = baseline_metrics.get(metric, 0.0)
        cand = candidate_metrics.get(metric, 0.0)
        delta = cand - base
        style = _delta_style(metric, base, cand)
        table.add_row(metric, f"{base:.4f}", f"{cand:.4f}", f"[{style}]{delta:+.4f}[/{style}]")

    console.print(table)


if __name__ == "__main__":
    app()
