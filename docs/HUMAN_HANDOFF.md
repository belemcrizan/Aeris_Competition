# Human handoff: supplying the official competition artifacts

Everything below the P0 step in the plan (official audit, first B0 run, split, baseline, experiments, submission) waits on files that require a human Kaggle login and rules acceptance, which cannot be automated from here. This page lists exactly what is needed, where to put it, and how to check that the system picked it up.

**Never commit credentials.** `kaggle.json`, `.env` and everything under `external/` and `data/` are gitignored. No step below asks you to paste a token into a file in this repository.

## 1. Accept the rules (browser, human only)

1. Sign in at <https://www.kaggle.com> with the account that will compete.
2. Open <https://www.kaggle.com/competitions/gemma-4-developer-agent/rules> and click **I Understand and Accept**. Downloads return 403 until this is done.

## 2. Download the data (either option)

The full dataset is about 22 GB, mostly snapshots, graphs and embeddings. The audit and the split need only `HARNESS_README.md`, `sample_submission/` and the task list, which can be downloaded individually from the Data tab. The first real task additionally needs its snapshot.

**Option A: browser.** On the competition **Data** tab, click **Download All** (or download the individual files) and unzip into `external/competition/` at the repository root.

**Option B: Kaggle CLI.** The token stays in your user profile, outside the repository.

```powershell
python -m pip install kaggle
# Create a token at https://www.kaggle.com/settings -> API -> "Create New Token".
# Save it as %USERPROFILE%\.kaggle\kaggle.json (NOT inside this repository).
kaggle competitions download -c gemma-4-developer-agent -p external/competition
Expand-Archive external/competition/gemma-4-developer-agent.zip -DestinationPath external/competition
```

A `kaggle.json` from 2025 exists in `Downloads\docs\docs\`. It was not opened or used. If it is yours and still valid, you may move it to `%USERPROFILE%\.kaggle\`. Otherwise create a fresh token and delete the old file.

## 3. What must end up in `external/competition/`

The layout inside does not matter: the bootstrap searches up to 6 levels deep.

| Needed | How it is recognised | Unblocks (docs/gaps.yaml) |
| --- | --- | --- |
| `HARNESS_README.md` | file name starts with `HARNESS_README` | C-01, C-07, C-12 to C-15, E-05 |
| `sample_submission/` (directory or `sample_submission*.zip`) | contains `agent.yaml` | C-02, C-05, C-16 |
| Task list | a `.jsonl` whose first row has `instance_id` | X-04 (split), smoke selection |
| Snapshots, graphs, embeddings, eval code | everything else, recorded by suffix in the inventory | X-01, X-05, scoring |

To keep the data elsewhere, set `AERIS_COMPETITION_DIR` to that directory instead:

```powershell
$env:AERIS_COMPETITION_DIR = "D:\kaggle\gemma-4-developer-agent"
```

## 4. Verify and continue (automatic)

```powershell
python scripts/competition_bootstrap.py      # or: make competition-audit
```

| Exit code | Meaning | Next |
| ---: | --- | --- |
| 3 | Something is still missing; the `[MISSING]` lines say what | Add it and rerun |
| 1 | An INCOMPATIBLE finding in `artifacts/audits/sample_submission_diff.md`, our validator rejecting the official sample, or an invalid split | Fix it (agent work), rerun |
| 0 | Everything present and compatible | The printed `[NEXT]` command: prepare B0 for the first real task |

After exit 0, commit `research/results/data_split.json` right away: from that moment the held-out half is frozen.

## 5. Running the agent (needs HARNESS_README)

How to run the harness and which Gemma 4 endpoint it uses is documented only in HARNESS_README. The sequence below covers the parts that do not depend on it:

```powershell
git status --short                                          # must be empty
python scripts/run_experiment.py prepare --variant B0 --require-clean --run-id first_task_B0
# run artifacts/runs/first_task_B0/submission.zip on ONE task with the harness (per HARNESS_README)
python scripts/run_experiment.py score --run-dir artifacts/runs/first_task_B0 `
  --tasks <tasks.jsonl> --snapshots <snapshots dir> --predictions <harness predictions> --limit 1
```

## 6. Uploading to Kaggle (release, human only)

Upload `dist/submission.zip` on the competition **Submit** page only after `docs/RELEASE_CHECKLIST.md` passes. Then record the date, archive SHA-256, commit and public result in `docs/FINAL_VARIANT_DECISION.md`.
