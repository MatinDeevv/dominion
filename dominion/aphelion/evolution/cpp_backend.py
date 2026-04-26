from __future__ import annotations

from typing import Any

try:
    import _dominion_cpp
except ImportError:  # pragma: no cover - depends on optional native build
    _dominion_cpp = None


def is_cpp_available() -> bool:
    return _dominion_cpp is not None


def run_replay(*args: Any, python_engine: Any | None = None, **kwargs: Any) -> Any:
    if _dominion_cpp is not None:
        return _dominion_cpp.run_replay(*args, **kwargs)
    if python_engine is None:
        raise RuntimeError(
            "C++ replay backend is not built. Pass python_engine=... "
            "or use the pure-Python backtest/replay engine directly."
        )
    return python_engine.run(*args, **kwargs)


def run_evolution(*args: Any, **kwargs: Any) -> Any:
    if _dominion_cpp is not None:
        return _dominion_cpp.run_evolution(*args, **kwargs)

    from aphelion.evolution.prometheus.engine import PrometheusEngine

    config = kwargs.pop("config", None)
    engine = PrometheusEngine(config)
    return engine.run(*args, **kwargs)

