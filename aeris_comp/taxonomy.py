"""Failure taxonomy used to label unsuccessful episodes (see research/metrics.md)."""

from __future__ import annotations

FAILURE_CATEGORIES: dict[str, str] = {
    "LOCALIZATION_FAILURE": "Never inspected or edited the file/symbol changed by the reference fix.",
    "ROOT_CAUSE_FAILURE": "Edited the right area but the change does not address the actual cause.",
    "CONTEXT_FAILURE": "Relevant information was read but lost (context overflow, compaction, truncation).",
    "PATCH_FAILURE": "Right cause, but the edit is wrong (syntax, logic, incomplete case coverage).",
    "TEST_SELECTION_FAILURE": "Validated against tests that do not exercise the changed behavior.",
    "REGRESSION_FAILURE": "Fix works for the issue but breaks previously passing tests.",
    "TOOL_MISUSE": "Tool calls with invalid arguments, failed edits, or misuse of harness semantics.",
    "GRAPH_EXPLOSION": "Graph expansion consumed budget without narrowing candidates.",
    "BUDGET_EXHAUSTION": "Episode ended by time or budget before a validated patch was submitted.",
    "LOOPING": "Repeated equivalent actions or patches without new evidence.",
    "OVER_EDITING": "Unrelated changes (refactors, test edits, scratch files) caused failure or conflicts.",
    "UNDER_EDITING": "Only part of the requested behavior was implemented.",
    "INVALID_SUBMISSION": "No patch, empty patch, or patch that does not apply.",
}

# Mechanical outcomes produced by the local scorer (aeris_comp.scoring).
SCORER_STATUSES = ("PASS", "FAIL", "NO_PATCH", "APPLY_FAILED", "TEST_PATCH_CONFLICT", "TIMEOUT", "SETUP_FAILED", "MISSING_SNAPSHOT")

# Scorer statuses that determine the failure category without trace inspection.
AUTOMATIC_CATEGORY = {
    "NO_PATCH": "INVALID_SUBMISSION",
    "APPLY_FAILED": "INVALID_SUBMISSION",
    "TEST_PATCH_CONFLICT": "OVER_EDITING",
}


def validate_category(category: str | None) -> None:
    if category is not None and category not in FAILURE_CATEGORIES:
        raise ValueError(f"unknown failure category {category!r}; expected one of {sorted(FAILURE_CATEGORIES)}")
