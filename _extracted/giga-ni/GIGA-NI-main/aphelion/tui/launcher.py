"""Canonical package-owned launcher for the APHELION terminal UI."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from aphelion.tui.app import AphelionTUI, TUIConfig
from aphelion.tui.config import load_config
from aphelion.tui.controller import AphelionController


def _setup_logging() -> logging.Logger:
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "aphelion.log"),
            logging.StreamHandler(sys.stderr),
        ],
        force=True,
    )
    return logging.getLogger("aphelion")


def main() -> None:
    logger = _setup_logging()
    config_path = os.environ.get("APHELION_CONFIG", "config/aphelion.json")
    config = load_config(config_path)

    errors = config.validate()
    if errors:
        for error in errors:
            logger.warning("Config warning: %s", error)

    controller = AphelionController(config)
    initial_view = os.environ.get("APHELION_VIEW", "launcher")
    tui = AphelionTUI(controller=controller, config=TUIConfig(initial_view=initial_view))
    controller.tui_state = tui.state

    logger.info("APHELION TUI starting (view=%s)", initial_view)
    try:
        tui.run_sync()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop_session()
        logger.info("APHELION TUI shutdown complete")


__all__ = ["main"]
