# Metrics

## Primary

PASS rate: the share of tasks whose patch makes the validation tests pass. It is reported with a Wilson 95% interval (`aeris_comp/metrics.py::wilson_interval`). No secondary metric may be improved at the expense of the PASS rate.

## Secondary (per task, mean and median)

| Metric | Source | Status |
| --- | --- | --- |
| Wall time | Harness trace | Needs the trace format |
| Tool calls, commands | Harness trace | Needs the trace format |
| Files inspected | Harness trace (distinct `read_file` paths) | Needs the trace format |
| Changed files, changed LOC | Scorer (`files_changed`, `lines_added + lines_removed`) | Implemented |
| Retries | Ledger patch attempts or distinct test signatures | Implemented in the skill, extraction pending |
| Unnecessary-patch rate | Diff files not touched by the reference patch | Planned |
| Exploration cost | Tool calls before the first edit | Needs the trace format |
| Validation cost | Test commands and their time | Needs the trace format |

## Comparisons

- Paired exact McNemar test on shared tasks (`paired_comparison`).
- Report every comparison that was run, not only the significant ones.

## Failure taxonomy

Defined in `aeris_comp/taxonomy.py`:

- LOCALIZATION_FAILURE
- ROOT_CAUSE_FAILURE
- CONTEXT_FAILURE
- PATCH_FAILURE
- TEST_SELECTION_FAILURE
- REGRESSION_FAILURE
- TOOL_MISUSE
- GRAPH_EXPLOSION
- BUDGET_EXHAUSTION
- LOOPING
- OVER_EDITING
- UNDER_EDITING
- INVALID_SUBMISSION

The scorer labels mechanical outcomes automatically:
- NO_PATCH and APPLY_FAILED become INVALID_SUBMISSION;
- TEST_PATCH_CONFLICT becomes OVER_EDITING.

Other failures are labeled from traces. A useful heuristic for LOCALIZATION_FAILURE: the files in the predicted patch do not overlap the files in the reference `patch`.

## Calibration (hypothesis H6)

For tasks where the ledger was used, extract the top weight and the normalized entropy at the first patch attempt. Report AUROC against final PASS, with a bootstrap CI. Until this is measured, the weights are described only as "model-reported confidence".
