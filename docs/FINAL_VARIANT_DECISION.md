# Final variant decision

**Status: BLOCKED (gap L-03). No variant has been measured.**

`dist/submission.zip` is built from FULL because FULL is the default variant in `aeris_comp/variants.py`. That default is a starting point, not a decision: there is no evidence that FULL beats B0.

## Decision rule (written before any data)

Measured on the dev split only, with the same model, sampling and budget for every variant:

1. Candidates are the variants whose PASS rate on dev is within the Wilson 95% interval of the best variant.
2. Among candidates, prefer the one with fewer components (simplest wins ties), because each component costs context and budget, and the hidden set is from different repositories (R-DATA-2).
3. A component stays only if removing it (its ablation) lowers dev PASS, or it significantly reduces a failure category it targets (exact McNemar p < 0.1 on the tasks where that category occurs).
4. If H6 is refuted (confidence carries no signal), use evidence-count gating in the final variant ([BUDGET_POLICY.md](BUDGET_POLICY.md)).
5. Freeze: record the variant id, the git commit and the `content_sha256` from `dist/release_manifest.json` here, then run held-out exactly once (X-10). Held-out results do not change the choice.

## LoRA

Not planned. A LoRA is considered only if failure analysis on dev shows that most failures are PATCH_FAILURE or TOOL_SCHEMA_FAILURE with correct localization. Those are problems in what the model generates, which prompts and tools did not fix. It would then be trained only on data that excludes the held-out tasks.

## Decision record

| Date | Variant | Commit | content_sha256 | Dev PASS | Rationale |
| --- | --- | --- | --- | --- | --- |
| [PENDING] | | | | | |
