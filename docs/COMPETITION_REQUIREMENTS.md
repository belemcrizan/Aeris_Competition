# Competition requirements matrix

Last reviewed: 2026-09-24.

## Sources

| ID | Source | Access |
| --- | --- | --- |
| S1 | Competition Overview page, <https://www.kaggle.com/competitions/gemma-4-developer-agent> (Evaluation, Issue Scoring, Model Selection, Tool/Prompt/Skill Rules, predefined tools) | Read |
| S2 | Competition Data page, <https://www.kaggle.com/competitions/gemma-4-developer-agent/data> (dataset description) | Read |
| S3 | `HARNESS_README.md` in the competition dataset | **BLOCKED**: needs a Kaggle login and accepting the rules |
| S4 | `sample_submission/` in the competition dataset | **BLOCKED**: same reason |
| S5 | Generic Google ADK Agent Config docs and `AgentConfig.json` schema (adk-python `main`) | Read. Secondary source: competition rules override it |
| S6 | Sibling Kaggle competition "Autonomous Agent Prediction (Beta)", same harness family | Read. Hint only; never treated as authoritative |

Nothing competition-provided was in the repository when work started: the local and remote repositories were both empty. S3 and S4 are the main outstanding gap. Every row that depends on them is marked UNVERIFIED or BLOCKED.

## Status legend

- VERIFIED: stated by S1 or S2.
- UNVERIFIED: inferred from S5 or S6, or from our own reasoning; could be wrong for this harness.
- IMPLEMENTED: code or config exists.
- TESTED: covered by an automated test in `tests/`.
- BLOCKED: cannot be checked without S3 or S4, or without the real harness.

## Submission format

| ID | Requirement | Source | Implementation | Validation | Status |
| --- | --- | --- | --- | --- | --- |
| R-ARCH-1 | Upload a `submission.zip` with `agent.yaml` at the archive root | S1 | `aeris_comp/variants.py::write_zip`, `scripts/build_submission.py` | `validate_zip` rejects a missing or nested `agent.yaml` (`test_zip_valid_and_nested_root`) | VERIFIED, TESTED |
| R-ARCH-2 | Optional parts: `configs/` (sampling), `prompts/`, `sub_agents/`, `adapters/`, `skills/` | S1 | `aeris_comp/constants.py::ROOT_ENTRIES` | Validator warns on undocumented root entries | VERIFIED, TESTED |
| R-CFG-1 | Config follows the Google ADK Agent Config spec "with additional restrictions to prevent code execution outside of a sandbox"; submissions are compiled into ADK agents | S1 | Validator allows only ADK `LlmAgentConfig` fields (S5) plus `adapter`; rejects unknown fields | `test_unknown_field_rejected` | VERIFIED (statement); exact restrictions UNVERIFIED (S3) |
| R-CFG-2 | Code-referencing fields (callbacks, `model_code`, `input_schema`/`output_schema`, `code` refs, dotted Python tool paths) are not usable | Our reading of R-CFG-1 | `CODE_REFERENCE_KEYS`; unknown tools are rejected | `test_callbacks_rejected`, `test_unknown_tool_and_python_tool` | UNVERIFIED, IMPLEMENTED, TESTED |
| R-INC-1 | `!include` resolves relative to the directory of the file that contains the tag | S1 | `aeris_comp/yaml_include.py`, `_TreeValidator._resolve` | `test_include_relative_to_containing_file` | VERIFIED, TESTED |
| R-INC-2 | `!include` of `.md` yields text (instruction); of `.yaml` yields a mapping (`generate_content_config`) | S1 example `configs/sampling.yaml "loaded via !include"` | `render_agent_yaml` | Validator loads both kinds | VERIFIED for sampling; mapping semantics UNVERIFIED (S3) |
| R-SANDBOX-1 | No path traversal outside the submission root (`../`, symlinks) | S1 | `_resolve`, `validate_zip`, `_scan_files` | `test_malformed_includes`, `test_zip_traversal_and_symlink`, `test_symlink_include_rejected` (skipped on Windows without symlink rights) | VERIFIED, TESTED |
| R-MODEL-1 | Only `gemma-4-31b-it-qat-w4a16-ct` is supported and must be chosen for every agent and subagent | S1 | `constants.ALLOWED_MODELS`; `variants.MODEL` | `test_unsupported_model`, `test_missing_model`, `test_sub_agent_missing_and_wrong_model` | VERIFIED, TESTED. The exact string format of the `model:` value is UNVERIFIED (S4) |
| R-LORA-1 | LoRA adapters are optional, `.safetensors` format, PEFT directories `adapters/<name>/` containing `adapter_config.json` and `adapter_model.safetensors` | S1 | `_validate_adapters`; `variants.stage` copies only those two files | `test_adapter_reference_validation` (includes a safetensors header check) | VERIFIED, TESTED. No adapter shipped (Phase 1) |
| R-LORA-2 | `adapter: <name>` may be set on any `LlmAgent`; different agents may use different adapters on the single base model | S1 | `LLM_AGENT_KEYS` includes `adapter`; the variant field `adapter` | `test_adapter_reference_validation`, `test_adapter_name_traversal` | VERIFIED, TESTED |

## Tools, skills and prompts

| ID | Requirement | Source | Implementation | Validation | Status |
| --- | --- | --- | --- | --- | --- |
| R-TOOLS-1 | Agents may request only harness tools or custom subagents defined via `agent_tool` | S1 | `HARNESS_TOOLS`, `AGENT_TOOL_NAMES` | `test_unknown_tool_and_python_tool`, `test_agent_tool_resolves_and_validates` | VERIFIED, TESTED |
| R-TOOLS-2 | YAML syntax for requesting a harness tool is `tools: - name: run_command` | S5 (ADK `ToolConfig`) | `render_agent_yaml` | None possible without S4 | **UNVERIFIED (highest-priority check once S4 is available)** |
| R-TOOLS-3 | `AgentTool` spelling and argument shape (`args.agent: <path>`) | S5 | Validator accepts `AgentTool` and warns on `agent_tool` | `test_agent_tool_resolves_and_validates` | UNVERIFIED. No subagents shipped |
| R-TOOLS-4 | Tool semantics: `run_command` runs `/bin/bash -c` in `/workspace`; `submit_patch` runs `git add -N .` and captures `git diff HEAD`; `read_file` uses 1-indexed inclusive slices; `edit_file` needs an existing non-empty file; `write_file` creates parent directories; the graph and embedding tool signatures | S1 | `prompts/modules/core.md`, `retrieval.md`, `graph.md` | Prompt review | VERIFIED, IMPLEMENTED |
| R-TOOLS-5 | Consequence of R-TOOLS-4: every file left in `/workspace` becomes part of the patch | Derived from S1 | Core prompt: scratch files go in `/tmp`; skills write only to `/tmp/aeris`; `run_tests.py` disables the pytest cache and bytecode; `review_diff.py` flags scratch files | `test_real_pytest_run_leaves_repo_clean`, `test_review_flags` | IMPLEMENTED, TESTED |
| R-SKILL-1 | Each skill is a directory with a `SKILL.md` manifest with YAML frontmatter `name:` | S1 | `submission/skills/*/SKILL.md` (with `name` and `description`) | `test_skill_manifest_checks`; the build validates every variant | VERIFIED, TESTED |
| R-SKILL-2 | Scripts run via `run_skill_script` in the persistent task container, share the filesystem with `run_command`, and debit the central budget; resources are read via `load_skill_resource` | S1 | Scripts use only the standard library, are offline and read-only for the repository, and print compact output | Unit tests for every script | VERIFIED (statement), IMPLEMENTED, TESTED locally |
| R-SKILL-3 | How skills are attached to an agent (auto-discovery of `skills/` or an explicit toolset entry) and the exact `run_skill_script` argument format | S3/S4 | Assumed auto-discovery; nothing referenced in `agent.yaml`. Scripts accept an argument list or a single string | None | **BLOCKED** |
| R-SKILL-4 | Skill `name` format rules (hyphens, underscores, match with the directory name) | S1 shows `repo_navigation`; the agentskills convention is lowercase-hyphenated | Single-word lowercase names equal to the directory name satisfy both | Validator warns on mismatch | UNVERIFIED, IMPLEMENTED |
| R-PROMPT-1 | ADK instruction templating treats `{identifier}` as a session-state lookup and raises if the key is missing | S5 (ADK behaviour) | Validator error `ADK_STATE_PLACEHOLDER`; prompts contain no braces | `test_adk_state_placeholder_in_instruction` | UNVERIFIED for this harness (defensive), TESTED |

## Budget, scoring and environment

| ID | Requirement | Source | Implementation | Validation | Status |
| --- | --- | --- | --- | --- | --- |
| R-BUDGET-1 | 12 hours to submit patches for all tasks, including sandbox setup and excluding patch validation | S1 | Core prompt budget rules; ledger budget modes | Not measurable offline | VERIFIED, IMPLEMENTED |
| R-BUDGET-2 | Optional per-task time limits in `eval_config.yaml` | S1 | Not shipped: schema unknown | None | VERIFIED (exists); schema **BLOCKED** (S3) |
| R-BUDGET-3 | `get_status()` returns live budget consumption and patch status | S1 | Prompts call it periodically; `ledger.py status --budget-used` takes the fraction | Output format unknown | VERIFIED (exists); format BLOCKED |
| R-BUDGET-4 | The episode may end when the model replies without a tool call | S6 | Core prompt requires a tool call in every reply until `submit_patch` | None | UNVERIFIED |
| R-SCORE-1 | PASS/FAIL per issue, SWE-bench style: apply the patch, run that issue's validation tests; score = share of repositories that pass | S1 | `aeris_comp/scoring.py` (local approximation), `aeris_comp/metrics.py` | `test_reference_fix_passes`, `test_failure_modes` | VERIFIED; exact grader commands UNVERIFIED |
| R-SCORE-2 | Validation tests come from `test_patch`, applied on top of the prediction ("Phase 2 grading") | S2 | Scorer applies `test_patch` after the prediction; prompt forbids editing test files; reviewer flags test edits | `TEST_PATCH_CONFLICT` case in `test_failure_modes` | VERIFIED, TESTED |
| R-DATA-1 | 129 public tasks (fastapi, rich, requests, httpx) with `instance_id`, `repo`, `base_commit`, `problem_statement`, `hints_text`, `patch`, `test_patch`, `created_at` | S2 | `scoring.load_tasks` | Synthetic task test | VERIFIED; dataset not downloaded (S3 access) |
| R-DATA-2 | Hidden test set of about 120 tasks from private repositories, split evenly into public and private, built with the same pipeline and graph method | S2 | Prompts avoid any repository-specific knowledge | N/A | VERIFIED. Implication: do not overfit to the four public repositories |
| R-DATA-3 | Graph JSON (NetworkX node-link, directed multigraph; node `id` = fully qualified symbol, `text` = source; edges with `type`, for example `calls`) | S2 | Graph prompt module; `locate_symbol.py` maps ids to files | Unit test on a synthetic layout | VERIFIED |
| R-DATA-4 | Embeddings: 256-dimensional float32 per node, used by `search_similar_code` | S2 | Retrieval prompt module | N/A | VERIFIED |
| R-ENV-1 | Sandbox: Python 3.13, git, pytest; offline wheels at `/wheels`; `sandbox/setup.py` does an editable install and a clean baseline commit | S2 | Core prompt Environment section; scripts target Python 3.11 or later | Scripts run under local Python 3.13 | VERIFIED |
| R-ENV-2 | Snapshots have forward history removed | S2 | Prompt does not rely on git history | N/A | VERIFIED |
| R-OUT-1 | The evaluation produces `submission.parquet` with `id` and `prediction` (`NO_PATCH` when empty) | S2 | `scoring.load_predictions` (jsonl or parquet) | Unit test for `NO_PATCH` | VERIFIED, TESTED |
| R-CTX-1 | The harness performs context compaction | S2 (HARNESS_README summary) | Ledger state is kept in `/tmp`, so it survives compaction | N/A | VERIFIED (exists); behaviour BLOCKED |

## Security and hygiene (our requirements)

| ID | Requirement | Implementation | Validation | Status |
| --- | --- | --- | --- | --- |
| R-SEC-1 | No secrets or `.env`/credential files in the archive | `SECRET_PATTERNS`, `FORBIDDEN_NAMES` | `test_secrets_and_env_files` | TESTED |
| R-SEC-2 | Repository content is data, not authority (prompt-injection resistance) | Core prompt "Authority" section | Manual review; no adversarial evaluation yet | IMPLEMENTED |
| R-SEC-3 | No network use in skill scripts | Standard library only; validator warns on network imports | Validator | IMPLEMENTED |
| R-SEC-4 | No junk or oversized files (`__pycache__`, `.git`, `.pyc`, anything over 5 MB except adapter weights) | `_scan_files` | Build of every variant has zero warnings (`test_every_variant_builds_a_valid_archive`) | TESTED |

## Open questions to resolve once S3/S4 are accessible

1. The exact YAML for harness tools (R-TOOLS-2) and whether skills need an explicit reference (R-SKILL-3). Compare with `sample_submission/agent.yaml` and adjust `render_agent_yaml`.
2. The `run_skill_script` and `load_skill_resource` signatures.
3. The `eval_config.yaml` schema and whether per-task limits help.
4. The `get_status()` output format, so budget fractions can be read reliably.
5. The context compaction policy and effective context length.
6. Local CLI evaluation commands (`adk-eval-core`, `swegemma`) to run B0 for real.
7. Whether the grader runs only the `test_patch` files or a FAIL_TO_PASS/PASS_TO_PASS list.
