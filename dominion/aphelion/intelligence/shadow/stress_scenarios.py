"""Stub module for the removed SHADOW stress scenarios."""

_MESSAGE = (
    "SHADOW stress scenarios were removed. "
    "Use ZEUS stress tooling with real market data instead."
)

__all__: list[str] = []


def __getattr__(name: str) -> object:
    raise ImportError(_MESSAGE)
