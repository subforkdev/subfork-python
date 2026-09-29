PYTHON ?= python

.PHONY: format lint typecheck test check build
format:
	$(PYTHON) -m isort src tests scripts
	$(PYTHON) -m black src tests scripts

lint:
	$(PYTHON) -m black --check src tests scripts
	$(PYTHON) -m isort --check-only src tests scripts
	$(PYTHON) -m flake8 src tests scripts

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

check: lint typecheck test check-version

build: check-version
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*

.PHONY: version check-version bump-patch bump-minor bump-major bump-version
export VERSION

version:
	@$(PYTHON) scripts/bump-version.py --show

check-version:
	@$(PYTHON) scripts/bump-version.py --check

bump-patch bump-minor bump-major:
	@$(PYTHON) scripts/bump-version.py --bump $(@:bump-%=%)

bump-version:
	@$(PYTHON) scripts/bump-version.py --set
