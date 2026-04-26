"""Manifest and spec helpers for the dataset compiler."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from mt5pipe.config.models import MergeConfig
from mt5pipe.contracts.compiler import DatasetSpec, ExperimentSpec, LineageManifest
from mt5pipe.contracts.identity import (
    build_artifact_id as _build_artifact_id,
    build_id_now,
    build_manifest_id as _build_manifest_id,
    build_stage_artifact_id,
    build_stage_manifest_id,
    code_version,
    compute_content_hash,
)
from mt5pipe.contracts.manifest import read_manifest_sidecar, write_manifest_sidecar
from mt5pipe.storage.paths import StoragePaths


def _resolve_spec_path(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path

    prefixed_path = Path("data") / path
    if prefixed_path.exists():
        return prefixed_path

    return path


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    path = _resolve_spec_path(path)
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(raw)
    return json.loads(raw)


def load_dataset_spec(path: Path) -> DatasetSpec:
    """Load a DatasetSpec from YAML or JSON."""
    return DatasetSpec.model_validate(_load_yaml_or_json(path))


def load_experiment_spec(path: Path) -> ExperimentSpec:
    """Load an ExperimentSpec from YAML or JSON."""
    return ExperimentSpec.model_validate(_load_yaml_or_json(path))


def merge_config_ref(cfg: MergeConfig) -> str:
    payload = json.dumps(cfg.model_dump(mode="json"), sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"merge.default@{digest}"


def build_artifact_id(dataset_name: str, created_at: dt.datetime, content_hash: str) -> str:
    _ = created_at
    return _build_artifact_id("dataset", dataset_name, content_hash)


def build_manifest_id(dataset_name: str, created_at: dt.datetime, content_hash: str) -> str:
    _ = created_at
    return _build_manifest_id("dataset", dataset_name, content_hash)
