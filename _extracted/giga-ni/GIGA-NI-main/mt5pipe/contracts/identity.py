"""Shared artifact identity helpers used across compiler and state layers."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from typing import Any


def build_id_now(prefix: str = "build") -> str:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{prefix}.{ts}"


def code_version() -> str:
    """Best-effort code version identifier."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        sha = result.stdout.strip()
        if sha:
            return sha
    except Exception:
        pass
    return "workspace-local-no-git"


def compute_content_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_artifact_id(artifact_kind: str, logical_name: str, content_hash: str) -> str:
    return f"{artifact_kind}.{logical_name}.{content_hash[:12]}"


def build_manifest_id(artifact_kind: str, logical_name: str, content_hash: str) -> str:
    return f"manifest.{artifact_kind}.{logical_name}.{content_hash[:12]}"


def build_stage_artifact_id(
    artifact_kind: str,
    logical_name: str,
    created_at: dt.datetime,
    content_hash: str,
) -> str:
    _ = created_at
    return build_artifact_id(artifact_kind, logical_name, content_hash)


def build_stage_manifest_id(
    artifact_kind: str,
    logical_name: str,
    created_at: dt.datetime,
    content_hash: str,
) -> str:
    _ = created_at
    return build_manifest_id(artifact_kind, logical_name, content_hash)

