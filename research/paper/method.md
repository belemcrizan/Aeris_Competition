# Method

Drafted from the implementation at `submission/`, `experiments/` and `aeris_comp/`.

## Agent

A single ADK `LlmAgent` using `gemma-4-31b-it-qat-w4a16-ct`, with temperature 1.0, top-p 0.95 and top-k 64 (`submission/configs/sampling.yaml`). The system prompt is assembled from switchable modules (`submission/prompts/modules/`); each experimental component contributes its prompt modules, tools and skills (`experiments/components.yaml`). There is no custom Python in the agent: extra behaviour lives in four standard-library skills that the agent runs through `run_skill_script`.

## Components

| Component | Tools | Skill | Behaviour |
| --- | --- | --- | --- |
| core (always on) | run_command, read_file, edit_file, write_file, submit_patch, get_status | - | Authority rules, a 7-step workflow, no test edits, scratch files in /tmp |
| semantic_retrieval | search_similar_code | navigation | Embedding search to shortlist candidate files |
| graph_navigation | get_code_neighbors, get_code_subgraph | navigation | Bounded expansion around candidates; `locate_symbol` maps graph node ids to files |
| hypothesis_tracking | - | ledger | Competing root-cause hypotheses with weights, evidence for and against |
| uncertainty_gating | - | ledger | Entropy and top weight give an uncertainty level; together with the budget mode it gives the next action (investigate, discriminate, confirm, patch, submit) |
| failure_feedback | - | testing | Compact pytest reports with a failure signature that ignores volatile tokens; repeated signatures flagged |
| reviewer | - | review | Pre-submission diff review (scratch files, test edits, debug statements, whitespace-only edits, oversized diffs) |

## Uncertainty and budget

Normalized weights \(p_i\) of active hypotheses give entropy \(H = -\sum_i p_i \log p_i\), normalized by \(\log n\). Uncertainty is LOW when the top weight reaches a mode-dependent bar and has supporting evidence, HIGH below a lower bar, MEDIUM otherwise. Budget modes (NORMAL, CONSERVATIVE, CRITICAL) come from the used budget fraction. Hard limits: 3 patch attempts, 8 investigation steps before patching. Details and thresholds: docs/BUDGET_POLICY.md. All thresholds are provisional until tuned on the dev split.

[PENDING: if H6 is refuted, describe the evidence-count gating that replaces weight gating.]
