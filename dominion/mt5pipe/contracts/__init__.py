"""
Shared contracts package.

All cross-sector imports between state/features/compiler sectors
must go through this package or through ``<sector>.public``.
"""

from mt5pipe.contracts.artifacts import ArtifactKind, ArtifactRef
from mt5pipe.contracts.catalog import ArtifactRegistry
from mt5pipe.contracts.compiler import ArtifactStatus, DatasetSpec, ExperimentSpec, LineageManifest
from mt5pipe.contracts.dataset import DATASET_JOIN_KEYS, DatasetId, DatasetSplitKind
from mt5pipe.contracts.lineage import LineageNode
from mt5pipe.contracts.manifest import read_manifest_sidecar, write_manifest_sidecar
from mt5pipe.contracts.state import (
    StateArtifactRef,
    StateWindowArtifactRef,
    StateWindowRequest,
    TickArtifactRef,
    parse_window_size,
)
from mt5pipe.contracts.trust import TrustVerdict

__all__ = [
    "ArtifactKind",
    "ArtifactRef",
    "ArtifactRegistry",
    "ArtifactStatus",
    "DATASET_JOIN_KEYS",
    "DatasetSpec",
    "DatasetId",
    "DatasetSplitKind",
    "ExperimentSpec",
    "LineageNode",
    "LineageManifest",
    "StateArtifactRef",
    "StateWindowArtifactRef",
    "StateWindowRequest",
    "TickArtifactRef",
    "TrustVerdict",
    "parse_window_size",
    "read_manifest_sidecar",
    "write_manifest_sidecar",
]
