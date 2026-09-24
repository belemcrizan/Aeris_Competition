# Paper readiness

Paper deadline: **2026-11-12** (49 days after 2026-09-24). Final submission: 2026-12-02.

## Claim audit

Every claim the paper could make, with the evidence it has today. A claim may appear in the paper only as SUPPORTED or REFUTED, backed by generated tables; otherwise it goes under limitations or future work.

| Claim | Source | Evidence needed | Status |
| --- | --- | --- | --- |
| H1: semantic retrieval improves localization and PASS rate | research/hypothesis.md | B0 vs B1 on dev, paired test; LOCALIZATION_FAILURE counts | UNSUPPORTED (no runs) |
| H2: graph expansion adds to retrieval | same | B1 vs B2, FULL vs ABL_no_graph | UNSUPPORTED |
| H3: competing hypotheses reduce ROOT_CAUSE_FAILURE | same | B2 vs B3; failure labels | UNSUPPORTED |
| H4: uncertainty gating raises PASS at equal or lower cost | same | B3 vs B4; patch attempts per task | UNSUPPORTED |
| H5: failure signatures reduce LOOPING | same | B4 vs B5; LOOPING and retry success | UNSUPPORTED |
| H6: model confidence carries signal | same | AUROC with a CI excluding 0.5 (`calibration_report`) | UNSUPPORTED |
| The submission is valid for the competition | docs/COMPETITION_REQUIREMENTS.md | Accepted by the Kaggle platform | UNSUPPORTED: ADK accepts it (level 6); platform acceptance is BLOCKED (L-04) |
| The local scorer approximates the official grader | docs/SCORER_FIDELITY.md | `fidelity` agreement of at least 95% | UNSUPPORTED (X-05) |
| The skills are robust to hostile repository content | docs/SECURITY_EVALUATION.md | Skill-level tests | SUPPORTED at skill level only; agent level BLOCKED (E-11) |
| Any efficiency claim (time, tool calls) | none yet | Telemetry from harness runs | UNSUPPORTED |

No numbers exist yet. The paper skeleton in `research/paper/` marks every result slot `[PENDING: ...]`.

## Sections

| Section | File | State |
| --- | --- | --- |
| Abstract | research/paper/abstract.md | Placeholder; written last |
| Introduction | research/paper/introduction.md | Draft of motivation and question; contributions conditional on results |
| Related work | research/paper/related_work.md | Outline only; no citations until each is checked against its source |
| Method | research/paper/method.md | Drafted from the implementation |
| Experimental setup | research/paper/experimental_setup.md | Drafted; numbers pending |
| Results | research/paper/results.md | Placeholder; tables come from `scripts/make_tables.py` |
| Ablations | research/paper/ablations.md | Design drafted; results pending |
| Failure analysis | research/paper/failure_analysis.md | Taxonomy drafted; counts pending |
| Limitations | research/paper/limitations.md | Drafted |
| Threats to validity | research/paper/threats_to_validity.md | Drafted |
| Conclusion | research/paper/conclusion.md | Placeholder |

## Critical path

1. Kaggle access, then the dataset and HARNESS_README (C-01). Everything below depends on it.
2. B0 on one task (X-01), then FIRST_PASS (X-02), then a smoke benchmark (X-03).
3. Freeze the data split (X-04). Check scorer fidelity (X-05).
4. Ladder B0 to FULL plus ablations on dev (X-06, X-07): with 129 tasks, 70% dev is about 90 tasks per variant, times 12 variants.
5. Decide the final variant (L-03); run held-out once (X-10).
6. Generate tables, fill results, failure analysis, abstract.

If step 1 has not happened by 2026-10-15, there is not enough time for the full ladder before the deadline. The fallback is B0, B3 and FULL on dev plus the held-out run, with the other hypotheses reported as untested.
