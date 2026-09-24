# Methodology

## Data

- Development: the 129 public tasks (`tasks.jsonl`: fastapi, rich, requests, httpx).
- Split the public tasks once, by repository-stratified random sampling with a recorded seed, into:
  - dev (about 70%), used for prompt and policy iteration;
  - held-out (about 30%), used only for frozen-variant comparisons.
  Record the split file in `research/results/` before the first measured run.
- The hidden test set comes from private repositories. The public leaderboard is an additional, noisy out-of-distribution check. It must not be used for iterative tuning, since that overfits to about 30 tasks.

## Protocol

1. Freeze the variant: commit, then `run_experiment.py prepare --variant X`. The manifest records the git SHA and the archive SHA-256.
2. Run the harness on the fixed task list, with the same budget per task for every variant.
3. Score with `run_experiment.py score` inside the competition Docker image.
4. Check scorer fidelity once (the reference patches must PASS; see docs/EXPERIMENTS.md).
5. Label every non-PASS task with a failure category from trace review. The labeler does not see the variant name where practical.
6. Keep all raw outputs (`records.jsonl`, `summary.json`, `manifest.json`, harness traces) under `artifacts/runs/`, including failed or aborted runs.

## Controls

- Same model, sampling config, task list, time budget and harness version across compared variants.
- Stochasticity: sampling uses temperature 1.0. Repeat each compared variant at least 3 times when budget allows, and report the mean and spread per variant as well as the per-run paired tests.
- Order effects: randomize the task order per run if the harness processes tasks sequentially under the global budget.

## Sampling configuration

`submission/configs/sampling.yaml` uses Google's recommended Gemma 4 defaults (temperature 1.0, top_p 0.95, top_k 64). Sampling is an experiment variable. A lower-temperature variant must be added as a separate sampling file plus a variant, never by editing the default in place during a comparison.

## Fine-tuning gate (Phase 9)

A LoRA is considered only if baseline traces show a failure category that is:
- frequent (at least 20% of failures);
- plausibly learnable from trajectories (for example TOOL_MISUSE, PATCH_FAILURE on correctly localized tasks);
- not fixable by a prompt change (a prompt fix was tried and measured).

Training data must exclude every held-out and hidden-test repository. See `adapters/README.md`.
