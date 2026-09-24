# Threats to validity

Full discussion: research/threats_to_validity.md. Summary for the paper:

- **Internal**: prompt changes between variants are confined to component modules; every variant is built from one commit, and its archive hash is recorded. Tuning happens on dev only; held-out is scored once.
- **Construct**: PASS is measured by hidden tests added in `test_patch`; a patch can pass without fully fixing the issue, or fail on unrelated flaky tests. Localization is measured against the files of the reference patch, which is only one valid fix.
- **External**: four public Python repositories; the hidden set is private repositories built with the same pipeline.
- **Conclusion**: multiple comparisons across 12 variants. We treat H1-H6 as pre-registered and report other comparisons as exploratory.
