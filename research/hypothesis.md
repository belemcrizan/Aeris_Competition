# Research hypothesis

## Question

Can uncertainty-gated, graph-guided repository exploration improve the patch success rate and efficiency of a local autonomous software-engineering agent (Gemma 4 31B QAT) under a fixed execution budget?

## Falsifiable claims

Each claim compares variants on the same task set with the same model and sampling, using a paired test (see `metrics.md`).

| ID | Claim | Supported if | Refuted if |
| --- | --- | --- | --- |
| H1 | Semantic retrieval improves localization and PASS rate over the vanilla agent | PASS(B1) > PASS(B0), and LOCALIZATION_FAILURE drops | PASS(B1) ≤ PASS(B0), or the difference is within noise across repeated runs |
| H2 | Bounded graph expansion adds to retrieval | PASS(B2) > PASS(B1), and PASS(FULL) > PASS(ABL_no_graph) | Either is ≤, or graph use raises GRAPH_EXPLOSION or BUDGET_EXHAUSTION without a PASS gain |
| H3 | Explicit competing hypotheses reduce ROOT_CAUSE_FAILURE | PASS(B3) ≥ PASS(B2), and ROOT_CAUSE_FAILURE drops | The ledger overhead lowers PASS rate, or ROOT_CAUSE_FAILURE does not change |
| H4 | Uncertainty gating raises PASS rate at equal or lower cost | PASS(B4) ≥ PASS(B3), with fewer failed patch attempts per task | The gating causes over-exploration (more BUDGET_EXHAUSTION) or lower PASS rate |
| H5 | Structured failure signatures reduce LOOPING and improve retries | PASS(B5) ≥ PASS(B4), LOOPING drops, and success after the first failed test rises | No change in retry success or LOOPING |
| H6 | Model-reported hypothesis confidence carries signal | The top-weight or entropy value at first patch predicts PASS better than chance (AUROC > 0.5 with a CI excluding 0.5) | AUROC CI includes 0.5 |

H6 matters: if the confidence weights carry no signal, gating on them cannot help, and any gain from B4 must come from something else (for example, simply forcing more reading before editing).

## What would change the plan

- If H1 and H2 fail: graph and embedding tools are not worth their context cost for this model. Simplify the navigation to grep-first.
- If H6 fails: replace confidence gating with evidence-count gating (for example "at least one reproduction or direct code evidence before editing") and test that instead.
- If every component is neutral: the bottleneck is patch generation or reasoning, not exploration. That is the evidence that would justify a LoRA (Phase 9).

Negative results will be reported.
