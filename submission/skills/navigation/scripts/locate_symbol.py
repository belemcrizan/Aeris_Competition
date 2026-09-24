#!/usr/bin/env python3
"""Map fully qualified Python symbols to file paths and line ranges (stdlib only)."""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", "build", "dist", ".tox", ".nox", "site-packages", ".eggs"}
SOURCE_ROOTS = ("", "src", "lib")
MAX_FALLBACK_HITS = 5
MAX_FILE_BYTES = 2_000_000


def resolve_module(repo: Path, parts: list[str]) -> tuple[Path, list[str]] | None:
    """Longest prefix of ``parts`` that is a module file under a source root."""
    for i in range(len(parts), 0, -1):
        for root in SOURCE_ROOTS:
            base = repo / root if root else repo
            module = base.joinpath(*parts[:i])
            for candidate in (module.with_suffix(".py"), module / "__init__.py"):
                if candidate.is_file():
                    return candidate, parts[i:]
    return None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def block_end(lines: list[str], start: int) -> int:
    """1-indexed last line of the def/class block starting at 0-indexed ``start``."""
    indent = _indent(lines[start])
    end = start
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if not stripped:
            continue
        if _indent(lines[j]) <= indent and not stripped.startswith(("#", ")", "]", "}")):
            break
        end = j
    return end + 1


def find_in_file(lines: list[str], names: list[str]) -> tuple[int, int] | None:
    """Locate nested def/class ``names``; return 1-indexed (start, end)."""
    lo, hi, min_indent = 0, len(lines), -1
    found = None
    for name in names:
        pattern = re.compile(rf"^(\s*)(?:async\s+def|def|class)\s+{re.escape(name)}\b")
        match_at = None
        for j in range(lo, hi):
            m = pattern.match(lines[j])
            if m and len(m.group(1)) > min_indent:
                match_at = j
                break
        if match_at is None:
            assign = re.compile(rf"^(\s*){re.escape(name)}\s*[:=]")
            for j in range(lo, hi):
                m = assign.match(lines[j])
                if m and len(m.group(1)) > min_indent:
                    return j + 1, j + 1
            return None
        end = block_end(lines, match_at)
        found = (match_at + 1, end)
        lo, hi, min_indent = match_at + 1, end, _indent(lines[match_at])
    return found


def iter_py_files(repo: Path):
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(dirpath) / filename


def fallback_search(repo: Path, name: str) -> list[str]:
    pattern = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b")
    hits = []
    for path in iter_py_files(repo):
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if pattern.match(line):
                rel = path.relative_to(repo).as_posix()
                hits.append(f"{rel}:{i + 1}-{block_end(lines, i)}  {line.strip()[:120]}")
                if len(hits) >= MAX_FALLBACK_HITS:
                    return hits
    return hits


def locate(repo: Path, symbol: str) -> list[str]:
    parts = [p for p in symbol.strip().split(".") if p]
    if not parts:
        return [f"{symbol} -> ERROR empty symbol"]
    resolved = resolve_module(repo, parts)
    if resolved:
        path, rest = resolved
        rel = path.relative_to(repo).as_posix()
        if not rest:
            return [f"{symbol} -> {rel} (module)"]
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        span = find_in_file(lines, rest)
        if span:
            return [f"{symbol} -> {rel}:{span[0]}-{span[1]}  {lines[span[0] - 1].strip()[:120]}"]
        hits = [h for h in fallback_search(repo, rest[-1])]
        note = f"{symbol} -> module {rel} found but {'.'.join(rest)} not defined there"
        return [note] + [f"   candidate {h}" for h in hits]
    hits = fallback_search(repo, parts[-1])
    if not hits:
        return [f"{symbol} -> NOT FOUND (no module and no def/class named {parts[-1]})"]
    return [f"{symbol} -> module not found; candidates:"] + [f"   {h}" for h in hits]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 1 and " " in argv[0]:
        argv = shlex.split(argv[0])
    repo = Path("/workspace") if Path("/workspace").is_dir() else Path.cwd()
    if len(argv) >= 2 and argv[0] == "--repo":
        repo, argv = Path(argv[1]), argv[2:]
    if not argv:
        print("usage: locate_symbol.py [--repo PATH] SYMBOL [SYMBOL ...]", file=sys.stderr)
        return 2
    if not repo.is_dir():
        print(f"ERROR: repository {repo} does not exist", file=sys.stderr)
        return 2
    for symbol in argv[:20]:
        print("\n".join(locate(repo, symbol)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
