# Scorer fidelity

`aeris_comp/scoring.py` is a local approximation of the official grader. It is used for development only; reported results must come from the official grader, or state the measured agreement with it.

## Status

| Item | Status |
| --- | --- |
| Agreement tool (`python scripts/run_experiment.py fidelity ours.jsonl official.jsonl`) | LOCALLY_TESTED (`tests/test_research_tooling.py::test_scorer_agreement`) |
| Measured agreement on real predictions | **BLOCKED** (gap X-05): needs official grades for at least one run |

## What the local scorer does

1. Extract the task snapshot at `base_commit`.
2. `git apply --check`, then apply the prediction. An empty prediction gives `NO_PATCH`; an apply failure gives `APPLY_FAILED`.
3. Apply `test_patch` on top. A conflict gives `TEST_PATCH_CONFLICT`.
4. Optionally run a setup command (the dataset's `sandbox/setup.py`).
5. Run `pytest -q -p no:cacheprovider` on the Python files touched by `test_patch`. Exit code 0 is `PASS`; a timeout is `TIMEOUT`.

## Known or suspected divergences from the official grader

| Divergence | Direction of error | How to settle it |
| --- | --- | --- |
| We run whole test files from `test_patch`; the grader may run a FAIL_TO_PASS / PASS_TO_PASS list | Can pass or fail differently: unrelated failing tests in the same file make us stricter; untouched regression tests make us more lenient | Read HARNESS_README (C-01), then compare with `fidelity` |
| Local environment differs from the sandbox (Python 3.13, offline `/wheels`) | Mostly false FAILs from missing dependencies (`SETUP_FAILED`) | Run the scorer inside the dataset's container image when available |
| Timeout value (900 s default) is our choice | Either way | Use the official value once known |
| Flaky tests | Either way | Score twice; report disagreements |

## Acceptance rule

Before any result from the local scorer goes into the paper, run `fidelity` on at least one full run that was also graded officially. If agreement is below 95%, or the two pass rates differ by more than one task per 50, use only official grades and report the disagreement cases.
