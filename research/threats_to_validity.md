# Threats to validity

## Benchmark representativeness

The public tasks come from four well-known libraries (fastapi, rich, requests, httpx), and the hidden test set comes from private repositories. Gains that rely on familiarity with public repositories (from pretraining or from our prompt iteration) may not transfer. Mitigations: no repository-specific prompt content, and a held-out public split.

## Contamination

The public repositories and their fixes are probably in Gemma's pretraining data, so dev-set PASS rates may be inflated relative to the hidden set. The public-leaderboard score is reported separately, and absolute numbers are not compared across benchmarks. Any LoRA training data must exclude held-out tasks and must not be derived from reference patches of the tasks it is evaluated on.

## Model-specific effects

All results are for `gemma-4-31b-it-qat-w4a16-ct` under the competition serving stack. The quantization and the tool-call parser behaviour (see the reported vLLM Gemma 4 tool-parser issues) can dominate outcomes and may not generalize to other models or runtimes.

## Graph and embedding quality

The graph is static AST analysis: dynamic dispatch, decorators and registries are missing edges. The embeddings are 256-dimensional, from an undisclosed encoder. A null result for H1 or H2 may reflect tool quality rather than the value of structure in general. We report graph coverage issues seen in traces.

## Stochasticity

Temperature 1.0 sampling makes single runs noisy. With about 60 tasks, the 95% interval on the PASS rate is roughly ±12 points. Repeated runs and paired tests are required, and single-run differences below that are not claimed.

## Hidden-test uncertainty

The local scorer approximates the grader (test selection and apply command). Local PASS may differ from official PASS. Fidelity is checked on reference patches before any result is used.

## Compute budget

The 12-hour budget is shared across tasks. A variant that spends more per task can gain PASS rate locally, with generous per-task limits, but lose it under the real global budget. Compared variants use identical per-task limits, and budget exhaustion is recorded as a failure category.

## Self-reported confidence

Hypothesis weights are produced by the model and may be uncalibrated or anchored on the first hypothesis. H6 tests this directly. Until then, no probabilistic interpretation is claimed.

## Researcher degrees of freedom

Prompt iteration on the dev split can overfit. Variants are frozen (git SHA plus archive hash) before held-out runs, and every run, including negative and aborted ones, is kept in `artifacts/runs/`.
