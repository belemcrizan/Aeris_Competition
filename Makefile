PYTHON ?= python
VARIANT ?= FULL

.PHONY: setup lint test validate-config package package-all verify-submission sync baseline check

setup:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest

sync:
	$(PYTHON) scripts/build_submission.py --sync

validate-config:
	$(PYTHON) scripts/build_submission.py --check-sync
	$(PYTHON) scripts/validate_submission.py submission --strict

package:
	$(PYTHON) scripts/build_submission.py --variant $(VARIANT) --strict

package-all:
	$(PYTHON) scripts/build_submission.py --all --strict

verify-submission:
	$(PYTHON) scripts/validate_submission.py dist/submission.zip --strict

# Prepares a frozen baseline run directory; running it needs the competition harness.
baseline:
	$(PYTHON) scripts/run_experiment.py prepare --variant B0

check: lint test validate-config package verify-submission
