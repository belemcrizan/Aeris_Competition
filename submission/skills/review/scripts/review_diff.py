#!/usr/bin/env python3
"""Read-only review of the working-tree diff before submission (stdlib only)."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath

LARGE_DIFF_LINES = 200
LARGE_DIFF_FILES = 5
MAX_UNTRACKED_BYTES = 200_000

DEBUG_PATTERNS = [
    (re.compile(r"\bbreakpoint\(\)"), "breakpoint()"),
    (re.compile(r"\bimport pdb\b|\bpdb\.set_trace\("), "pdb"),
    (re.compile(r"^\s*print\("), "print("),
    (re.compile(r"\b(TODO|FIXME|XXX)\b"), "TODO/FIXME marker"),
]
SCRATCH_NAME = re.compile(
    r"(^|/)(repro\w*|reproduce\w*|debug\w*|scratch\w*|tmp\w*|test_issue\w*|test_repro\w*)\.py$|\.(orig|rej|bak|log|swp|pyc)$|(^|/)__pycache__/"
)
DEPENDENCY_FILES = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "poetry.lock", "Pipfile", "Pipfile.lock", "tox.ini"}


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    return (
        p.name.startswith("test_")
        or p.name.endswith("_test.py")
        or p.name == "conftest.py"
        or any(part in {"tests", "test", "testing"} for part in p.parts[:-1])
    )


def parse_diff(diff: str) -> dict[str, dict]:
    files: dict[str, dict] = {}
    current = None
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            name = match.group(2) if match else line.split()[-1]
            current = files.setdefault(name, {"added": [], "removed": [], "status": "M", "binary": False})
        elif current is None:
            continue
        elif line.startswith("new file mode"):
            current["status"] = "A"
        elif line.startswith("deleted file mode"):
            current["status"] = "D"
        elif line.startswith("Binary files"):
            current["binary"] = True
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            current["added"].append(line[1:])
        elif line.startswith("-"):
            current["removed"].append(line[1:])
    return files


def analyze(files: dict[str, dict], untracked: dict[str, str]) -> list[tuple[str, str, str]]:
    flags: list[tuple[str, str, str]] = []
    all_files = dict(files)
    for name, content in untracked.items():
        all_files.setdefault(name, {"added": content.splitlines(), "removed": [], "status": "?", "binary": False})
    total_lines = 0
    for name, info in sorted(all_files.items()):
        total_lines += len(info["added"]) + len(info["removed"])
        base = PurePosixPath(name).name
        if SCRATCH_NAME.search(name):
            flags.append(("SCRATCH_FILE", name, "looks like a scratch/generated file; move it to /tmp or delete it"))
        if is_test_path(name):
            flags.append(("TEST_FILE_CHANGED", name, "hidden tests are applied on top of the patch; edits here may conflict"))
        if base in DEPENDENCY_FILES:
            flags.append(("DEPENDENCY_FILE_CHANGED", name, "dependency/config file modified; keep only if the issue requires it"))
        if info["binary"]:
            flags.append(("BINARY_FILE", name, "binary change in patch"))
        if info["status"] == "D":
            flags.append(("FILE_DELETED", name, "file deleted"))
        if not name.endswith(".py") and info["status"] in {"A", "?"}:
            flags.append(("NON_PYTHON_NEW_FILE", name, "new non-Python file; confirm it belongs to the fix"))
        for pattern, label in DEBUG_PATTERNS:
            if any(pattern.search(line) for line in info["added"]):
                flags.append(("DEBUG_STATEMENT", name, f"added line contains {label}"))
        added_norm = sorted(line.strip() for line in info["added"] if line.strip())
        removed_norm = sorted(line.strip() for line in info["removed"] if line.strip())
        if info["added"] and added_norm == removed_norm:
            flags.append(("WHITESPACE_ONLY", name, "changes only whitespace/indentation or line order"))
        added_crlf = sum(line.endswith("\r") for line in info["added"])
        removed_crlf = sum(line.endswith("\r") for line in info["removed"])
        if added_crlf != removed_crlf and max(added_crlf, removed_crlf) >= 3:
            flags.append(("LINE_ENDINGS_CHANGED", name, "line endings changed (CRLF/LF); rewrite the file with its original endings"))
        elif any(line.rstrip("\r") != line.rstrip() for line in info["added"]):
            flags.append(("TRAILING_WHITESPACE", name, "added lines end with whitespace"))
    if len(all_files) > LARGE_DIFF_FILES:
        flags.append(("MANY_FILES", "-", f"{len(all_files)} files changed; confirm each is needed"))
    if total_lines > LARGE_DIFF_LINES:
        flags.append(("LARGE_DIFF", "-", f"{total_lines} changed lines; confirm there is no unrelated change"))
    if not all_files:
        flags.append(("EMPTY_DIFF", "-", "no changes; an empty patch always fails"))
    return flags


def git(repo: Path, *args: str) -> str:
    # Bytes, not text mode: universal newlines would hide CRLF changes.
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    return proc.stdout.decode("utf-8", errors="replace")


def collect(repo: Path) -> tuple[dict[str, dict], dict[str, str]]:
    diff = git(repo, "diff", "HEAD", "--no-color", "--no-ext-diff")
    untracked: dict[str, str] = {}
    for line in git(repo, "status", "--porcelain", "--untracked-files=all").splitlines():
        if line.startswith("?? "):
            name = line[3:].strip().strip('"')
            path = repo / name
            if path.is_file():
                data = path.read_bytes()[:MAX_UNTRACKED_BYTES]
                untracked[name] = data.decode("utf-8", errors="replace")
    return parse_diff(diff), untracked


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 1 and " " in argv[0]:
        argv = shlex.split(argv[0])
    repo = Path("/workspace") if Path("/workspace").is_dir() else Path.cwd()
    if len(argv) >= 2 and argv[0] == "--repo":
        repo = Path(argv[1])
    elif argv:
        print("usage: review_diff.py [--repo PATH]", file=sys.stderr)
        return 2
    try:
        files, untracked = collect(repo)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    flags = analyze(files, untracked)
    added = sum(len(f["added"]) for f in files.values()) + sum(len(c.splitlines()) for c in untracked.values())
    removed = sum(len(f["removed"]) for f in files.values())
    print(f"DIFF: {len(files) + len(set(untracked) - set(files))} files, +{added} -{removed}")
    for name, info in sorted(files.items()):
        print(f"  {info['status']} {name} +{len(info['added'])} -{len(info['removed'])}")
    for name in sorted(set(untracked) - set(files)):
        print(f"  ? {name} (untracked, will be included by submit_patch)")
    if flags:
        print("FLAGS:")
        for code, name, message in flags:
            print(f"  {code} {name}: {message}")
    print(f"VERDICT: {'REVIEW' if flags else 'OK'} ({len(flags)} flags)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
