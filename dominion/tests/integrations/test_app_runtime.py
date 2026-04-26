from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from aphelion import Aphelion, Config
from aphelion.__main__ import app


def test_config_load_and_runtime_status(tmp_path: Path) -> None:
    config_path = tmp_path / "backtest.yaml"
    config_path.write_text(
        "\n".join(
            [
                "aphelion:",
                "  execution_mode: backtest",
                "  timezone: UTC",
                "  symbol: XAUUSD",
                "  backtest:",
                "    mt5pipe_root: .",
                "    primary_symbol: XAUUSD",
                "    start_date: '2026-01-01'",
                "    end_date: '2026-01-02'",
                "    bar_timeframes: ['M1']",
            ]
        ),
        encoding="utf-8",
    )

    config = Config.from_yaml(config_path)
    runtime = Aphelion(config, config_path=config_path)
    status = runtime.status()

    assert config.execution_mode == "backtest"
    assert status["symbol"] == "XAUUSD"
    assert status["execution_mode"] == "backtest"
    assert status["config_path"] == str(config_path.resolve())


def test_cli_validate_and_status_commands(tmp_path: Path) -> None:
    config_path = tmp_path / "backtest.yaml"
    config_path.write_text(
        "\n".join(
            [
                "aphelion:",
                "  execution_mode: backtest",
                "  timezone: UTC",
                "  symbol: XAUUSD",
                "  backtest:",
                "    mt5pipe_root: .",
                "    primary_symbol: XAUUSD",
                "    start_date: '2026-01-01'",
                "    end_date: '2026-01-02'",
                "    bar_timeframes: ['M1']",
            ]
        ),
        encoding="utf-8",
    )

    runner = CliRunner()

    validate = runner.invoke(app, ["config", "validate", "--config", str(config_path)])
    assert validate.exit_code == 0
    assert '"valid": true' in validate.stdout.lower()

    status = runner.invoke(app, ["status", "--config", str(config_path)])
    assert status.exit_code == 0
    assert '"execution_mode": "backtest"' in status.stdout
