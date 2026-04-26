.PHONY: help install install-dev test test-fast lint format typecheck coverage clean docker docker-up docker-down k8s-apply k8s-delete hooks

PYTHON ?= python
PIP    ?= pip
PKGS   := aphelion mt5pipe machinelearning scripts

help:
	@echo "Dominion Makefile targets:"
	@echo "  install       - pip install -e ."
	@echo "  install-dev   - pip install -e .[ml,tui,dev]"
	@echo "  test          - full pytest suite"
	@echo "  test-fast     - pytest -x -q (fail-fast)"
	@echo "  lint          - ruff check"
	@echo "  format        - ruff format"
	@echo "  typecheck     - mypy on core/feature_engine/inference"
	@echo "  coverage      - pytest with coverage report"
	@echo "  hooks         - install pre-commit hooks"
	@echo "  docker        - build docker image"
	@echo "  docker-up     - docker compose up"
	@echo "  docker-down   - docker compose down"
	@echo "  k8s-apply     - apply k8s manifests"
	@echo "  k8s-delete    - delete k8s manifests"
	@echo "  clean         - remove build/test artifacts"

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[ml,tui,dev]" ruff mypy pre-commit

test:
	pytest tests/ machinelearning/tests/ -v

test-fast:
	pytest tests/ machinelearning/tests/ -x -q

lint:
	ruff check $(PKGS)

format:
	ruff format $(PKGS)

typecheck:
	mypy aphelion/core aphelion/feature_engine aphelion/inference

coverage:
	pytest tests/ machinelearning/tests/ \
	  --cov=aphelion --cov=mt5pipe --cov=machinelearning \
	  --cov-report=term --cov-report=html --cov-report=xml

hooks:
	pre-commit install
	pre-commit install --hook-type commit-msg

docker:
	docker build -t dominion:dev .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

k8s-apply:
	kubectl apply -f k8s/

k8s-delete:
	kubectl delete -f k8s/

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
