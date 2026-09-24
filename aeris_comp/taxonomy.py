"""Failure taxonomy used to label unsuccessful episodes (see research/metrics.md).

Each failed task gets one primary category and optional secondary categories. Labels
come from three sources, in decreasing reliability: the scorer status (mechanical),
telemetry rules (aeris_comp.telemetry.suggest_labels), and manual trace review.
"""

from __future__ import annotations

from collections.abc import Iterable

# category -> (family, definition)
TAXONOMY: dict[str, tuple[str, str]] = {
    "INFRASTRUCTURE_FAILURE": ("infrastructure", "Harness, container, snapshot or environment problem unrelated to the agent."),
    "CONFIG_FAILURE": ("infrastructure", "Submission config rejected or misloaded (agent.yaml, includes, skills)."),
    "MODEL_LOAD_FAILURE": ("infrastructure", "Model or adapter failed to load or serve."),
    "TOOL_SCHEMA_FAILURE": ("tools", "Tool calls rejected for malformed arguments or unknown tool names."),
    "TOOL_MISUSE": ("tools", "Valid tool calls used wrongly (failed edits, wrong paths, misread semantics)."),
    "LOCALIZATION_FAILURE": ("localization", "Never inspected or edited the file/symbol changed by the reference fix."),
    "GRAPH_EXPLOSION": ("localization", "Graph expansion consumed budget without narrowing candidates."),
    "CONTEXT_FAILURE": ("localization", "Relevant information was read but lost (overflow, compaction, truncation)."),
    "ROOT_CAUSE_FAILURE": ("reasoning", "Edited the right area but the change does not address the actual cause."),
    "PREMATURE_PATCH": ("reasoning", "Patched before any evidence discriminated between plausible causes."),
    "PATCH_FAILURE": ("patch", "Right cause, but the edit is wrong (logic, incomplete case coverage)."),
    "SYNTAX_REGRESSION": ("patch", "Patch introduces a syntax or import error."),
    "BEHAVIOR_REGRESSION": ("patch", "Fix works for the issue but breaks previously passing behavior."),
    "OVER_EDITING": ("patch", "Unrelated changes (refactors, test edits, scratch files) caused failure or conflicts."),
    "UNDER_EDITING": ("patch", "Only part of the requested behavior was implemented."),
    "TEST_SELECTION_FAILURE": ("validation", "Validated against tests that do not exercise the changed behavior."),
    "REPEATED_FAILURE": ("control", "Same failure signature reproduced three or more times without a change of approach."),
    "LOOPING": ("control", "Repeated equivalent actions or patches without new evidence."),
    "BUDGET_EXHAUSTION": ("control", "Episode ended by the step/token budget before a validated patch."),
    "TIMEOUT": ("control", "Episode or grading hit a wall-clock limit."),
    "NO_PATCH": ("submission", "Episode ended without submit_patch or with an empty diff."),
    "INVALID_SUBMISSION": ("submission", "Patch submitted but does not apply to the base commit."),
    "UNKNOWN": ("unknown", "Evidence insufficient to assign a category."),
}

FAILURE_CATEGORIES: dict[str, str] = {name: definition for name, (_, definition) in TAXONOMY.items()}
FAMILIES: dict[str, str] = {name: family for name, (family, _) in TAXONOMY.items()}

# Older labels still accepted in stored results.
ALIASES = {"REGRESSION_FAILURE": "BEHAVIOR_REGRESSION"}

# Mechanical outcomes produced by the local scorer (aeris_comp.scoring).
SCORER_STATUSES = ("PASS", "FAIL", "NO_PATCH", "APPLY_FAILED", "TEST_PATCH_CONFLICT", "TIMEOUT", "SETUP_FAILED", "MISSING_SNAPSHOT")

# Scorer statuses that determine the primary category without trace inspection.
AUTOMATIC_CATEGORY = {
    "NO_PATCH": "NO_PATCH",
    "APPLY_FAILED": "INVALID_SUBMISSION",
    "TEST_PATCH_CONFLICT": "OVER_EDITING",
    "TIMEOUT": "TIMEOUT",
    "SETUP_FAILED": "INFRASTRUCTURE_FAILURE",
    "MISSING_SNAPSHOT": "INFRASTRUCTURE_FAILURE",
}


def canonical(category: str) -> str:
    return ALIASES.get(category, category)


def validate_category(category: str | None) -> None:
    if category is not None and canonical(category) not in FAILURE_CATEGORIES:
        raise ValueError(f"unknown failure category {category!r}; expected one of {sorted(FAILURE_CATEGORIES)}")


def validate_labels(primary: str | None, secondary: Iterable[str] = ()) -> None:
    secondary = list(secondary)
    validate_category(primary)
    for label in secondary:
        validate_category(label)
    if secondary and primary is None:
        raise ValueError("secondary failure labels require a primary label")
    if primary is not None and canonical(primary) in {canonical(s) for s in secondary}:
        raise ValueError(f"{primary!r} is both primary and secondary")
