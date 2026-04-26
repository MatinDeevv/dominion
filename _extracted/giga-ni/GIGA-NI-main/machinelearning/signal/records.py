"""Signal records that mark the handoff from research predictions to risk-taking decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SignalRecord:
    """Immutable contract between the model layer and the execution layer.

    Once a signal crosses this boundary it is no longer only a research artifact; it becomes a risk decision.
    Keeping the record frozen and traceable makes every later PnL number auditable back to the exact model,
    regime context, and sizing rationale that produced it.
    """

    timestamp_utc: datetime
    symbol: str
    model_artifact_id: str
    regime: str
    regime_confidence: float
    direction_60m: int
    direction_probs_60m: tuple[float, float, float]
    return_median_60m: float
    return_lower_80: float
    return_upper_80: float
    conformal_lower_60m: float
    conformal_upper_60m: float
    conformal_coverage: float
    direction_5m: int
    direction_15m: int
    direction_240m: int
    dual_source_ratio: float
    disagreement_pressure_bps: float
    kelly_fraction: float
    position_fraction: float
    signal_strength: float
    action_horizon_minutes: int = 60
    action_direction: int | None = None
    action_direction_probs: tuple[float, float, float] | None = None
    action_return_median: float | None = None
    action_conformal_lower: float | None = None
    action_conformal_upper: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation so signals can be logged, replayed, and audited later."""

        return {
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "symbol": self.symbol,
            "model_artifact_id": self.model_artifact_id,
            "regime": self.regime,
            "regime_confidence": float(self.regime_confidence),
            "direction_60m": int(self.direction_60m),
            "direction_probs_60m": [float(value) for value in self.direction_probs_60m],
            "return_median_60m": float(self.return_median_60m),
            "return_lower_80": float(self.return_lower_80),
            "return_upper_80": float(self.return_upper_80),
            "conformal_lower_60m": float(self.conformal_lower_60m),
            "conformal_upper_60m": float(self.conformal_upper_60m),
            "conformal_coverage": float(self.conformal_coverage),
            "direction_5m": int(self.direction_5m),
            "direction_15m": int(self.direction_15m),
            "direction_240m": int(self.direction_240m),
            "dual_source_ratio": float(self.dual_source_ratio),
            "disagreement_pressure_bps": float(self.disagreement_pressure_bps),
            "kelly_fraction": float(self.kelly_fraction),
            "position_fraction": float(self.position_fraction),
            "signal_strength": float(self.signal_strength),
            "action_horizon_minutes": int(self.action_horizon_minutes),
            "action_direction": None if self.action_direction is None else int(self.action_direction),
            "action_direction_probs": (
                None
                if self.action_direction_probs is None
                else [float(value) for value in self.action_direction_probs]
            ),
            "action_return_median": None if self.action_return_median is None else float(self.action_return_median),
            "action_conformal_lower": (
                None if self.action_conformal_lower is None else float(self.action_conformal_lower)
            ),
            "action_conformal_upper": (
                None if self.action_conformal_upper is None else float(self.action_conformal_upper)
            ),
        }

    def direction_for_horizon(self, horizon_minutes: int) -> int:
        """Return the stored direction aligned to a requested horizon."""

        mapping = {
            5: self.direction_5m,
            15: self.direction_15m,
            60: self.direction_60m,
            240: self.direction_240m,
        }
        try:
            return mapping[int(horizon_minutes)]
        except KeyError as exc:
            raise KeyError(f"Unsupported signal horizon: {horizon_minutes}") from exc

    def resolved_action_direction(self) -> int:
        """Return the canonical direction the runtime should execute."""

        if self.action_direction is not None:
            return int(self.action_direction)
        return self.direction_for_horizon(self.action_horizon_minutes)

    def resolved_action_direction_probs(self) -> tuple[float, float, float]:
        """Return the probability triplet aligned to the execution horizon."""

        if self.action_direction_probs is not None:
            return self.action_direction_probs
        return self.direction_probs_60m

    def resolved_action_return_median(self) -> float:
        """Return the median return forecast aligned to the execution horizon."""

        if self.action_return_median is not None:
            return float(self.action_return_median)
        return float(self.return_median_60m)

    def resolved_action_conformal_lower(self) -> float:
        """Return the lower conformal bound aligned to the execution horizon."""

        if self.action_conformal_lower is not None:
            return float(self.action_conformal_lower)
        return float(self.conformal_lower_60m)

    def resolved_action_conformal_upper(self) -> float:
        """Return the upper conformal bound aligned to the execution horizon."""

        if self.action_conformal_upper is not None:
            return float(self.action_conformal_upper)
        return float(self.conformal_upper_60m)

    def is_actionable(self) -> bool:
        """Gate trades so only confident, sign-consistent, data-quality-clean signals consume risk capital.

        A research signal is not enough on its own. This method enforces the minimum bar-quality, confidence,
        and interval-consistency checks required before the execution layer is allowed to place risk.
        """

        direction = self.resolved_action_direction()
        if direction == 0:
            return False

        direction_probs = self.resolved_action_direction_probs()
        probability = direction_probs[direction + 1]
        if probability < 0.45:
            return False

        conformal_lower = self.resolved_action_conformal_lower()
        conformal_upper = self.resolved_action_conformal_upper()
        excludes_zero = (
            conformal_lower > 0.0 and conformal_upper > 0.0
        ) or (
            conformal_lower < 0.0 and conformal_upper < 0.0
        )
        if not excludes_zero:
            return False

        if direction > 0 and conformal_lower <= 0.0:
            return False
        if direction < 0 and conformal_upper >= 0.0:
            return False

        if self.position_fraction < 0.01:
            return False

        if self.dual_source_ratio < 0.10:
            return False

        return True


__all__ = ["SignalRecord"]
