# Release checklist

State on 2026-09-24, branch `phase2-gap-closure`. Legend: PASS, FAIL, BLOCKED, N/A.

| # | Check | How | State |
| --- | --- | --- | --- |
| 1 | Lint clean | `make lint` | PASS |
| 2 | UNIT and LOCAL_INTEGRATION tests green | `make test` | PASS |
| 3 | Rendered `agent.yaml` / `system.md` in sync with modules | `build_submission.py --check-sync` | PASS |
| 4 | Generated docs up to date | `generate_docs.py --check` | PASS |
| 5 | Every variant builds with 0 errors and 0 warnings | `build_submission.py --all --strict` | PASS |
| 6 | Release manifest matches a fresh rebuild (content hashes) | `build_submission.py --check-manifest` | PASS |
| 7 | No secrets, credential or junk files in any archive | Blocking policy checks in the builder | PASS |
| 8 | ADK 2.9.2 accepts every variant's `agent.yaml` and skills | `adk_conformance.py` (CI job `adk-conformance`) | PASS |
| 9 | CI green on the pull request | GitHub Actions | BLOCKED until the PR run finishes |
| 10 | Diff against `sample_submission` reviewed | `artifacts/audits/sample_submission_diff.md` | BLOCKED (C-02) |
| 11 | HARNESS_README rules re-checked | docs/COMPETITION_REQUIREMENTS.md | BLOCKED (C-01) |
| 12 | Harness run of the chosen variant on at least one task | FIRST_PASS.md | BLOCKED (X-01, X-02) |
| 13 | Final variant chosen by the written rule | docs/FINAL_VARIANT_DECISION.md | BLOCKED (L-03) |
| 14 | Held-out result recorded once | research/results/ | BLOCKED (X-10) |
| 15 | Archive accepted by the Kaggle platform | Upload | BLOCKED (L-04) |
| 16 | LoRA adapter validated | Validator adapter checks | N/A (no adapter; see FINAL_VARIANT_DECISION.md) |
| 17 | `eval_config.yaml` | Not shipped | N/A (optional; schema BLOCKED, C-12) |

`dist/release_manifest.json` is committed. Its `git.commit` is the commit it was built on, and `git.dirty` is true when uncommitted changes were included: the committed copy is always built one commit earlier than the one containing it. The reproducibility guarantee is `content_sha256`, which CI checks against a fresh build.
