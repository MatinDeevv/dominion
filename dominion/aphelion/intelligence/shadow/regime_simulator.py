"""Stub module for the removed SHADOW regime simulator."""

_MESSAGE = (
    "SHADOW regime simulator was removed. "
    "Use real market data and runtime regime detection instead."
)

__all__: list[str] = []


def __getattr__(name: str) -> object:
    raise ImportError(_MESSAGE)
