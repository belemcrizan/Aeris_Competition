# Architecture

## Constraints that shape the design

- The submission is declarative. The harness compiles `agent.yaml` into an ADK agent, and our own code can run only as skill scripts inside the task container (R-CFG-1, R-SKILL-2). There is no custom Python orchestrator at evaluation time.
- There is one model (`gemma-4-31b-it-qat-w4a16-ct`) and one global 12-hour budget for roughly 60 tasks per split (R-MODEL-1, R-BUDGET-1, R-DATA-2).
- The grader applies the hidden `test_patch` on top of our patch (R-SCORE-2). Any file left in `/workspace` becomes part of the patch (R-TOOLS-5).

So the "orchestrator" is the root LLM agent following a structured system prompt. State that must survive long contexts and compaction lives in skill-script files under `/tmp/aeris/`.

## Logical roles and where they live

| Role | Realization | Why not a separate subagent (yet) |
| --- | --- | --- |
| Orchestrator | Root `LlmAgent`; core prompt workflow, budget rules, submission protocol | It is the agent |
| Repository navigator | `retrieval` and `graph` prompt modules; `navigation` skill (`locate_symbol.py`, `find_tests.py`) | An `AgentTool` navigator costs an extra model context per call and returns summaries that can hide the lines the patcher needs. It stays a candidate for ablation once the harness syntax is verified (R-TOOLS-3) |
| Root-cause analyzer | `hypotheses` and `uncertainty` modules; `ledger` skill | Hypotheses must stay next to the evidence that produced them |
| Patcher | Core "Fix" step and patch principles | Same context as the analysis; handing it off loses detail |
| Validator / reviewer | `feedback` module with the `testing` skill; `review` module with the `review` skill | Deterministic scripts are cheaper and more reliable than an LLM reviewer for hygiene checks |

The decision rule (would it plausibly raise hidden-test PASS rate, or help measure what does?) currently favours one agent with deterministic helper scripts. Subagents are deferred until B0 measurements show a context bottleneck they would relieve.

## Closed loop

```
issue ─► understand ─► localize (grep │ search_similar_code ─► locate_symbol)
                           │
                           ▼
                 bounded graph expansion (≤3 seeds, ≤2 hops, ≤20 neighbors)
                           │
                           ▼
          hypotheses H1..H3 with weights ─► ledger status ─► gate
                  ▲                                       │
                  │                         HIGH: investigate / MEDIUM: discriminate / LOW: patch
                  │                                       ▼
   belief update ◄── failure signature ◄── run_tests ◄── minimal patch
                                                          │ pass (or retry limit / critical budget)
                                                          ▼
                                             review_diff ─► submit_patch
```

## Components (ablation units)

Defined in `experiments/components.yaml`. Each component contributes tools, prompt modules and skills; a variant enables a set of components. The same module text is used in every variant that enables it, so an ablation is a pure configuration change.

| Component | Tools | Prompt module | Skill |
| --- | --- | --- | --- |
| core (required) | run_command, read_file, edit_file, write_file, submit_patch, get_status | core | none |
| semantic_retrieval | search_similar_code | retrieval | navigation |
| graph_navigation | get_code_neighbors, get_code_subgraph | graph | navigation |
| hypothesis_tracking | none | hypotheses | ledger |
| uncertainty_gating (requires hypothesis_tracking) | none | uncertainty | ledger |
| failure_feedback | none | feedback | testing |
| reviewer | none | review | review |

A shared `skills` module, which explains how to invoke skill scripts, is inserted after `core` whenever any skill ships.

## Issue-conditioned subgraph

The conceptual node score is

R(v) = α·semantic(v) + β·graph(v) + γ·test_proximity(v) + δ·dependency(v) + ε·failure_evidence(v)

What is actually computable today:

- semantic: rank in `search_similar_code` results. The harness does not expose scores to our code, only to the model.
- graph: whether v lies on a caller/callee path between the API named in the issue and a candidate, from `get_code_neighbors` and `get_code_subgraph`.
- test_proximity: `find_tests.py` score (imports and mentions in test files).
- failure_evidence: source frames in `run_tests.py` output.
- dependency: not separately measured.

These signals are combined by the model under explicit limits, not by a numeric formula. We do not claim a computed R(v). Making it numeric would need a skill script reading the graph JSON, and whether the graph files are present in the sandbox is unverified.

## Uncertainty gate

Implemented in `submission/skills/ledger/scripts/ledger.py::assess`.

- Weights are normalized over non-rejected hypotheses. The script reports entropy H = −Σ pᵢ log pᵢ and its value normalized by log n.
- Budget mode from the fraction of budget used: below 0.5 is NORMAL, below 0.8 is CONSERVATIVE, otherwise CRITICAL.
- The level uses the top weight p₁ and requires at least one supporting evidence item for LOW:

| Mode | LOW | HIGH |
| --- | --- | --- |
| NORMAL | p₁ ≥ 0.6 and supported | p₁ < 0.4 |
| CONSERVATIVE / CRITICAL | p₁ ≥ 0.5 and supported | p₁ < 0.3 |

- Overrides, in order: the last patch passed leads to SUBMIT; 3 patch attempts lead to SUBMIT with the best attempt; CRITICAL mode leads to "patch now" or SUBMIT; after 8 investigation steps without a patch, patch the leading hypothesis.
- The gate uses p₁ rather than entropy because, with one to three hypotheses, p₁ is easier for the model to reason about. Entropy is logged so the paper can test whether it is the better gating variable. Weights are model-reported confidences, not calibrated probabilities.

## Failure feedback

`run_tests.py` parses pytest output into counts, failing test ids, exception types, the first comparison, and non-site-packages frames. It hashes (test id, exception type, message with volatile tokens removed) into a 12-character signature. The history in `/tmp/aeris/test_history.json` detects a repeated signature for the same arguments, which tells the model that its last change did not affect the failure.

## Context policy

- Bounded reads (40 to 120 line ranges), no rereads of unchanged ranges, and `grep -n`, `head` and `tail` instead of full dumps.
- Graph limits: 3 seeds, 2 hops, 10 to 20 neighbors, at most 8 nodes per subgraph call, and no repeated calls.
- The ledger keeps one-line evidence items, the last 6 claims and the last 5 experiments in the rendered view.
- Script outputs are capped (5 failures, 25 tail lines, 200-character fields).

## Security

Repository text, issue text and tool output are treated as data. The core prompt forbids environment and credential access, network use, destructive git commands, and writing outside `/workspace` except `/tmp`. Scripts are standard-library only, offline, and read-only for the repository.
