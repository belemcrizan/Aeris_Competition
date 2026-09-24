# Ablations

There are two complementary designs, both defined as frozen variant files in `experiments/configs/`.

1. Additive ladder: B0 → B1 → B2 → B3 → B4 → B5 → FULL. This answers "does adding X help, given everything before it?". It is order-dependent.
2. Leave-one-out from FULL: ABL_no_retrieval, ABL_no_graph, ABL_no_hypotheses, ABL_no_uncertainty, ABL_no_feedback, and B5 (no reviewer). This answers "does FULL depend on X?".

A component is credited only if both designs point the same way. If they disagree (for example, X helps in the ladder but removing it from FULL changes nothing), we report an interaction or redundancy rather than a gain.

Properties that keep the ablations clean (enforced by `tests/test_build.py`):
- Every variant builds a valid archive with zero warnings.
- The ladder is strictly monotone in components.
- Each ablation removes exactly its component (plus the declared dependants).
- Prompt modules mention only tools owned by their own component (or core), so disabling a component never leaves instructions pointing at missing tools.

Results: not yet measured.
