"""Runtime configuration models for the unified APHELION entry point."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_expand_env(item) for item in value)
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


class _BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)


class BacktestRuntimeConfig(_BaseConfigModel):
    mt5pipe_root: Path = Path("..")
    primary_symbol: str | None = None
    start_date: date = date(2026, 1, 1)
    end_date: date = date(2026, 1, 31)
    tick_symbols: tuple[str, ...] = ()
    bar_symbols: tuple[str, ...] = ()
    bar_timeframes: tuple[str, ...] = ("M1", "M15", "H1")
    storage_root: Path | None = None
    pipeline_config_path: Path | None = None
    event_journal_path: Path | None = None
    snapshot_journal_path: Path | None = None
    include_inferred_sessions: bool = True
    emit_tick_snapshots: bool = False
    include_btc: bool = False
    initial_capital: float = 10_000.0


class PaperRuntimeConfig(_BaseConfigModel):
    mode: Literal["live", "replay", "mt5_tick"] = "live"
    initial_capital: float = 10_000.0
    symbol: str | None = None
    hydra_checkpoint: str = ""
    warmup_bars: int = 200
    enable_tui: bool = True
    poll_interval_ms: int = 100
    verbose: bool = False


class MT5RuntimeConfig(_BaseConfigModel):
    login: int | None = None
    password: str = ""
    server: str = ""
    terminal_path: str = ""
    timeout_ms: int = 10_000
    retry_attempts: int = 3
    retry_delay_seconds: float = 5.0


class AphelionConfig(_BaseConfigModel):
    timezone: str = "UTC"
    execution_mode: Literal["backtest", "paper", "live"] = "backtest"
    symbol: str = "XAUUSD"
    backtest: BacktestRuntimeConfig = Field(default_factory=BacktestRuntimeConfig)
    paper: PaperRuntimeConfig = Field(default_factory=PaperRuntimeConfig)
    mt5: MT5RuntimeConfig = Field(default_factory=MT5RuntimeConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AphelionConfig":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Config file must contain a mapping at the root: {config_path}")
        data = payload.get("aphelion", payload)
        if not isinstance(data, dict):
            raise ValueError(f"Config file must contain a mapping under 'aphelion': {config_path}")
        return cls.model_validate(_expand_env(data))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AphelionConfig":
        data = payload.get("aphelion", payload)
        if not isinstance(data, dict):
            raise ValueError("Config payload must be a mapping.")
        return cls.model_validate(_expand_env(data))

    def summary(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode,
            "symbol": self.symbol,
            "timezone": self.timezone,
            "backtest": {
                "primary_symbol": self.backtest.primary_symbol or self.symbol,
                "start_date": self.backtest.start_date.isoformat(),
                "end_date": self.backtest.end_date.isoformat(),
                "bar_timeframes": list(self.backtest.bar_timeframes),
            },
            "paper": {
                "mode": self.paper.mode,
                "symbol": self.paper.symbol or self.symbol,
                "enable_tui": self.paper.enable_tui,
                "warmup_bars": self.paper.warmup_bars,
            },
        }


__all__ = [
    "AphelionConfig",
    "BacktestRuntimeConfig",
    "MT5RuntimeConfig",
    "PaperRuntimeConfig",
]
