PYTHON ?= python
VARIANT ?= FULL

.PHONY: setup lint test test-unit test-integration validate-config package package-all verify-submission sync docs adk-conformance baseline competition-audit release-manifest check-release check

setup:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest -m unit

test-integration:
	$(PYTHON) -m pytest -m local_integration

sync:
	$(PYTHON) scripts/build_submission.py --sync

docs:
	$(PYTHON) scripts/generate_docs.py

validate-config:
	$(PYTHON) scripts/build_submission.py --check-sync
	$(PYTHON) scripts/generate_docs.py --check
	$(PYTHON) scripts/validate_submission.py submission --strict

# Needs: pip install google-adk==2.9.2
adk-conformance: package
	$(PYTHON) scripts/adk_conformance.py dist/submission.zip --out artifacts/audits/adk_conformance.json

package:
	$(PYTHON) scripts/build_submission.py --variant $(VARIANT) --strict

package-all:
	$(PYTHON) scripts/build_submission.py --all --strict
	$(PYTHON) scripts/build_submission.py --check-manifest

verify-submission:
	$(PYTHON) scripts/validate_submission.py dist/submission.zip --strict

# Prepares a frozen baseline run directory; running it needs the competition harness.
baseline:
	$(PYTHON) scripts/run_experiment.py prepare --variant B0 --require-clean

# Detects official artifacts in external/competition/ (docs/HUMAN_HANDOFF.md), audits them
# and prints the next command. Exit 3 means artifacts are still missing.
competition-audit:
	$(PYTHON) scripts/competition_bootstrap.py

# Release manifest from a clean tree; commit dist/release_manifest.json on its own afterwards.
release-manifest:
	$(PYTHON) scripts/build_submission.py --all --strict --require-clean

check-release:
	$(PYTHON) scripts/build_submission.py --check-release

check: lint test validate-config package verify-submission
