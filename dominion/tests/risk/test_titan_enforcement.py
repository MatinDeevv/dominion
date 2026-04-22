"""Tests for TITAN startup enforcement in the paper runner."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from aphelion.paper.runner import validate_titan_gate
from aphelion.risk.titan.gate import GateReport, GateStatus, ValidationResult


def _build_report(validations: list[ValidationResult], failures: list[str] | None = None) -> GateReport:
    return GateReport(
        status=GateStatus.FAILED if failures else GateStatus.PASSED,
        triggered_by="test",
        validations=validations,
        failures=failures or [],
    )


def test_titan_gate_blocks_on_required_failure() -> None:
    titan = MagicMock()
    titan.run_full_gate.return_value = _build_report(
        validations=[
            ValidationResult(
                check_name="min_sharpe_ratio",
                passed=False,
                actual_value=0.45,
                threshold=0.50,
                message="Sharpe below minimum",
            ),
            ValidationResult(
                check_name="max_drawdown",
                passed=True,
                actual_value=0.12,
                threshold=0.30,
            ),
        ],
        failures=["min_sharpe_ratio"],
    )

    with pytest.raises(RuntimeError) as exc_info:
        validate_titan_gate(
            titan,
            ["min_sharpe_ratio", "max_drawdown"],
            metrics={"sharpe": 0.45},
        )

    error_text = str(exc_info.value)
    assert "min_sharpe_ratio" in error_text
    assert "actual=0.4500" in error_text
    assert "threshold=0.5000" in error_text
    assert "Sharpe below minimum" in error_text


def test_titan_gate_passes_on_all_required_checks() -> None:
    titan = MagicMock()
    titan.run_full_gate.return_value = _build_report(
        validations=[
            ValidationResult(
                check_name="min_sharpe_ratio",
                passed=True,
                actual_value=0.65,
                threshold=0.50,
            ),
            ValidationResult(
                check_name="max_drawdown",
                passed=True,
                actual_value=0.12,
                threshold=0.30,
            ),
            ValidationResult(
                check_name="wf_min_folds_passing",
                passed=False,
                actual_value=6.0,
                threshold=8.0,
            ),
        ],
        failures=["wf_min_folds_passing"],
    )

    validate_titan_gate(
        titan,
        ["min_sharpe_ratio", "max_drawdown"],
        metrics={"sharpe": 0.65},
    )


def test_titan_gate_missing_required_check_warns(caplog: pytest.LogCaptureFixture) -> None:
    titan = MagicMock()
    titan.run_full_gate.return_value = _build_report(
        validations=[
            ValidationResult(
                check_name="min_sharpe_ratio",
                passed=True,
                actual_value=0.65,
                threshold=0.50,
            ),
        ]
    )

    with caplog.at_level(logging.WARNING):
        validate_titan_gate(
            titan,
            ["min_sharpe_ratio", "nonexistent_check"],
            metrics={"sharpe": 0.65},
        )

    assert any("not found in report" in record.message for record in caplog.records)


def test_titan_gate_skips_when_no_metrics_supplied(caplog: pytest.LogCaptureFixture) -> None:
    titan = MagicMock()

    with caplog.at_level(logging.WARNING):
        validate_titan_gate(titan, ["min_sharpe_ratio"], metrics={})

    titan.run_full_gate.assert_not_called()
    assert any("no metrics were supplied" in record.message for record in caplog.records)
