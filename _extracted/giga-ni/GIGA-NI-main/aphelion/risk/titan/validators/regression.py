"""
TITAN — Regression Validator
Ensures new changes don't degrade existing performance.
"""

from aphelion.risk.titan.gate import RegressionValidator

__all__ = ["RegressionValidator"]
