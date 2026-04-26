"""APHELION Autonomous Trading System.

This package is workspace-aware: other Aphelion repos can expose additional
subpackages under the shared ``aphelion`` namespace when they are available on
``sys.path``. The unified runtime and CLI live in ``aphelion.app`` and
``aphelion.__main__``.
"""

from importlib import import_module
from pkgutil import extend_path
from typing import Any

__path__ = extend_path(__path__, __name__)
__version__ = "0.2.0"

__all__ = ["Aphelion", "AphelionConfig", "Config", "__version__"]


def __getattr__(name: str) -> Any:
    if name in {"Aphelion", "AphelionConfig", "Config"}:
        module = import_module("aphelion.app")
        if name == "Config":
            return getattr(module, "AphelionConfig")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
