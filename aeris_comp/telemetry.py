"""Telemetry event schema, validation and rule-based failure-label suggestions.

Every event is one JSON object per line with exactly the fields in
:data:`FIELDS`. Skills write events to ``$AERIS_STATE_DIR/events.jsonl`` inside the
sandbox; the local scorer writes ``grade_result``. Events that only the harness can
observe (``task_start``, harness ``tool_call`` ...) need harness traces, which are not
available yet (docs/TELEMETRY.md lists the source of every event type).
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

EVENT_TYPES = (
    "task_start",
    "task_end",
    "tool_call",
    "tool_result",
    "semantic_search",
    "graph_expansion",
    "file_read",
    "edit",
    "hypothesis_created",
    "hypothesis_updated",
    "uncertainty_state",
    "patch_attempt",
    "test_start",
    "test_result",
    "failure_signature",
    "retry",
    "review",
    "budget_status",
    "submit_patch",
    "grade_result",
)

FIELDS = ("timestamp", "task_id", "variant", "event_type", "duration", "tool", "success", "metadata")

# Who can emit each event type today.
EVENT_SOURCES = {
    "task_start": "HARNESS_TRACE",
    "task_end": "HARNESS_TRACE",
    "tool_call": "HARNESS_TRACE",
    "tool_result": "HARNESS_TRACE+SKILL",
    "semantic_search": "HARNESS_TRACE",
    "graph_expansion": "HARNESS_TRACE",
    "file_read": "HARNESS_TRACE",
    "edit": "HARNESS_TRACE",
    "hypothesis_created": "SKILL:ledger",
    "hypothesis_updated": "SKILL:ledger",
    "uncertainty_state": "SKILL:ledger",
    "patch_attempt": "SKILL:ledger",
    "test_start": "SKILL:testing",
    "test_result": "SKILL:testing",
    "failure_signature": "SKILL:testing",
    "retry": "SKILL:testing",
    "review": "SKILL:review",
    "budget_status": "SKILL:ledger",
    "submit_patch": "HARNESS_TRACE",
    "grade_result": "SCORER",
}


class TelemetryError(ValueError):
    pass


def make_event(
    event_type: str,
    *,
    task_id: str | None = None,
    variant: str | None = None,
    duration: float | None = None,
    tool: str | None = None,
    success: bool | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: float | None = None,
) -> dict[str, Any]:
    event = {
        "timestamp": round(time.time() if timestamp is None else timestamp, 3),
        "task_id": task_id,
        "variant": variant,
        "event_type": event_type,
        "duration": duration,
        "tool": tool,
        "success": success,
        "metadata": metadata or {},
    }
    validate_event(event)
    return event


def validate_event(event: Any) -> None:
    if not isinstance(event, dict):
        raise TelemetryError("event must be a JSON object")
    if tuple(sorted(event)) != tuple(sorted(FIELDS)):
        raise TelemetryError(f"event fields {sorted(event)} != {sorted(FIELDS)}")
    if event["event_type"] not in EVENT_TYPES:
        raise TelemetryError(f"unknown event_type {event['event_type']!r}")
    if not isinstance(event["timestamp"], (int, float)) or isinstance(event["timestamp"], bool):
        raise TelemetryError("timestamp must be a number (unix seconds)")
    if event["duration"] is not None and (not isinstance(event["duration"], (int, float)) or event["duration"] < 0):
        raise TelemetryError("duration must be null or a non-negative number")
    for key in ("task_id", "variant", "tool"):
        if event[key] is not None and not isinstance(event[key], str):
            raise TelemetryError(f"{key} must be null or a string")
    if event["success"] is not None and not isinstance(event["success"], bool):
        raise TelemetryError("success must be null or a boolean")
    if not isinstance(event["metadata"], dict):
        raise TelemetryError("metadata must be an object")


def read_events(path: Path, *, task_id: str | None = None, variant: str | None = None) -> list[dict[str, Any]]:
    """Read and validate a JSONL file; fill task_id/variant when the sandbox left them null."""
    events = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            validate_event(event)
        except (json.JSONDecodeError, TelemetryError) as exc:
            raise TelemetryError(f"{path}:{lineno}: {exc}") from exc
        if event["task_id"] is None:
            event["task_id"] = task_id
        if event["variant"] is None:
            event["variant"] = variant
        events.append(event)
    return events


def write_events(events: Iterable[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            validate_event(event)
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def event_counts(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(e["event_type"] for e in events).items()))


# Thresholds for rule-based labels; tuned only on the dev split (research/methodology.md).
REPEATED_SIGNATURE_MIN = 3
GRAPH_EXPANSION_MAX = 15
BUDGET_EXHAUSTED_AT = 0.95


def suggest_labels(events: list[dict[str, Any]], scorer_status: str | None = None) -> list[str]:
    """Suggest failure labels from telemetry; a human confirms them during trace review."""
    labels: list[str] = []
    types = [e["event_type"] for e in events]
    signatures = Counter(
        e["metadata"].get("signature") for e in events if e["event_type"] == "failure_signature" and e["metadata"].get("signature")
    )
    if signatures and max(signatures.values()) >= REPEATED_SIGNATURE_MIN:
        labels.append("REPEATED_FAILURE")
    first_patch = types.index("patch_attempt") if "patch_attempt" in types else None
    if first_patch is not None:
        before = types[:first_patch]
        if "test_result" not in before and "hypothesis_updated" not in before:
            labels.append("PREMATURE_PATCH")
    if types.count("graph_expansion") > GRAPH_EXPANSION_MAX:
        labels.append("GRAPH_EXPLOSION")
    if any(e["event_type"] == "tool_result" and e["metadata"].get("error_code") == "INVALID_ARGUMENTS" for e in events):
        labels.append("TOOL_SCHEMA_FAILURE")
    if "submit_patch" not in types and scorer_status in {None, "NO_PATCH"} and "task_end" in types:
        labels.append("NO_PATCH")
    budget = [e for e in events if e["event_type"] == "budget_status"]
    used = budget[-1]["metadata"].get("budget_used") if budget else None
    if isinstance(used, (int, float)) and used >= BUDGET_EXHAUSTED_AT and scorer_status != "PASS":
        labels.append("BUDGET_EXHAUSTION")
    return labels
