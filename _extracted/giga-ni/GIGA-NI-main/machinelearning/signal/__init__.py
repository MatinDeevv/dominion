"""Public exports for the Phase 7 signal layer."""

__all__ = [
    "ConformalCalibrator",
    "KellyPositionSizer",
    "SignalPublisher",
    "SignalRecord",
]

_LAZY_IMPORTS = {
    "ConformalCalibrator": ".conformal",
    "KellyPositionSizer": ".sizing",
    "SignalPublisher": ".publisher",
    "SignalRecord": ".records",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name], __package__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
