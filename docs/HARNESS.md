# Harness notes

What we know about the evaluation harness, and what we still need from `HARNESS_README.md` (see [COMPETITION_REQUIREMENTS.md](COMPETITION_REQUIREMENTS.md) for sources and status).

## Known (verified from the competition pages)

- Each task runs in a sandbox: Python 3.13, git and pytest, the repository in `/workspace` at `base_commit`, dependencies installed in editable mode from `/wheels` by `sandbox/setup.py`, and a clean baseline commit, so `git diff HEAD` equals our changes.
- A "two-container sandbox lifecycle" exists; the details are in `HARNESS_README.md`.
- Tools: `run_command`, `submit_patch`, `get_status`, `read_file`, `edit_file`, `write_file`, `get_code_neighbors`, `search_similar_code`, `get_code_subgraph`, plus skill tools (`run_skill_script`, `load_skill_resource`).
- `submit_patch` runs `git add -N .` and then `git diff HEAD`, so untracked files are included.
- The output is `submission.parquet` (`id`, `prediction`; `NO_PATCH` when empty).
- The libraries are `swegemma`, `adk-submission` and `adk-eval-core`, with local CLI evaluation commands described in `HARNESS_README.md`.

## Unknown (blocked until the dataset is accessible)

- Tool-reference syntax in `agent.yaml` and how skills are attached.
- Which `run_skill_script` mode the harness uses (ADK code executor vs environment `command` string). The ADK signatures themselves are known (R-SKILL-3b) and our scripts accept every form.
- `get_status()` output format.
- Context length and the compaction policy.
- The `eval_config.yaml` schema.
- Whether a plain-text reply ends a task (true in the sibling competition).

## Getting the dataset

1. Sign in to Kaggle and accept the competition rules.
2. `kaggle competitions download -c gemma-4-developer-agent` (22 GB; the snapshots, graphs and embeddings are most of it). Or download `HARNESS_README.md`, `sample_submission/`, `tasks.jsonl` and a few snapshots individually from the Data tab.
3. Put them under `external/competition/` (git-ignored), run `python scripts/competition_bootstrap.py`, and update [COMPETITION_REQUIREMENTS.md](COMPETITION_REQUIREMENTS.md) rows R-TOOLS-2, R-SKILL-3, R-BUDGET-2 and R-BUDGET-3. Exact steps: [HUMAN_HANDOFF.md](HUMAN_HANDOFF.md).

Never commit dataset files: they are covered by the competition rules.
