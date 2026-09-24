# Building and validating the submission

## Build

```bash
python scripts/build_submission.py                  # FULL variant -> dist/submission.zip
python scripts/build_submission.py --variant B0     # -> dist/B0/submission.zip
python scripts/build_submission.py --all            # every variant
```

The build:

1. Resolves the variant into tools, prompt modules and skills, and enforces component dependencies.
2. Stages a fresh tree:
   - `agent.yaml`
   - `prompts/system.md` (the concatenated modules)
   - `configs/sampling.yaml`
   - the selected `skills/`
   - `adapters/<name>/` only when the variant names an adapter.
3. Validates the staged tree, writes a deterministic zip (sorted entries, fixed timestamps and permissions), and validates the zip again.
4. Prints the SHA-256 of the archive. The same inputs always give the same hash.

The build exits non-zero on any validation error. Use `--strict` to also fail on warnings.

## Checked-in rendering

`submission/agent.yaml` and `submission/prompts/system.md` are the rendered FULL variant, committed so reviewers can read them. Do not edit them by hand. Edit the modules in `submission/prompts/modules/`, then run:

```bash
python scripts/build_submission.py --sync        # regenerate
python scripts/build_submission.py --check-sync  # CI / test guard
```

`submission/prompts/modules/` is never shipped.

## Validate any archive

```bash
python scripts/validate_submission.py dist/submission.zip
python scripts/validate_submission.py path/to/unpacked_dir --strict
```

Checks performed (codes appear in the output):

| Area | Checks |
| --- | --- |
| Archive | `agent.yaml` at the root (with a hint when it is nested), no absolute, `..` or backslash entries, no symlink entries, no duplicates, size limit |
| YAML | Parses, no duplicate keys, only ADK `LlmAgentConfig` fields plus `adapter`, no code-referencing fields |
| Includes | Relative to the containing file, inside the root, no symlinks, target exists |
| Agents | `model` equals the competition model on every agent, including `sub_agents` and `AgentTool` targets (recursively) |
| Tools | Only harness tools or `AgentTool`; warning if a prompt mentions a disabled tool |
| Instructions | Not empty; no ADK `{state}` placeholders |
| Adapters | Referenced directories exist with `adapter_config.json` (LORA, Gemma 4 31B base) and a valid safetensors header; warning for unreferenced adapters |
| Skills | `SKILL.md` exists with frontmatter `name` (and `description`), name matches the directory, scripts compile, warning on network imports |
| Hygiene | No `.env` or credential files, no secret patterns, no `__pycache__`, `.git` or `.pyc`, no files over 5 MB except adapter weights |

## Before uploading

1. Run `python -m pytest`.
2. Run `python scripts/build_submission.py --strict`.
3. Put official artifacts in `external/competition/` and run `python scripts/competition_bootstrap.py`. It writes `artifacts/audits/sample_submission_diff.md` (B0 and FULL vs the sample). Fix every INCOMPATIBLE finding. R-TOOLS-2 and R-SKILL-3 stay UNVERIFIED until that file exists.
4. Record the SHA-256 printed by the build alongside the Kaggle submission.
