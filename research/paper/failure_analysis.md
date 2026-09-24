# Failure analysis

Every failed task gets one primary label and optional secondary labels from the 23-category taxonomy in `aeris_comp/taxonomy.py`, grouped into families: infrastructure, tools, localization, reasoning, patch, validation, control, submission and unknown. Labels come from, in order of reliability: the scorer status (for example `NO_PATCH` or `APPLY_FAILED`), rule-based suggestions from telemetry (`suggest_labels`), and manual trace review. A second person relabels a random 20% sample to check agreement.

[PENDING: `research/paper/tables/failure_categories.md` per variant; the three most frequent categories for B0 and the final variant, each with one representative trace excerpt; which categories each component reduced.]
