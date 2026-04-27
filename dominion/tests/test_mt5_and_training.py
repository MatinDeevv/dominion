"""Integration test suite for MT5 exporters and H200 trainer."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch


class TestMT5Exporter:
    """Tests for MT5 exporter module."""

    def test_mt5_exporter_imports(self):
        """Verify MT5 exporter module imports without errors."""
        try:
            from scripts.export_mt5_all_brokers import (
                download_symbol_timeframe,
                get_all_mt5_accounts,
            )
            assert callable(download_symbol_timeframe)
            assert callable(get_all_mt5_accounts)
        except ImportError as e:
            pytest.skip(f"MT5 not available: {e}")

    def test_export_mt5_readme_exists(self):
        """Verify EXPORT_MT5_README.md exists."""
        readme = Path("scripts/EXPORT_MT5_README.md")
        assert readme.exists()
        content = readme.read_text()
        assert "export_mt5_all_brokers" in content

    def test_scan_mt5_imports(self):
        """Verify scan_mt5.py can be imported."""
        try:
            import scripts.scan_mt5
            assert hasattr(scripts.scan_mt5, "scan_mt5_setup")
        except ImportError as e:
            pytest.skip(f"Dependencies missing: {e}")


class TestH200Trainer:
    """Tests for H200 trainer module."""

    def test_train_smart_imports(self):
        """Verify train_smart.py imports without errors."""
        from scripts.train_smart import AugDataset, mixup_collate
        assert AugDataset is not None
        assert mixup_collate is not None

    def test_mixup_collate(self):
        """Verify mixup_collate function works."""
        from scripts.train_smart import mixup_collate
        with torch.no_grad():
            batch = [
                (torch.randn(32), torch.randint(0, 10, (5,)), 
                 torch.tensor(0), torch.tensor(1), torch.tensor(2))
                for _ in range(8)
            ]
            X, C, Y5, Y15, Y30 = mixup_collate(batch)
            assert X.shape == (8, 32)
            assert C.shape == (8, 5)
            assert Y5.shape == (8,)

    def test_vm_h200_script_exists(self):
        """Verify vm_h200.sh exists."""
        script = Path("scripts/vm_h200.sh")
        assert script.exists()
        content = script.read_text(encoding="utf-8", errors="ignore")
        assert "H200" in content or "torchrun" in content or "train" in content


class TestIntegration:
    """Cross-component integration tests."""

    def test_all_scripts_importable(self):
        """Verify all main scripts can be imported."""
        scripts_to_test = [
            "scripts.export_mt5_all_brokers",
            "scripts.train_smart",
        ]
        for script_path in scripts_to_test:
            try:
                __import__(script_path)
            except ImportError as e:
                if "MetaTrader5" in str(e):
                    pytest.skip(f"Optional dependency: {e}")
                else:
                    raise

    def test_no_syntax_errors(self):
        """Compile all Python files to check syntax."""
        import py_compile
        python_files = [
            "scripts/export_mt5_all_brokers.py",
            "scripts/train_smart.py",
            "scripts/scan_mt5.py",
        ]
        for pf in python_files:
            py_compile.compile(pf, doraise=True)


@pytest.mark.parametrize("script_path", [
    "scripts/export_mt5_all_brokers.py",
    "scripts/train_smart.py",
])
def test_scripts_exist(script_path):
    """Verify all required scripts exist."""
    assert Path(script_path).exists()
