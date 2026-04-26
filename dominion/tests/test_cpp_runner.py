"""Tests for the C++ runner bridge — mocked, no actual binary required."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from aphelion.evolution.cpp_runner import CppRunner, HydraEvolutionFinalist


def test_finalist_from_dict():
    d = {
        "param_id": 42,
        "monthly_return": 0.08,
        "total_return": 0.96,
        "max_drawdown": 0.12,
        "profit_factor": 1.35,
        "win_rate": 0.48,
        "trade_count": 87,
        "consistency": 0.71,
        "composite_score": 1.23,
        "robustness_score": 0.65,
        "params": {"sl_atr_multiple": 1.5, "confidence_threshold": 0.55},
    }
    f = HydraEvolutionFinalist.from_dict(d)
    assert f.param_id == 42
    assert f.monthly_return == pytest.approx(0.08)
    assert f.params["sl_atr_multiple"] == pytest.approx(1.5)


def test_finalist_from_dict_missing_fields():
    """Missing optional fields should use sensible defaults."""
    f = HydraEvolutionFinalist.from_dict({})
    assert f.param_id == 0
    assert f.monthly_return == pytest.approx(0.0)
    assert f.params == {}


def test_runner_warns_missing_binary(tmp_path):
    with patch("aphelion.evolution.cpp_runner.log") as mock_log:
        runner = CppRunner(
            data_root=tmp_path,
            cpp_bin=tmp_path / "nonexistent.exe",
        )
    # Should warn but not raise
    assert runner.cpp_bin == tmp_path / "nonexistent.exe"
    mock_log.warning.assert_called_once()


def test_parse_finalists_missing_file(tmp_path):
    runner = CppRunner(data_root=tmp_path)
    result = runner._parse_finalists(tmp_path / "nonexistent.json")
    assert result == []


def test_parse_finalists_valid_json(tmp_path):
    data = [
        {
            "param_id": 1,
            "monthly_return": 0.07,
            "total_return": 0.84,
            "max_drawdown": 0.10,
            "profit_factor": 1.40,
            "win_rate": 0.52,
            "trade_count": 60,
            "consistency": 0.80,
            "composite_score": 1.10,
            "robustness_score": 0.70,
            "params": {},
        }
    ]
    json_path = tmp_path / "finalists.json"
    import json
    json_path.write_text(json.dumps(data))

    runner = CppRunner(data_root=tmp_path)
    finalists = runner._parse_finalists(json_path)
    assert len(finalists) == 1
    assert finalists[0].monthly_return == pytest.approx(0.07)
    assert finalists[0].trade_count == 60


def test_runner_raises_on_cpp_failure(tmp_path):
    """_run should raise RuntimeError when the binary exits non-zero."""
    runner = CppRunner(data_root=tmp_path, cpp_bin=tmp_path / "fake.exe")
    # Patch subprocess.run to simulate a failed binary call
    with patch("aphelion.evolution.cpp_runner.subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "some error output"
        mock_run.return_value = mock_proc
        with pytest.raises(RuntimeError, match="C\\+\\+ binary failed"):
            runner._run(["--help"])


def test_hydra_evolution_requires_tape(tmp_path):
    runner = CppRunner(data_root=tmp_path)
    with pytest.raises(ValueError, match="hydra_tape path is required"):
        runner.run_hydra_evolution(hydra_tape=None)
