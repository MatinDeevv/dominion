from __future__ import annotations

import pytest

import aphelion.hephaestus.llm_client as llm_module
from aphelion.hephaestus.llm_client import HephaestusLLMClient, HephaestusLLMError, LLMConfig


def test_default_client_runs_in_stub_mode() -> None:
    client = HephaestusLLMClient()

    assert client.is_live is False
    assert client.is_stub is True
    assert client.backend_mode == "stub"
    assert client.call("system", "user") == ""
    assert client.last_error is not None


def test_require_live_without_api_key_raises() -> None:
    with pytest.raises(HephaestusLLMError):
        HephaestusLLMClient(LLMConfig(require_live=True))


def test_require_live_without_sdk_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "_HAS_ANTHROPIC", False)

    with pytest.raises(HephaestusLLMError):
        HephaestusLLMClient(LLMConfig(api_key="test-key", require_live=True))


def test_raise_on_failure_surfaces_call_errors() -> None:
    class _BrokenMessages:
        def create(self, **_: object) -> object:
            raise RuntimeError("backend down")

    class _BrokenClient:
        messages = _BrokenMessages()

    client = HephaestusLLMClient(LLMConfig(raise_on_failure=True))
    client._client = _BrokenClient()  # noqa: SLF001 - controlled test seam
    client._backend_mode = "live"  # noqa: SLF001 - controlled test seam

    with pytest.raises(HephaestusLLMError):
        client.call("system", "user")
