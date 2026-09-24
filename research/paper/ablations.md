# Ablations

Each ablation removes one component from FULL (`experiments/configs/ABL_*.yaml`); removing hypothesis tracking also removes uncertainty gating, which depends on it.

| Ablation | Removed | Tests |
| --- | --- | --- |
| ABL_no_retrieval | semantic_retrieval | H1 |
| ABL_no_graph | graph_navigation | H2 |
| ABL_no_hypotheses | hypothesis_tracking, uncertainty_gating | H3 |
| ABL_no_uncertainty | uncertainty_gating | H4 |
| ABL_no_feedback | failure_feedback | H5 |
| ABL_no_reviewer (= B5) | reviewer | Review value |

[PENDING: PASS rate and McNemar p-value against FULL for each ablation; change in the failure category each component targets.]
