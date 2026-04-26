"""Unified runtime entry point for the merged APHELION workspace."""

from __future__ import annotations

import importlib.util
import platform
from pathlib import Path
from typing import Any

from aphelion.app_config import AphelionConfig
from aphelion.feature_engine.integrations.mt5pipe import MT5PipeReplayConfig
from aphelion.integrations.supersystem import EventDrivenReplayResult, EventDrivenSuperSystem
from aphelion.integrations.supersystem.execution_bridge import SuperExecutionStack


class Aphelion:
    """Facade over the merged backtest, paper, and live entry points."""

    def __init__(
        self,
        config: AphelionConfig,
        *,
        config_path: str | Path | None = None,
        backtest_runtime: EventDrivenSuperSystem | None = None,
    ) -> None:
        self.config = config
        self.config_path = None if config_path is None else Path(config_path).resolve()
        self._config_dir = self.config_path.parent if self.config_path else Path.cwd()
        self._backtest_runtime = backtest_runtime
        self._started = False

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Aphelion":
        config_path = Path(path)
        return cls(AphelionConfig.from_yaml(config_path), config_path=config_path)

    async def __aenter__(self) -> "Aphelion":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        if self._backtest_runtime is not None:
            await self._backtest_runtime.stop()
        self._started = False

    async def run_backtest(self) -> EventDrivenReplayResult:
        runtime = self._ensure_backtest_runtime()
        replay_config = self._build_replay_config()
        return await runtime.replay(replay_config)

    async def run_paper(self) -> Any:
        from aphelion.paper.feed import FeedConfig, FeedMode
        from aphelion.paper.runner import PaperRunner, PaperRunnerConfig
        from aphelion.paper.session import PaperSessionConfig
        from aphelion.risk.sentinel.execution.mt5 import MT5Config

        mode_map = {
            "live": FeedMode.LIVE,
            "replay": FeedMode.REPLAY,
            "mt5_tick": FeedMode.MT5_TICK,
        }
        paper_symbol = self.config.paper.symbol or self.config.symbol
        runner = PaperRunner(
            PaperRunnerConfig(
                feed_mode=mode_map[self.config.paper.mode],
                mt5_config=MT5Config(
                    terminal_path=self.config.mt5.terminal_path,
                    login=self.config.mt5.login or 0,
                    password=self.config.mt5.password,
                    server=self.config.mt5.server,
                    symbol=paper_symbol,
                    timeout_ms=self.config.mt5.timeout_ms,
                    retry_attempts=self.config.mt5.retry_attempts,
                    retry_delay_seconds=self.config.mt5.retry_delay_seconds,
                ),
                feed_config=FeedConfig(
                    symbol=paper_symbol,
                    poll_interval_ms=self.config.paper.poll_interval_ms,
                    warmup_bars=self.config.paper.warmup_bars,
                ),
                session_config=PaperSessionConfig(
                    initial_capital=self.config.paper.initial_capital,
                    symbol=paper_symbol,
                    hydra_checkpoint=self._resolve_optional_str_path(self.config.paper.hydra_checkpoint),
                    warmup_bars=max(64, self.config.paper.warmup_bars),
                ),
                enable_tui=self.config.paper.enable_tui,
            )
        )
        return await runner.run()

    async def run_live(self) -> Any:
        self.config.execution_mode = "live"
        self.config.paper.mode = "live"
        return await self.run_paper()

    def status(self) -> dict[str, Any]:
        status = {
            "execution_mode": self.config.execution_mode,
            "symbol": self.config.symbol,
            "timezone": self.config.timezone,
            "config_path": str(self.config_path) if self.config_path else None,
            "workspace_root": str(Path.cwd()),
            "python_platform": platform.platform(),
            "torch_available": importlib.util.find_spec("torch") is not None,
            "metatrader5_available": importlib.util.find_spec("MetaTrader5") is not None,
            "backtest_root": str(self._resolve_path(self.config.backtest.mt5pipe_root)),
            "paper_mode": self.config.paper.mode,
            "paper_symbol": self.config.paper.symbol or self.config.symbol,
        }
        if self._backtest_runtime is not None:
            status["event_bus_stats"] = self._backtest_runtime.event_bus.stats
            status["equity"] = self._backtest_runtime.execution_stack.portfolio.equity
        return status

    def _ensure_backtest_runtime(self) -> EventDrivenSuperSystem:
        if self._backtest_runtime is None:
            self._backtest_runtime = EventDrivenSuperSystem(
                execution_stack=SuperExecutionStack(
                    initial_capital=self.config.backtest.initial_capital,
                )
            )
        return self._backtest_runtime

    def _build_replay_config(self) -> MT5PipeReplayConfig:
        symbol = self.config.backtest.primary_symbol or self.config.symbol
        tick_symbols = self.config.backtest.tick_symbols or (symbol,)
        bar_symbols = self.config.backtest.bar_symbols or (symbol,)
        return MT5PipeReplayConfig(
            mt5pipe_root=self._resolve_path(self.config.backtest.mt5pipe_root),
            primary_symbol=symbol,
            start_date=self.config.backtest.start_date,
            end_date=self.config.backtest.end_date,
            tick_symbols=tuple(tick_symbols),
            bar_symbols=tuple(bar_symbols),
            bar_timeframes=tuple(self.config.backtest.bar_timeframes),
            storage_root=self._resolve_optional_path(self.config.backtest.storage_root),
            pipeline_config_path=self._resolve_optional_path(self.config.backtest.pipeline_config_path),
            event_journal_path=self._resolve_optional_path(self.config.backtest.event_journal_path),
            snapshot_journal_path=self._resolve_optional_path(self.config.backtest.snapshot_journal_path),
            include_inferred_sessions=self.config.backtest.include_inferred_sessions,
            emit_tick_snapshots=self.config.backtest.emit_tick_snapshots,
            include_btc=self.config.backtest.include_btc,
        )

    def _resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self._config_dir / path).resolve()

    def _resolve_optional_path(self, value: str | Path | None) -> Path | None:
        if value is None:
            return None
        return self._resolve_path(value)

    def _resolve_optional_str_path(self, value: str) -> str:
        if not value:
            return ""
        return str(self._resolve_path(value))


__all__ = ["Aphelion", "AphelionConfig"]
