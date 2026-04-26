"""Neutral catalog protocols shared across sectors."""

from __future__ import annotations

from typing import Protocol

from mt5pipe.contracts.compiler import LineageManifest


class ArtifactRegistry(Protocol):
    """Minimal artifact-registration surface needed outside the compiler sector."""

    def register_artifact(self, manifest: LineageManifest, manifest_uri: str, *, detail: str = "") -> None:
        ...
