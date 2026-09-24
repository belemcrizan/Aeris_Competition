"""Aggregate per-task run records into experiment metrics.

PASS rate is the primary metric; everything else is secondary and reported only for the
records that contain the field.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter

from .taxonomy import FAMILIES, canonical, validate_labels

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
    categories: Counter[str] = Counter()
    secondary_labels: Counter[str] = Counter()
    families: Counter[str] = Counter()
    for r in records:
        category = r.get("failure_category")
        extra = r.get("failure_secondary") or []
        validate_labels(category, extra)
        if r["status"] != "PASS":
            primary = canonical(category) if category else "UNLABELED"
            categories[primary] += 1
            families[FAMILIES.get(primary, "unlabeled")] += 1
            secondary_labels.update(canonical(s) for s in extra)
    passed = statuses.get("PASS", 0)
    summary = {
        "n_tasks": n,
        "n_pass": passed,
        "pass_rate": passed / n if n else None,
        "pass_rate_ci95": wilson_interval(passed, n) if n else None,
        "status_counts": dict(sorted(statuses.items())),
        "failure_categories": dict(sorted(categories.items())),
        "failure_secondary": dict(sorted(secondary_labels.items())),
        "failure_families": dict(sorted(families.items())),
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


def scorer_agreement(ours: list[dict], official: list[dict]) -> dict:
    """PASS/not-PASS agreement between our local scorer and official grades."""
    a = {r["instance_id"]: r["status"] == "PASS" for r in ours}
    b = {r["instance_id"]: r["status"] == "PASS" for r in official}
    shared = sorted(set(a) & set(b))
    false_pass = [t for t in shared if a[t] and not b[t]]
    false_fail = [t for t in shared if b[t] and not a[t]]
    agree = len(shared) - len(false_pass) - len(false_fail)
    return {
        "n_shared": len(shared),
        "only_ours": sorted(set(a) - set(b)),
        "only_official": sorted(set(b) - set(a)),
        "agreement": agree / len(shared) if shared else None,
        "agreement_ci95": wilson_interval(agree, len(shared)) if shared else None,
        "we_pass_official_fails": false_pass,
        "we_fail_official_passes": false_fail,
        "pass_rate_ours": sum(a[t] for t in shared) / len(shared) if shared else None,
        "pass_rate_official": sum(b[t] for t in shared) / len(shared) if shared else None,
    }


# ------------------------------------------------------------- localization
def localization_metrics(tasks: list[dict], ks: tuple[int, ...] = (1, 3, 5, 10)) -> dict:
    """Recall@k, Hit@k and MRR of ranked candidate files against gold files.

    Each task is ``{"ranked": [path, ...], "gold": [path, ...]}``; ``ranked`` is the
    order in which the agent first inspected files, ``gold`` the files changed by the
    reference patch. Tasks without gold files are skipped.
    """
    scored = [t for t in tasks if t.get("gold")]
    out: dict = {"n_tasks": len(scored)}
    if not scored:
        return out
    reciprocal = []
    for task in scored:
        ranked = list(dict.fromkeys(task.get("ranked") or []))
        gold = set(task["gold"])
        rank = next((i for i, path in enumerate(ranked, 1) if path in gold), None)
        reciprocal.append(1 / rank if rank else 0.0)
    out["mrr"] = statistics.fmean(reciprocal)
    for k in ks:
        recalls, hits = [], []
        for task in scored:
            top = set(list(dict.fromkeys(task.get("ranked") or []))[:k])
            gold = set(task["gold"])
            recalls.append(len(top & gold) / len(gold))
            hits.append(1.0 if top & gold else 0.0)
        out[f"recall@{k}"] = statistics.fmean(recalls)
        out[f"hit@{k}"] = statistics.fmean(hits)
    return out


# -------------------------------------------------------------- calibration
def _check_pairs(confidences: list[float], outcomes: list[int]) -> None:
    if len(confidences) != len(outcomes):
        raise ValueError("confidences and outcomes differ in length")
    if any(not 0.0 <= c <= 1.0 for c in confidences):
        raise ValueError("confidences must be in [0, 1]")
    if any(o not in (0, 1) for o in outcomes):
        raise ValueError("outcomes must be 0 or 1")


def brier_score(confidences: list[float], outcomes: list[int]) -> float | None:
    _check_pairs(confidences, outcomes)
    if not confidences:
        return None
    return statistics.fmean((c - o) ** 2 for c, o in zip(confidences, outcomes, strict=True))


def reliability_bins(confidences: list[float], outcomes: list[int], n_bins: int = 10) -> list[dict]:
    _check_pairs(confidences, outcomes)
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for c, o in zip(confidences, outcomes, strict=True):
        bins[min(int(c * n_bins), n_bins - 1)].append((c, o))
    return [
        {
            "lower": i / n_bins,
            "upper": (i + 1) / n_bins,
            "n": len(b),
            "mean_confidence": statistics.fmean(c for c, _ in b) if b else None,
            "accuracy": statistics.fmean(o for _, o in b) if b else None,
        }
        for i, b in enumerate(bins)
    ]


def expected_calibration_error(confidences: list[float], outcomes: list[int], n_bins: int = 10) -> float | None:
    if not confidences:
        return None
    n = len(confidences)
    return sum(
        b["n"] / n * abs(b["accuracy"] - b["mean_confidence"])
        for b in reliability_bins(confidences, outcomes, n_bins)
        if b["n"]
    )


def auroc(confidences: list[float], outcomes: list[int]) -> float | None:
    """Mann-Whitney AUROC with average ranks for ties; None if one class is absent."""
    _check_pairs(confidences, outcomes)
    n_pos = sum(outcomes)
    n_neg = len(outcomes) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(len(confidences)), key=lambda i: confidences[i])
    ranks = [0.0] * len(confidences)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and confidences[order[j + 1]] == confidences[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    rank_sum = sum(r for r, o in zip(ranks, outcomes, strict=True) if o)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def calibration_report(confidences: list[float], outcomes: list[int], n_bins: int = 10) -> dict:
    """Calibration summary plus a decision on whether confidence carries signal.

    ``confidence_has_signal`` is True only when the AUROC 95% interval (Hanley-McNeil
    standard error) excludes 0.5. When it is False the agent should gate on evidence
    counts, not on its stated confidence (docs/BUDGET_POLICY.md).
    """
    n_pos = sum(outcomes)
    n_neg = len(outcomes) - n_pos
    area = auroc(confidences, outcomes)
    interval = None
    if area is not None:
        q1 = area / (2 - area)
        q2 = 2 * area * area / (1 + area)
        var = (area * (1 - area) + (n_pos - 1) * (q1 - area * area) + (n_neg - 1) * (q2 - area * area)) / (n_pos * n_neg)
        half = 1.959964 * math.sqrt(max(var, 0.0))
        interval = (max(0.0, area - half), min(1.0, area + half))
    return {
        "n": len(outcomes),
        "n_positive": n_pos,
        "brier": brier_score(confidences, outcomes),
        "ece": expected_calibration_error(confidences, outcomes, n_bins),
        "auroc": area,
        "auroc_ci95": interval,
        "confidence_has_signal": bool(interval and interval[0] > 0.5),
        "reliability": reliability_bins(confidences, outcomes, n_bins),
    }
