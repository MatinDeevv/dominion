"""
APHELION Paper Trading — Phase 5
Data feed abstraction, paper trade ledger, session orchestrator, and runner.
"""

__all__ = [
    "DataFeed",
    "FeedConfig",
    "FeedMode",
    "FeedStats",
    "LiveMT5Feed",
    "MT5TickFeed",
    "PaperLedger",
    "PaperRunner",
    "PaperRunnerConfig",
    "PaperSession",
    "PaperSessionConfig",
    "PaperSessionResult",
    "ReplayFeed",
    "run_demo_main",
    "run_paper_main",
    "LatencyProfile",
    "LiveReadinessGate",
    "ReadinessCheck",
]


_LAZY_IMPORTS = {
    "DataFeed": ".feed",
    "FeedConfig": ".feed",
    "FeedMode": ".feed",
    "FeedStats": ".feed",
    "LiveMT5Feed": ".feed",
    "MT5TickFeed": ".feed",
    "ReplayFeed": ".feed",
    "PaperLedger": ".ledger",
    "PaperRunner": ".runner",
    "PaperRunnerConfig": ".runner",
    "PaperSession": ".session",
    "PaperSessionConfig": ".session",
    "PaperSessionResult": ".session",
    "run_demo_main": ".launchers",
    "run_paper_main": ".launchers",
    "LatencyProfile": ".readiness",
    "LiveReadinessGate": ".readiness",
    "ReadinessCheck": ".readiness",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name], __package__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
