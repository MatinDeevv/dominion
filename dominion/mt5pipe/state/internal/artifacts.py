"""State-sector artifact helpers with no compiler-sector dependency."""

from __future__ import annotations

import json
from pathlib import Path

from mt5pipe.contracts.identity import (
    build_artifact_id,
    build_id_now,
    build_manifest_id,
    code_version,
    compute_content_hash,
)
from mt5pipe.state.models import StateArtifactManifest
from mt5pipe.storage.paths import StoragePaths


def state_code_version() -> str:
    """Backward-compatible alias for the shared code version helper."""
    return code_version()


def write_state_manifest(manifest: StateArtifactManifest, paths: StoragePaths) -> Path:
    path = paths.manifest_file(manifest.artifact_kind, manifest.logical_name, manifest.manifest_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def read_state_manifest(path: Path) -> StateArtifactManifest:
    return StateArtifactManifest.model_validate_json(path.read_text(encoding="utf-8"))
