"""Deterministic, repository-stratified dev / held-out split of the public tasks.

Tuning (prompts, thresholds, variant choice) may only look at ``dev``; ``heldout`` is
scored once per frozen variant (research/methodology.md).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict

DEFAULT_SEED = 20260924
DEFAULT_DEV_FRACTION = 0.7


def repo_of(task: dict) -> str:
    """``repo`` field if present, else the prefix of a SWE-bench style id (owner__repo-123)."""
    if task.get("repo"):
        return str(task["repo"])
    match = re.match(r"^(.+?)[-_]\d+$", str(task["instance_id"]))
    return match.group(1) if match else "unknown"


def _sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def make_split(tasks: list[dict], seed: int = DEFAULT_SEED, dev_fraction: float = DEFAULT_DEV_FRACTION) -> dict:
    if not 0.0 < dev_fraction < 1.0:
        raise ValueError("dev_fraction must be in (0, 1)")
    ids = [str(t["instance_id"]) for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate instance_id in task list")
    by_repo: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        by_repo[repo_of(task)].append(str(task["instance_id"]))
    dev: list[str] = []
    heldout: list[str] = []
    per_repo = {}
    for repo in sorted(by_repo):
        members = sorted(by_repo[repo])
        random.Random(f"{seed}:{repo}").shuffle(members)
        n_dev = round(len(members) * dev_fraction)
        if len(members) > 1:
            n_dev = min(max(n_dev, 1), len(members) - 1)
        dev += members[:n_dev]
        heldout += members[n_dev:]
        per_repo[repo] = {"total": len(members), "dev": n_dev, "heldout": len(members) - n_dev}
    split = {
        "schema": "aeris-data-split/1",
        "seed": seed,
        "dev_fraction": dev_fraction,
        "stratified_by": "repo",
        "n_tasks": len(ids),
        "input_ids_sha256": _sha256(sorted(ids)),
        "per_repo": per_repo,
        "dev": sorted(dev),
        "heldout": sorted(heldout),
    }
    split["split_sha256"] = _sha256({"dev": split["dev"], "heldout": split["heldout"]})
    return split


def select_smoke(tasks: list[dict], split: dict, n: int, seed: int = DEFAULT_SEED) -> dict:
    """``n`` dev tasks taken round-robin across repositories in a seeded order.

    Never draws from ``heldout``. Round-robin spreads the smoke set over repositories
    instead of letting one large repository (or its easiest tasks) dominate.
    """
    dev = set(split["dev"])
    by_repo: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        if str(task["instance_id"]) in dev:
            by_repo[repo_of(task)].append(str(task["instance_id"]))
    rng = random.Random(f"{seed}:smoke")
    repos = sorted(by_repo)
    rng.shuffle(repos)
    queues = {}
    for repo in repos:
        members = sorted(by_repo[repo])
        random.Random(f"{seed}:smoke:{repo}").shuffle(members)
        queues[repo] = members
    chosen: list[tuple[str, str]] = []
    while len(chosen) < n and any(queues.values()):
        for repo in repos:
            if queues[repo] and len(chosen) < n:
                chosen.append((queues[repo].pop(0), repo))
    return {
        "schema": "aeris-smoke-selection/1",
        "method": "dev split only; seeded repository order; round-robin one task per repository",
        "seed": seed,
        "split_sha256": split.get("split_sha256"),
        "n": len(chosen),
        "task_ids": [t for t, _ in chosen],
        "repos": {t: r for t, r in chosen},
    }


def verify_split(split: dict, tasks: list[dict]) -> list[str]:
    """Problems that would make ``split`` unusable for ``tasks``; empty means OK."""
    problems = []
    ids = sorted(str(t["instance_id"]) for t in tasks)
    if split.get("input_ids_sha256") != _sha256(ids):
        problems.append("task list differs from the one the split was made from")
    dev, heldout = set(split.get("dev", [])), set(split.get("heldout", []))
    if dev & heldout:
        problems.append(f"{len(dev & heldout)} tasks are in both dev and heldout")
    if (dev | heldout) != set(ids):
        problems.append("split does not cover exactly the task list")
    if split.get("split_sha256") != _sha256({"dev": sorted(dev), "heldout": sorted(heldout)}):
        problems.append("split_sha256 does not match its contents (edited by hand?)")
    regenerated = make_split(tasks, split.get("seed", DEFAULT_SEED), split.get("dev_fraction", DEFAULT_DEV_FRACTION))
    if regenerated["dev"] != sorted(dev):
        problems.append("split is not reproducible from its seed")
    return problems
