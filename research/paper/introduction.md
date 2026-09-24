# Introduction

Autonomous repair agents are usually evaluated with large hosted models and generous budgets. The Gemma 4 Developer Agent competition fixes both the model (Gemma 4 31B, 4-bit quantized) and a shared 12-hour budget for all tasks, and it adds tools that expose a code graph and code embeddings. The question then shifts from "how capable is the model" to "how should a mid-sized local model spend a fixed budget exploring a repository before it edits".

We study one answer: explore with retrieval and a bounded graph, keep explicit competing root-cause hypotheses, and gate the decision to patch on uncertainty and remaining budget. We test each part separately with a ladder of variants (B0 to FULL) and single-component ablations, using paired comparisons on the same tasks.

Research question: can uncertainty-gated, graph-guided repository exploration improve the patch success rate and efficiency of a local autonomous software-engineering agent under a fixed execution budget?

Contributions (each conditional on the results; see docs/PAPER_READINESS.md):

1. A configuration-only agent (no custom code in the agent itself) whose components can be switched independently, with deterministic builds for every variant.
2. [PENDING] A paired evaluation of retrieval, graph expansion, hypothesis tracking, uncertainty gating, failure signatures and review.
3. [PENDING] A measurement of whether the model's own hypothesis confidence predicts success (H6), and what to gate on if it does not.
4. [PENDING] A failure taxonomy with counts for each variant.
