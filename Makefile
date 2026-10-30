PYTHON ?= python

.PHONY: install lint type test check

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

type:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest -q

check: lint type test
