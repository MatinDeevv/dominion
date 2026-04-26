"""Compatibility shim for compiler-era contracts.

Canonical ownership now lives in ``mt5pipe.contracts.compiler`` so other
sectors can share artifact/spec types without importing compiler internals.
"""

from mt5pipe.contracts.compiler import ArtifactKind, ArtifactStatus, DatasetSpec, ExperimentSpec, LineageManifest

__all__ = [
    "ArtifactKind",
    "ArtifactStatus",
    "DatasetSpec",
    "ExperimentSpec",
    "LineageManifest",
]
