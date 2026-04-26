"""Archived compatibility package for the removed feature system."""

_MESSAGE = (
    "aphelion.features is archived. "
    "Import from aphelion.feature_engine.features instead."
)

__all__: list[str] = []


def __getattr__(name: str) -> object:
    raise ImportError(_MESSAGE)
