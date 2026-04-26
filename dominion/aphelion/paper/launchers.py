"""Canonical package-owned launchers for paper trading and the live demo."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from aphelion.paper.feed import FeedConfig, FeedMode
from aphelion.paper.runner import PaperRunner, PaperRunnerConfig
from aphelion.paper.session import PaperSessionConfig
from aphelion.risk.sentinel.execution.mt5 import MT5Config
from aphelion.tui.app import AphelionTUI, TUIConfig

try:
    from aphelion.ares.coordinator import AresCoordinator, AresConfig

    _HAS_ARES = True
except ImportError:
    _HAS_ARES = False

try:
    from aphelion.governance.council.sola import SOLA

    _HAS_SOLA = True
except ImportError:
    _HAS_SOLA = False

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()


def _setup_logging(verbose: bool = False, *, log_file: str | None = None) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("MetaTrader5").setLevel(logging.WARNING)


def parse_run_paper_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_paper",
        description="APHELION Paper Trading - end-to-end launcher",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="live",
        choices=["mt5_tick", "live", "replay"],
        help="Data feed mode (default: live)",
    )
    parser.add_argument("--capital", type=float, default=10_000.0, help="Starting capital (USD)")
    parser.add_argument("--symbol", type=str, default="XAUUSD", help="Trading symbol")
    parser.add_argument("--hydra-checkpoint", type=str, default="", help="Path to HYDRA ensemble .pt checkpoint")
    parser.add_argument(
        "--mt5-login",
        type=int,
        default=int(os.getenv("MT5_LOGIN", "0")),
        help="MT5 account login (env: MT5_LOGIN)",
    )
    parser.add_argument(
        "--mt5-password",
        type=str,
        default=os.getenv("MT5_PASSWORD", ""),
        help="MT5 account password (env: MT5_PASSWORD)",
    )
    parser.add_argument(
        "--mt5-server",
        type=str,
        default=os.getenv("MT5_SERVER", ""),
        help="MT5 broker server (env: MT5_SERVER)",
    )
    parser.add_argument(
        "--mt5-terminal",
        type=str,
        default=os.getenv("MT5_TERMINAL", ""),
        help="Path to terminal64.exe (env: MT5_TERMINAL)",
    )
    parser.add_argument(
        "--mt5-timeout-ms",
        type=int,
        default=int(os.getenv("MT5_TIMEOUT_MS", "10000")),
        help="MT5 initialize timeout in ms (env: MT5_TIMEOUT_MS)",
    )
    parser.add_argument(
        "--mt5-retries",
        type=int,
        default=int(os.getenv("MT5_RETRIES", "3")),
        help="MT5 connection retry attempts (env: MT5_RETRIES)",
    )
    parser.add_argument(
        "--mt5-retry-delay",
        type=float,
        default=float(os.getenv("MT5_RETRY_DELAY", "5.0")),
        help="Seconds between MT5 retries (env: MT5_RETRY_DELAY)",
    )
    parser.add_argument("--poll-ms", type=int, default=100, help="Tick poll interval (ms)")
    parser.add_argument("--warmup", type=int, default=200, help="Warmup bars to pre-load")
    parser.add_argument("--no-tui", action="store_true", help="Disable TUI (console logging only)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")
    return parser.parse_args(argv)


def _build_paper_config(args: argparse.Namespace) -> PaperRunnerConfig:
    mode_map = {
        "mt5_tick": FeedMode.MT5_TICK,
        "live": FeedMode.LIVE,
        "replay": FeedMode.REPLAY,
    }
    return PaperRunnerConfig(
        feed_mode=mode_map[args.mode],
        mt5_config=MT5Config(
            terminal_path=args.mt5_terminal,
            login=args.mt5_login,
            password=args.mt5_password,
            server=args.mt5_server,
            symbol=args.symbol,
            timeout_ms=args.mt5_timeout_ms,
            retry_attempts=args.mt5_retries,
            retry_delay_seconds=args.mt5_retry_delay,
        ),
        feed_config=FeedConfig(
            symbol=args.symbol,
            poll_interval_ms=args.poll_ms,
            warmup_bars=args.warmup,
        ),
        session_config=PaperSessionConfig(
            initial_capital=args.capital,
            symbol=args.symbol,
            hydra_checkpoint=args.hydra_checkpoint,
            warmup_bars=max(64, args.warmup),
        ),
        enable_tui=not args.no_tui,
    )


async def _run_paper_from_args(args: argparse.Namespace) -> int:
    logger = logging.getLogger("aphelion.run_paper")
    Path("logs").mkdir(exist_ok=True)

    logger.info("=" * 60)
    logger.info("APHELION Paper Trading System")
    logger.info("=" * 60)

    if args.mode in ("mt5_tick", "live"):
        try:
            import MetaTrader5  # noqa: F401

            logger.info("MetaTrader5 package: AVAILABLE")
        except ImportError:
            logger.error("MetaTrader5 package not installed. Install with: pip install MetaTrader5")
            return 1

        if sys.platform != "win32":
            logger.error("MT5 is only available on Windows.")
            return 1

    config = _build_paper_config(args)
    logger.info("Feed mode: %s", config.feed_mode.name)
    logger.info("Capital:   $%.2f", config.session_config.initial_capital)
    logger.info("Symbol:    %s", config.session_config.symbol)

    if config.session_config.hydra_checkpoint:
        logger.info("HYDRA:     %s", config.session_config.hydra_checkpoint)
    else:
        logger.info("HYDRA:     (no checkpoint - signals disabled)")

    runner = PaperRunner(config)

    try:
        result = await runner.run()
        print("\n" + result.summary())
        return 0
    except asyncio.CancelledError:
        logger.info("Run cancelled - shutting down gracefully")
        await runner.stop()
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await runner.stop()
        return 130
    except ConnectionError as exc:
        logger.error("Connection failed: %s", exc)
        return 1
    except Exception:
        logger.exception("Fatal error during paper trading")
        return 1


def run_paper_main(argv: list[str] | None = None) -> None:
    _load_env()
    args = parse_run_paper_args(argv)
    _setup_logging(args.verbose, log_file="logs/paper_run.log")
    raise SystemExit(asyncio.run(_run_paper_from_args(args)))


def parse_run_demo_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APHELION all-in-one live demo")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Starting paper capital")
    parser.add_argument("--symbol", type=str, default="XAUUSD", help="Trading symbol")
    parser.add_argument("--warmup", type=int, default=64, help="Warmup bars")
    parser.add_argument("--no-training", action="store_true", help="Do not start background training")
    parser.add_argument("--train-full", action="store_true", help="Use full training config")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return parser.parse_args(argv)


def _find_hydra_checkpoint() -> str:
    preferred = [
        "models/hydra/hydra_ensemble_best_sharpe.pt",
        "models/hydra/hydra_ensemble_best_loss.pt",
        "models/test_hydra/hydra_ensemble_best_sharpe.pt",
        "models/test_hydra/hydra_ensemble_best_loss.pt",
    ]
    for path in preferred:
        if Path(path).exists():
            return path
    for path in Path("models").rglob("hydra_ensemble_best_sharpe.pt"):
        return str(path)
    for path in Path("models").rglob("hydra_ensemble_best_loss.pt"):
        return str(path)
    return ""


def _start_training_subprocess(train_full: bool, symbol: str = "XAUUSD") -> subprocess.Popen:
    Path("logs").mkdir(exist_ok=True)
    log_path = Path("logs/train_hydra_live.log")
    log_file = log_path.open("a", encoding="utf-8")

    sym_lower = symbol.lower()
    data_candidates = [
        Path(f"data/processed/{symbol}/{sym_lower}_hydra.parquet"),
        Path(f"data/raw/{symbol}/{sym_lower}_m5.csv"),
        Path(f"data/raw/{symbol}/{sym_lower}_m1.csv"),
        Path("data/processed/xauusd_hydra.parquet"),
        Path("data/bars/xauusd_m5.csv"),
        Path("data/bars/xauusd_m1.csv"),
    ]
    data_path = ""
    for candidate in data_candidates:
        if candidate.exists():
            data_path = str(candidate)
            break

    if not data_path:
        raise FileNotFoundError(
            f"No real data found for {symbol}. Run aphelion_data.py first to fetch and prepare data."
        )

    cmd = [sys.executable, "scripts/train_hydra.py", "--data", data_path]
    if train_full:
        cmd.append("--full")

    return subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(Path(__file__).resolve().parents[2]),
    )


async def _wait_for_runner_state(runner: PaperRunner, timeout_s: float = 5.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if runner.tui_state is not None:
            return runner.tui_state
        await asyncio.sleep(0.05)
    raise TimeoutError("Runner did not initialize TUI state in time")


async def _run_demo_from_args(args: argparse.Namespace) -> int:
    logger = logging.getLogger("aphelion.runall")

    logger.info("Starting APHELION all-in-one demo...")

    checkpoint = _find_hydra_checkpoint()
    if checkpoint:
        logger.info("Using HYDRA checkpoint: %s", checkpoint)
    else:
        logger.warning(
            "No HYDRA checkpoint found. Session will run but may not place model-driven trades."
        )

    training_proc: Optional[subprocess.Popen] = None
    if not args.no_training:
        training_proc = _start_training_subprocess(args.train_full, args.symbol)
        logger.info(
            "Background training started (PID %s). Logs: logs/train_hydra_live.log",
            training_proc.pid,
        )

    ares = None
    if _HAS_ARES:
        sola = None
        if _HAS_SOLA:
            try:
                sola = SOLA()
                logger.info("SOLA sovereign intelligence layer initialized")
            except Exception as exc:  # pragma: no cover - optional integration path
                logger.warning("SOLA init failed (non-fatal): %s", exc)

        ares = AresCoordinator(config=AresConfig(), sola=sola)
        logger.info(
            "ARES coordinator initialized - SOLA=%s",
            "active" if sola is not None else "disabled",
        )
    else:
        logger.warning("ARES not available - session will run without governance layer")

    config = PaperRunnerConfig(
        feed_mode=FeedMode.LIVE,
        session_config=PaperSessionConfig(
            initial_capital=args.capital,
            symbol=args.symbol,
            hydra_checkpoint=checkpoint,
            warmup_bars=max(32, args.warmup),
        ),
        enable_tui=True,
        ares=ares,
    )

    runner = PaperRunner(config)
    runner_task = asyncio.create_task(runner.run())

    try:
        state = await _wait_for_runner_state(runner)
        tui = AphelionTUI(
            state=state,
            config=TUIConfig(refresh_rate=0.25, initial_view="overview"),
        )
        logger.info("TUI started. Press 'q' in TUI or Ctrl+C to exit.")
        await tui.run()
        return 0
    except asyncio.CancelledError:
        logger.info("Run cancelled")
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    finally:
        await runner.stop()
        if not runner_task.done():
            runner_task.cancel()
            try:
                await runner_task
            except asyncio.CancelledError:
                pass

        if training_proc is not None and training_proc.poll() is None:
            logger.info("Stopping background training process (PID %s)", training_proc.pid)
            training_proc.terminate()
            try:
                training_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                training_proc.kill()

        logger.info("APHELION runall demo stopped.")


def run_demo_main(argv: list[str] | None = None) -> None:
    _load_env()
    args = parse_run_demo_args(argv)
    _setup_logging(args.verbose)
    raise SystemExit(asyncio.run(_run_demo_from_args(args)))


__all__ = [
    "parse_run_demo_args",
    "parse_run_paper_args",
    "run_demo_main",
    "run_paper_main",
]
