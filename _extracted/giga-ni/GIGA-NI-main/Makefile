.PHONY: help install test test-fast lint types format clean check-all backtest docs

help:
	@echo "Aphelion GIGA-NI Development Commands"
	@echo "======================================"
	@echo "make install       Install dependencies"
	@echo "make test          Run unit tests with coverage"
	@echo "make test-fast     Stop on first test failure"
	@echo "make lint          Run ruff linter + formatter check"
	@echo "make types         Run pyright type checker"
	@echo "make format        Auto-format code with ruff"
	@echo "make clean         Remove caches and coverage outputs"
	@echo "make check-all     Run tests + lint + types"
	@echo "make backtest      Run backtest suite"
	@echo "make docs          Show docs location"

install:
	pip install --upgrade pip setuptools wheel
	pip install -e ".[dev,ml,tui]"
	pip install pyright ruff pytorch-lightning loguru

test:
	pytest tests/ machinelearning/tests/ -v --tb=short --cov=aphelion --cov=machinelearning --cov=mt5pipe --cov-report=term-missing

test-fast:
	pytest tests/ machinelearning/tests/ -v --tb=line -x

lint:
	ruff check aphelion/ machinelearning/ mt5pipe/ tests/
	ruff format --check aphelion/ machinelearning/ mt5pipe/ tests/

types:
	pyright aphelion/ machinelearning/ mt5pipe/ --level=basic

format:
	ruff format aphelion/ machinelearning/ mt5pipe/ tests/
	ruff check --fix aphelion/ machinelearning/ mt5pipe/ tests/

backtest:
	pytest tests/backtest/ -v --tb=short

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage coverage.json coverage.xml htmlcov dist build *.egg-info

check-all: test lint types
	@echo "All checks passed. Ready to commit."

docs:
	@echo "See docs/CI_CD.md"
