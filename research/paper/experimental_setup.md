# Experimental setup

- **Tasks**: the 129 public competition tasks from four repositories (fastapi, rich, requests, httpx), split 70/30 into dev and held-out, stratified by repository, with a fixed seed (`aeris_comp/split.py`; the split file records SHA256 fingerprints). [PENDING: split file, X-04]
- **Harness**: the official competition harness, one sandbox per task, Python 3.13, offline. [PENDING: harness version]
- **Grading**: official grader. [PENDING: local-scorer agreement from docs/SCORER_FIDELITY.md]
- **Variants**: B0 to B5 and FULL (a cumulative ladder) plus five single-component ablations; the no-reviewer ablation is B5. Every variant has the same model, sampling and budget, and its archive hash is recorded in `dist/release_manifest.json`.
- **Statistics**: PASS rate with Wilson 95% intervals; paired variant comparisons with the exact McNemar test on shared tasks; localization Recall@k and MRR against the files changed by the reference patch; calibration with AUROC (Hanley-McNeil interval), Brier score and ECE.
- **Protocol**: all tuning on dev; the final variant is chosen by the rule in docs/FINAL_VARIANT_DECISION.md and scored on held-out exactly once.
- **Repetitions**: [PENDING: number of repeated runs per variant, given the 12-hour budget]
