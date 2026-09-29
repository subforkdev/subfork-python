PYTHON ?= python

.PHONY: format lint typecheck test check build
format:
	$(PYTHON) -m isort src tests
	$(PYTHON) -m black src tests

lint:
	$(PYTHON) -m black --check src tests
	$(PYTHON) -m isort --check-only src tests
	$(PYTHON) -m flake8 src tests

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

check: lint typecheck test

build:
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*
