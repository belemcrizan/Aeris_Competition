# Official artifact audit

Date: 2026-09-24. Branch: `phase2-gap-closure`.

## Result

No official competition artifact is available to this project. `artifacts/audits/sample_submission_diff.md` is not written, because there is no sample to diff against. Every requirement that depends on these artifacts stays BLOCKED or UNVERIFIED in [COMPETITION_REQUIREMENTS.md](COMPETITION_REQUIREMENTS.md) and [GAP_CLOSURE.md](GAP_CLOSURE.md).

The closest authority we could run is Google ADK itself (level 6). Its results are recorded below and in `artifacts/audits/adk_conformance.json`.

## Where we looked

| Artifact (authority level) | Location searched | Found |
| --- | --- | --- |
| `HARNESS_README.md` (1) | Repository working tree and full git history; GitHub remote `belemcrizan/Aeris_Competition`; public web search | No |
| `sample_submission/` (2) | Same | No |
| Harness packages `adk-eval-core`, `swegemma` (3) | PyPI package lookups | No: not published |
| Competition dataset (5): tasks, snapshots, graphs, embeddings | Kaggle, which needs a login and rules acceptance | No: no Kaggle credentials or CLI configured here |
| Kaggle Overview and Data pages (4) | Public web pages | Yes: already sources S1 and S2 |
| Google ADK (6) | PyPI `google-adk==2.9.2`, installed in an isolated `.venv-adk` | Yes |

Nothing competition-provided was modified: there was nothing to modify.

## Evidence obtained from ADK 2.9.2 (authority level 6)

ADK ranks below the harness README and the sample submission. Each finding below is "what ADK does"; the harness may add restrictions or extensions.

| Finding | ADK source | Effect on this project |
| --- | --- | --- |
| `config_agent_utils` validates every agent YAML with the class's `config_type` (`LlmAgentConfig`, `extra="forbid"`) before building it | `agents/config_agent_utils.py` | `aeris_comp/adk_conformance.py` runs that same model on our resolved `agent.yaml`. All 12 variants PASS. `adapter` is removed first and reported as a competition extension |
| Stock ADK has no `!include`; `from_config` uses `yaml.safe_load` | `agents/config_agent_utils.py::from_config` | `!include` is a harness feature (S1). We resolve it relative to the containing file before ADK validation |
| An undotted tool `name: X` resolves as `google.adk.tools.X`; harness tools such as `run_command` do not exist there | `_resolve_tools` | The harness must map tool names itself; our syntax (R-TOOLS-2) is schema-valid but its resolution is harness-specific. Reported as `harness_provided_tools` |
| `AgentTool` is a tool class; `agent_tool` is a module, which stock ADK rejects as a tool | `google.adk.tools` | The validator keeps `AGENT_TOOL_SPELLING` as an UNVERIFIED warning. We ship no subagents |
| `LlmAgentConfig` has no `skills` field, and `SkillToolset` cannot be resolved by name | `llm_agent_config.py`, `google.adk.tools` | YAML cannot attach skills in stock ADK, so the harness must discover `skills/` itself. R-SKILL-3 narrows to "auto-discovery"; still BLOCKED on the README |
| `SKILL.md` frontmatter: `name` in kebab-case (snake_case behind the `SNAKE_CASE_SKILL_NAME` feature flag), at most 64 characters, equal to the directory name; `description` required, at most 1024 characters; allowed keys are `name`, `description`, `license`, `compatibility`, `allowed-tools`, `metadata` | `skills/models.py`, `skills/_utils.py::_validate_skill_dir` | Validator errors now match ADK's own validator (cross-checked in `tests/test_validator_levels.py`). Our four skills pass ADK's loader |
| `run_skill_script(skill_name, file_path, args, short_options, positional_args)`. A dict `args` becomes `--k v`, placed **before** `--` and the positionals. A list `args` is the full argv. In environment mode the tool takes one `command` string | `tools/skill_toolset.py::RunSkillScriptTool`, `_SkillScriptCodeExecutor._build_wrapper_code` | All scripts accept every form. The prompt tells the model to pass a list. `tests/test_skill_runtime_contract.py` runs our scripts inside ADK's generated wrapper |
| Code-executor mode copies the skill into a temp directory and `chdir`s there before running | `_SkillScriptCodeExecutor` | Scripts default to `/workspace` (or `--repo`) instead of the current directory. Tested |
| Environment mode copies skill files into `skills_folder`, which defaults to `<working dir>/skills` | `RunSkillScriptTool._ensure_skill_materialized_in_env` | If the harness working directory is `/workspace`, skill files would land in the patch. The review skill flags `MATERIALIZED_SKILL_FILE` and the prompt says to delete them. Whether the harness does this is UNVERIFIED |
| Only `.py`, `.sh` and `.bash` scripts can be run | `_build_wrapper_code` | New validator warning `SKILL_UNSUPPORTED_SCRIPT` |
| `load_skill_resource(skill_name, file_path)` reads `references/`, `assets/` and `scripts/` | `LoadSkillResourceTool` | The competition page (S1) names a `resources/` folder instead; we ship neither. Open question for the README |

## How to redo this audit when access is granted

1. Accept the competition rules on Kaggle, then download the dataset into `data/` (gitignored).
2. Diff `sample_submission/agent.yaml` against `submission/agent.yaml` and write `artifacts/audits/sample_submission_diff.md`.
3. Re-check every row of [COMPETITION_REQUIREMENTS.md](COMPETITION_REQUIREMENTS.md) marked UNVERIFIED or BLOCKED against `HARNESS_README.md`; update `docs/gaps.yaml` and run `python scripts/generate_docs.py`.
4. If the README gives a validator or schema, add it as an `official_harness` test and make it the first check in `validate_submission.py`.
