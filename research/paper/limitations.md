# Limitations

- **Small sample**: about 90 dev and 39 held-out tasks from four repositories. Differences of a few tasks are within noise; we report intervals and paired tests rather than point estimates.
- **Different hidden distribution**: the competition's hidden tasks come from private repositories (R-DATA-2); public-task results may not transfer.
- **Self-reported confidence**: hypothesis weights are the model's own numbers and may be uncalibrated; H6 tests this directly.
- **Stochastic agent**: temperature 1.0; [PENDING: number of repetitions] runs per variant.
- **Local scorer**: development numbers come from an approximation of the official grader (docs/SCORER_FIDELITY.md).
- **Harness-specific behaviour**: several harness details (context compaction, skill runtime, `get_status` format) were not documented when the agent was designed, and the design had to hedge around them (docs/OFFICIAL_ARTIFACT_AUDIT.md).
- **Security evaluation**: prompt-injection robustness was tested at skill level; the agent-level test is [PENDING].
