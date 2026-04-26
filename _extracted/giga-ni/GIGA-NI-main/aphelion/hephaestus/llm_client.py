"""
HEPHAESTUS - LLM client.

Thin wrapper around the Anthropic API used by the Hephaestus forge.
When no backend is configured the client can still run in deterministic
stub mode so parser/codegen tests remain fully offline.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

try:
    import anthropic  # type: ignore[import-untyped]

    _HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    _HAS_ANTHROPIC = False


BackendMode = Literal["stub", "live"]


class HephaestusLLMError(RuntimeError):
    """Raised when the caller explicitly requires a live LLM backend."""


@dataclass
class LLMConfig:
    """LLM call configuration."""

    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.1
    api_key: str = ""
    require_live: bool = False
    raise_on_failure: bool = False


TOKEN_BUDGETS: dict[str, int] = {
    "parse": 1000,
    "generate": 3000,
    "fix": 2000,
    "diagnose": 1000,
}


class HephaestusLLMClient:
    """Claude API wrapper for HEPHAESTUS."""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self._config = config or LLMConfig()
        self._api_key = self._config.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client: Optional[object] = None
        self._total_tokens = 0
        self._total_calls = 0
        self._backend_mode: BackendMode = "stub"
        self._last_error: str | None = None

        self._initialize_backend()

    @property
    def is_live(self) -> bool:
        """True when a real LLM backend is configured."""
        return self._backend_mode == "live" and self._client is not None

    @property
    def is_stub(self) -> bool:
        return not self.is_live

    @property
    def backend_mode(self) -> BackendMode:
        return self._backend_mode

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_calls(self) -> int:
        return self._total_calls

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Send a prompt to the backend and return the response text.

        Default behavior preserves offline determinism: stub mode returns an
        empty string. Callers that need a hard failure can set
        ``require_live=True`` or ``raise_on_failure=True`` in ``LLMConfig``.
        """
        self._total_calls += 1
        max_tok = max_tokens or self._config.max_tokens
        temp = temperature if temperature is not None else self._config.temperature

        if not self.is_live:
            message = self._last_error or "No live LLM backend configured; using deterministic stub mode."
            logger.debug("HEPHAESTUS LLM stub call: %s", message)
            self._maybe_raise(message)
            return ""

        try:
            response = self._client.messages.create(  # type: ignore[union-attr]
                model=self._config.model,
                max_tokens=max_tok,
                temperature=temp,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text  # type: ignore[index]
            usage = getattr(response, "usage", None)
            if usage:
                self._total_tokens += getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
            self._last_error = None
            return text
        except Exception as exc:
            message = f"HEPHAESTUS LLM call failed: {exc}"
            self._last_error = message
            logger.exception(message)
            self._maybe_raise(message, exc)
            return ""

    def call_parser(self, system_prompt: str, user_prompt: str) -> str:
        return self.call(system_prompt, user_prompt, max_tokens=TOKEN_BUDGETS["parse"])

    def call_codegen(self, system_prompt: str, user_prompt: str) -> str:
        return self.call(system_prompt, user_prompt, max_tokens=TOKEN_BUDGETS["generate"])

    def call_fixer(self, system_prompt: str, user_prompt: str) -> str:
        return self.call(system_prompt, user_prompt, max_tokens=TOKEN_BUDGETS["fix"])

    @staticmethod
    def extract_json(text: str) -> Optional[dict]:
        """Best-effort JSON extraction from LLM output."""
        if not text:
            return None

        cleaned = text.strip()
        for fence in ("```json", "```", "```python"):
            if cleaned.startswith(fence):
                cleaned = cleaned[len(fence) :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        brace_depth = 0
        start: Optional[int] = None
        for i, ch in enumerate(cleaned):
            if ch == "{":
                if brace_depth == 0:
                    start = i
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0 and start is not None:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        pass
                    start = None

        return None

    def _initialize_backend(self) -> None:
        """Initialize the configured backend or record a precise stub reason."""
        if not self._api_key:
            self._last_error = "ANTHROPIC_API_KEY not configured; client is running in stub mode."
            if self._config.require_live:
                self._maybe_raise(self._last_error)
            return

        if not _HAS_ANTHROPIC:
            self._last_error = "anthropic package is not installed; client is running in stub mode."
            logger.warning(self._last_error)
            if self._config.require_live:
                self._maybe_raise(self._last_error)
            return

        try:
            self._client = anthropic.Anthropic(api_key=self._api_key)  # type: ignore[union-attr]
            self._backend_mode = "live"
            self._last_error = None
        except Exception as exc:
            self._last_error = f"Anthropic SDK initialization failed: {exc}"
            logger.exception(self._last_error)
            if self._config.require_live:
                self._maybe_raise(self._last_error, exc)

    def _maybe_raise(self, message: str, exc: Exception | None = None) -> None:
        if not (self._config.require_live or self._config.raise_on_failure):
            return
        if exc is None:
            raise HephaestusLLMError(message)
        raise HephaestusLLMError(message) from exc


__all__ = [
    "BackendMode",
    "HephaestusLLMClient",
    "HephaestusLLMError",
    "LLMConfig",
    "TOKEN_BUDGETS",
]
