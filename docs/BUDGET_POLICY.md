# Budget policy

The official budget is 12 hours of wall-clock time for all tasks, including sandbox setup and excluding patch validation (R-BUDGET-1, verified from the Kaggle page). Per-task limits exist through an optional `eval_config.yaml` whose schema is unknown (C-12, BLOCKED), so we ship none and manage budget per task inside the agent.

Every number below is **provisional**. None has been tuned yet, because tuning needs harness runs (X-06). When they are tuned, it will be on the dev split only.

## Budget modes

The agent reads the fraction of budget used from `get_status()` (format unknown, C-13) and passes it to the ledger: `ledger.py status --budget-used F`.

| Mode | Budget used | Evidence needed for LOW uncertainty (top weight, with supporting evidence) | Weight below which uncertainty is HIGH | Behaviour |
| --- | --- | --- | --- | --- |
| NORMAL | below 0.5 | 0.6 | 0.4 | Investigate, discriminate between hypotheses, patch when uncertainty is LOW |
| CONSERVATIVE | 0.5 to below 0.8 | 0.5 | 0.3 | Lower bar to patch; prefer the cheapest discriminating check |
| CRITICAL | 0.8 and above | 0.5 | 0.3 | Patch the top hypothesis now (or keep the best existing patch), validate once, submit |

Source: `submission/skills/ledger/scripts/ledger.py` (`BUDGET_MODES`, `THRESHOLDS`, `assess`); tests in `tests/test_ledger.py`.

## Hard limits

| Limit | Value | Action when reached |
| --- | --- | --- |
| Patch attempts per task | 3 (`MAX_PATCH_ATTEMPTS`) | Restore the best attempt and submit |
| Investigation steps without a patch | 8 (`MAX_INVESTIGATION_STEPS`) | Patch the top hypothesis and let tests provide evidence |
| Same test failure signature | Flagged `REPEATED` from the second occurrence | Change approach; two failed patches for one hypothesis trigger a "lower its weight" note |
| Test run timeout | 300 s per `run_tests.py` call | Narrow the selection |

A task never ends without `submit_patch`: an empty submission always fails, while a partial fix can pass.

## Confidence vs evidence gating

The ledger's weights are the model's own confidence and may not be calibrated. Once dev-split data exists:

1. Compute `calibration_report(confidences, outcomes)` over patch attempts, where the confidence is the top weight at patch time and the outcome is whether the attempt passed the hidden tests.
2. If `confidence_has_signal` is False (the AUROC 95% interval includes 0.5), switch gating to evidence counts only: LOW uncertainty requires at least two supporting items and no contradicting item, whatever the stated weight. Record the switch in [FINAL_VARIANT_DECISION.md](FINAL_VARIANT_DECISION.md).
3. If it is True, keep weight thresholds but re-fit them on the dev split, choosing the lowest bar whose precision is at least 0.6.

Status: the rule is written and `calibration_report` is tested (E-07). The measurement is BLOCKED (X-09).

## What we will measure

For every variant, per task: wall time, tool calls, patch attempts, mode at submission, and whether the task ended by budget. These come from telemetry (`budget_status`, `patch_attempt`) and from harness traces once available.
