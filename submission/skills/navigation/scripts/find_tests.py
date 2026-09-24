#!/usr/bin/env python3
"""Rank test files by how directly they exercise given files or symbols (stdlib only)."""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", "build", "dist", ".tox", ".nox", "site-packages", ".eggs"}
MAX_RESULTS = 8
MAX_FILE_BYTES = 1_000_000


def is_test_file(rel: str) -> bool:
    p = PurePosixPath(rel)
    if not p.name.endswith(".py") or p.name == "conftest.py":
        return False
    return p.name.startswith("test_") or p.name.endswith("_test.py") or any(part in {"tests", "test"} for part in p.parts[:-1])


def iter_test_files(repo: Path):
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            rel = path.relative_to(repo).as_posix()
            if is_test_file(rel):
                yield path, rel


def terms_for(target: str) -> dict:
    """Module dotted path, symbol name and file stem to search for."""
    target = target.strip().replace("\\", "/")
    if target.endswith(".py"):
        parts = list(PurePosixPath(target).with_suffix("").parts)
        if parts and parts[0] in {"src", "lib"}:
            parts = parts[1:]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return {"module": ".".join(parts), "symbol": None, "stem": parts[-1] if parts else None}
    if "." in target:
        parts = target.split(".")
        return {"module": ".".join(parts[:-1]), "symbol": parts[-1], "stem": parts[-2] if len(parts) > 1 else None}
    return {"module": None, "symbol": target, "stem": None}


def score_file(text: str, rel: str, terms: list[dict]) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    name = PurePosixPath(rel).stem
    for t in terms:
        module = t["module"]
        if module:
            imports = len(re.findall(rf"^\s*(?:from|import)\s+{re.escape(module)}\b", text, re.MULTILINE))
            if imports:
                score += 3 * imports
                reasons.append(f"imports {module}")
        if t["symbol"]:
            mentions = len(re.findall(rf"\b{re.escape(t['symbol'])}\b", text))
            if mentions:
                score += 2 * min(mentions, 5)
                reasons.append(f"mentions {t['symbol']} x{mentions}")
        if t["stem"] and t["stem"] != "__init__" and t["stem"] in name:
            score += 2
            reasons.append(f"name matches {t['stem']}")
    return score, reasons


def rank(repo: Path, targets: list[str]) -> list[tuple[int, str, list[str]]]:
    terms = [terms_for(t) for t in targets]
    ranked = []
    for path, rel in iter_test_files(repo):
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        score, reasons = score_file(path.read_text(encoding="utf-8", errors="replace"), rel, terms)
        if score:
            ranked.append((score, rel, reasons))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[:MAX_RESULTS]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 1 and " " in argv[0]:
        argv = shlex.split(argv[0])
    repo = Path("/workspace") if Path("/workspace").is_dir() else Path.cwd()
    if len(argv) >= 2 and argv[0] == "--repo":
        repo, argv = Path(argv[1]), argv[2:]
    if not argv:
        print("usage: find_tests.py [--repo PATH] TARGET [TARGET ...]", file=sys.stderr)
        return 2
    if not repo.is_dir():
        print(f"ERROR: repository {repo} does not exist", file=sys.stderr)
        return 2
    ranked = rank(repo, argv)
    if not ranked:
        print("NO MATCHING TESTS; try a module name or grep -rln NAME tests/")
        return 0
    for score, rel, reasons in ranked:
        print(f"{rel} score={score} ({'; '.join(reasons)})")
    print("SUGGESTED: python -m pytest -x -q " + " ".join(rel for _, rel, _ in ranked[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
