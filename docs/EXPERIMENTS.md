# Experiments

## Variants

Variant files live in `experiments/configs/`. Each lists enabled components from `experiments/components.yaml`.

| Variant | Components | Purpose |
| --- | --- | --- |
| B0 | core | Vanilla baseline |
| B1 | + semantic_retrieval | Effect of embedding search |
| B2 | + graph_navigation | Effect of graph expansion |
| B3 | + hypothesis_tracking | Effect of explicit hypotheses |
| B4 | + uncertainty_gating | Effect of gating edits on confidence |
| B5 | + failure_feedback | Effect of structured failure signatures |
| FULL | + reviewer | Default submission; B5 is also the "no reviewer" ablation |
| ABL_no_retrieval | FULL − semantic_retrieval | Leave-one-out |
| ABL_no_graph | FULL − graph_navigation | Leave-one-out |
| ABL_no_hypotheses | FULL − hypothesis_tracking − uncertainty_gating | Leave-one-out (gating depends on hypotheses) |
| ABL_no_uncertainty | FULL − uncertainty_gating | Leave-one-out |
| ABL_no_feedback | FULL − failure_feedback | Leave-one-out |

B6 (adapter) is not defined: no adapter exists and none is justified yet (see `adapters/README.md`).

## Workflow

```bash
# 1. Freeze: commit first, so the manifest records a clean git SHA.
python scripts/run_experiment.py prepare --variant B0 --notes "first baseline"
#    -> artifacts/runs/<run_id>/{submission.zip, manifest.json}

# 2. Run the agent with the competition harness (HARNESS_README.md, local CLI) on a fixed
#    task list, producing submission.parquet. Not automated here: the harness is not available yet.

# 3. Score locally (inside the provided Docker image for faithful dependencies).
python scripts/run_experiment.py score --run-dir artifacts/runs/<run_id> \
    --tasks data/tasks.jsonl --snapshots data/snapshots --predictions path/to/submission.parquet \
    --setup-cmd "python /path/to/sandbox/setup.py"

# 4. Summarize or compare.
python scripts/run_experiment.py summarize artifacts/runs/<run_id>
python scripts/run_experiment.py compare artifacts/runs/<run_B0> artifacts/runs/<run_B1>
```

## Run records

`records.jsonl` has one JSON object per task. The scorer fills `instance_id`, `status`, `detail`, `files_changed`, `lines_added`, `lines_removed`, `test_files`, `scoring_seconds` and `failure_category` (automatic for `NO_PATCH`, `APPLY_FAILED` and `TEST_PATCH_CONFLICT`).

Fields from harness traces, which are added once the trace format is known: `wall_time_s`, `tool_calls`, `commands`, `files_inspected`, `retries`. For `FAIL`, `failure_category` is assigned by manual trace review against `aeris_comp/taxonomy.py`. `summarize` rejects unknown categories.

## Local scorer fidelity

`aeris_comp/scoring.py` applies the prediction, applies `test_patch`, and runs pytest on the test files touched by `test_patch`. It differs from the official grader in ways we cannot yet check:

- The test selection may differ (the official grader may use FAIL_TO_PASS/PASS_TO_PASS lists).
- The apply command may differ (`git apply` versus `patch`), as may tolerance to whitespace.
- The environment differs unless it is run inside the competition Docker image with `sandbox/setup.py`.

Validate fidelity before trusting it: scoring each task's reference `patch` must give PASS on all 129 public tasks, and scoring an empty prediction must give no PASS.

## Statistics

- Primary: PASS rate with a Wilson 95% interval.
- Variant comparison: a paired exact McNemar test on shared tasks (`compare`).
- With about 60 tasks, only large effects are detectable. Repeat runs with different sampling seeds when possible, and report every run.
