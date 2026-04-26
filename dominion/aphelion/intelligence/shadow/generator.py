"""Stub module for the removed SHADOW generator."""

_MESSAGE = (
    "SHADOW generator was removed. "
    "Use real market data pipelines instead."
)

__all__: list[str] = []


def __getattr__(name: str) -> object:
    raise ImportError(_MESSAGE)
