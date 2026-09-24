# Release checklist

State on 2026-09-24, branch `phase3-empirical-readiness`. Legend: PASS, FAIL, BLOCKED, N/A. A release candidate (RC1, RC2, ...) is rejected if any mandatory row is FAIL; it is fixed and rebuilt as the next RC.

| # | Check | How | State |
| --- | --- | --- | --- |
| 1 | Lint clean | `make lint` | PASS |
| 2 | UNIT and LOCAL_INTEGRATION tests green | `make test` | PASS |
| 3 | Rendered `agent.yaml` / `system.md` in sync with modules | `build_submission.py --check-sync` | PASS |
| 4 | Generated docs up to date | `generate_docs.py --check` | PASS |
| 5 | Every variant builds with 0 errors and 0 warnings | `build_submission.py --all --strict` | PASS |
| 6 | Release manifest matches a fresh rebuild (content hashes) | `build_submission.py --check-manifest` | PASS |
| 7 | Manifest built from a clean commit, nothing but the manifest changed since | `build_submission.py --check-release` | PASS |
| 8 | No secrets, credential, symlink, traversal or junk entries in any archive | Blocking policy checks in the builder and validator | PASS |
| 9 | ADK 2.9.2 accepts every variant's `agent.yaml` and skills | `adk_conformance.py` (CI job `adk-conformance`) | PASS |
| 10 | CI green | GitHub Actions | PASS on `main` 161ef7b; re-check on this PR |
| 11 | Diff against `sample_submission` has no INCOMPATIBLE finding | `competition_bootstrap.py` -> `artifacts/audits/sample_submission_diff.md` | BLOCKED (C-02) |
| 12 | HARNESS_README rules re-checked | docs/COMPETITION_REQUIREMENTS.md | BLOCKED (C-01) |
| 13 | Official harness smoke run of the release candidate | FIRST_PASS.md / run directory | BLOCKED (X-01, L-07) |
| 14 | Final variant chosen by the written rule | docs/FINAL_VARIANT_DECISION.md | BLOCKED (L-03) |
| 15 | Held-out result recorded once | research/results/ | BLOCKED (X-10) |
| 16 | Archive accepted by the Kaggle platform | Upload (human) | BLOCKED (L-04) |
| 17 | LoRA adapter validated | Validator adapter checks | N/A (no adapter; see FINAL_VARIANT_DECISION.md) |
| 18 | `eval_config.yaml` | Not shipped | N/A (optional; schema BLOCKED, C-12) |

## Manifest provenance

`dist/release_manifest.json` is committed. The release procedure is:

1. Commit every change.
2. Run `make release-manifest` (`--all --strict --require-clean`). It refuses a dirty tree, so `git.dirty` is false and `git.commit` is the tested commit.
3. Commit `dist/release_manifest.json` alone.
4. `make check-release` verifies that the recorded commit is clean and that only the manifest changed after it, then rebuilds every variant and compares `content_sha256`.

Each variant entry records the archive SHA-256, `content_sha256`, the SHA-256 of `agent.yaml`, every prompt file, the sampling config and any adapter file, plus the validator result.
