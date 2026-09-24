"""Aggregate per-task run records into experiment metrics.

PASS rate is the primary metric; everything else is secondary and reported only for the
records that contain the field.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter

from .taxonomy import validate_category

NUMERIC_FIELDS = (
    "wall_time_s",
    "tool_calls",
    "commands",
    "files_inspected",
    "files_changed_count",
    "lines_added",
    "lines_removed",
    "changed_loc",
    "retries",
    "scoring_seconds",
)


def _numeric(record: dict, key: str):
    if key == "files_changed_count" and isinstance(record.get("files_changed"), list):
        return len(record["files_changed"])
    if key == "changed_loc" and "lines_added" in record and "lines_removed" in record:
        return record["lines_added"] + record["lines_removed"]
    value = record.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def summarize(records: list[dict]) -> dict:
    n = len(records)
    statuses = Counter(r["status"] for r in records)
    categories = Counter()
    for r in records:
        category = r.get("failure_category")
        validate_category(category)
        if r["status"] != "PASS":
            categories[category or "UNLABELED"] += 1
    passed = statuses.get("PASS", 0)
    summary = {
        "n_tasks": n,
        "n_pass": passed,
        "pass_rate": passed / n if n else None,
        "pass_rate_ci95": wilson_interval(passed, n) if n else None,
        "status_counts": dict(sorted(statuses.items())),
        "failure_categories": dict(sorted(categories.items())),
        "secondary": {},
    }
    for key in NUMERIC_FIELDS:
        values = [v for r in records if (v := _numeric(r, key)) is not None]
        if values:
            summary["secondary"][key] = {
                "n": len(values),
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
            }
    return summary


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def paired_comparison(a: list[dict], b: list[dict]) -> dict:
    """Compare two runs on their shared tasks with an exact two-sided McNemar test."""
    a_pass = {r["instance_id"]: r["status"] == "PASS" for r in a}
    b_pass = {r["instance_id"]: r["status"] == "PASS" for r in b}
    shared = sorted(set(a_pass) & set(b_pass))
    both = sum(a_pass[t] and b_pass[t] for t in shared)
    only_a = [t for t in shared if a_pass[t] and not b_pass[t]]
    only_b = [t for t in shared if b_pass[t] and not a_pass[t]]
    discordant = len(only_a) + len(only_b)
    k = min(len(only_a), len(only_b))
    p_value = min(1.0, 2 * sum(math.comb(discordant, i) for i in range(k + 1)) / 2**discordant) if discordant else 1.0
    return {
        "n_shared": len(shared),
        "both_pass": both,
        "only_a_pass": only_a,
        "only_b_pass": only_b,
        "neither_pass": len(shared) - both - discordant,
        "pass_rate_a": sum(a_pass[t] for t in shared) / len(shared) if shared else None,
        "pass_rate_b": sum(b_pass[t] for t in shared) / len(shared) if shared else None,
        "mcnemar_exact_p": p_value,
    }
