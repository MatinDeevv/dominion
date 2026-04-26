"""Manifest serialization helpers shared across sectors."""

from __future__ import annotations

import json
from pathlib import Path

from mt5pipe.contracts.compiler import LineageManifest
from mt5pipe.storage.paths import StoragePaths


def write_manifest_sidecar(manifest: LineageManifest, paths: StoragePaths) -> Path:
    path = paths.manifest_file(manifest.artifact_kind, manifest.logical_name, manifest.manifest_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def read_manifest_sidecar(path: Path) -> LineageManifest:
    return LineageManifest.model_validate_json(path.read_text(encoding="utf-8"))
