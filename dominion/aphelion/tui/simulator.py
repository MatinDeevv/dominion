"""Stub module for the removed TUI live simulator."""

_MESSAGE = (
    "LiveSimulator has been removed. "
    "Aphelion now requires real market data exclusively. "
    "Use paper trading with a live MT5 connection or replay historical data."
)

__all__: list[str] = []


def __getattr__(name: str) -> object:
    raise ImportError(_MESSAGE)
