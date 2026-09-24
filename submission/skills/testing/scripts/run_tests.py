#!/usr/bin/env python3
"""Run pytest and print a compact, signature-bearing failure report (stdlib only)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

MAX_FAILURES_SHOWN = 5
MAX_TAIL_LINES = 25
PYTEST_FLAGS = ["-q", "-rfE", "--tb=short", "-p", "no:cacheprovider"]

SUMMARY_COUNT = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected)")
SHORT_SUMMARY = re.compile(r"^(FAILED|ERROR) (\S+)(?: - (.*))?$")
FRAME = re.compile(r"^(\S+\.py):(\d+): in (\S+)")
EXCEPTION_LINE = re.compile(r"^E\s+([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Failed)|AssertionError)\b:?\s*(.*)$")
ASSERT_EQ = re.compile(r"^E\s+(?:AssertionError:\s*)?assert (.+?) (==|!=|not in|in|is not|is) (.+)$")
VOLATILE = re.compile(r"0x[0-9a-fA-F]+|\b\d+(\.\d+)?\b|'/[^']*'|\"/[^\"]*\"")


def state_dir() -> Path:
    return Path(os.environ.get("AERIS_STATE_DIR", "/tmp/aeris"))


def parse_pytest_output(text: str) -> dict:
    lines = text.splitlines()
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for line in reversed(lines):
        if re.search(r"\b(passed|failed|error|no tests ran)\b", line) and ("=" in line or line[:1].isdigit()):
            for num, kind in SUMMARY_COUNT.findall(line):
                key = "errors" if kind.startswith("error") else kind
                if key in counts:
                    counts[key] = int(num)
            break

    failures = []
    for line in lines:
        match = SHORT_SUMMARY.match(line.strip())
        if match:
            failures.append({"kind": match.group(1), "test": match.group(2), "message": (match.group(3) or "").strip()})

    exceptions = []
    frames = []
    comparisons = []
    for line in lines:
        m = EXCEPTION_LINE.match(line)
        if m:
            exceptions.append((m.group(1), m.group(2).strip()))
        m = FRAME.match(line.strip())
        if m:
            frames.append(f"{m.group(1)}:{m.group(2)} {m.group(3)}")
        m = ASSERT_EQ.match(line)
        if m:
            comparisons.append({"left": m.group(1).strip(), "op": m.group(2), "right": m.group(3).strip()})

    for failure in failures:
        message = failure["message"]
        exc = message.split(":", 1)[0].strip() if ":" in message else ""
        failure["exception"] = exc if re.fullmatch(r"[A-Za-z_][\w.]*", exc) else (exceptions[0][0] if exceptions else "")

    collection_error = "error" in text.lower() and ("ERROR collecting" in text or "ImportError while importing" in text)
    if "no tests ran" in text and not failures:
        status = "NO_TESTS"
    elif collection_error:
        status = "COLLECTION_ERROR"
    elif counts["failed"] or counts["errors"] or failures:
        status = "FAIL"
    elif counts["passed"]:
        status = "PASS"
    else:
        status = "UNKNOWN"

    return {
        "status": status,
        "counts": counts,
        "failures": failures,
        "exceptions": exceptions,
        "frames": frames,
        "comparisons": comparisons,
    }


def signature(parsed: dict) -> str:
    """Hash of failing tests and exception types with volatile tokens removed."""
    parts = sorted(
        f"{f['test']}|{f.get('exception', '')}|{VOLATILE.sub('#', f['message'])[:120]}" for f in parsed["failures"]
    )
    if not parts and parsed["status"] not in {"PASS"}:
        parts = [parsed["status"]] + [f"{e}|{VOLATILE.sub('#', m)[:120]}" for e, m in parsed["exceptions"][:3]]
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:12]


def log_event(event_type: str, success: bool | None = None, duration: float | None = None, **metadata) -> None:
    # Schema: aeris_comp/telemetry.py (FIELDS).
    record = {
        "timestamp": round(time.time(), 3),
        "task_id": os.environ.get("AERIS_TASK_ID"),
        "variant": os.environ.get("AERIS_VARIANT"),
        "event_type": event_type,
        "duration": None if duration is None else round(duration, 3),
        "tool": "skill:testing",
        "success": success,
        "metadata": metadata,
    }
    try:
        state_dir().mkdir(parents=True, exist_ok=True)
        with (state_dir() / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError as exc:
        print(f"WARNING: could not write telemetry: {exc}", file=sys.stderr)


def log_outcome(args_key: str, status: str, sig: str, seen: int, elapsed: float, counts: dict | None = None) -> None:
    log_event("test_result", status == "PASS", elapsed, args=args_key[:200], status=status, counts=counts or {})
    if status != "PASS":
        log_event("failure_signature", False, signature=sig, status=status, seen=seen, repeated=seen > 1)
        if seen > 1:
            log_event("retry", False, signature=sig, seen=seen)


def record_history(args_key: str, sig: str, status: str) -> int:
    path = state_dir() / "test_history.json"
    try:
        history = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except json.JSONDecodeError:
        history = []
    history.append({"args": args_key, "signature": sig, "status": status, "ts": round(time.time(), 3)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history[-200:]), encoding="utf-8")
    return sum(1 for h in history if h["args"] == args_key and h["signature"] == sig)


def format_report(parsed: dict, sig: str, seen: int, elapsed: float, raw: str) -> str:
    c = parsed["counts"]
    out = [
        f"RESULT: {parsed['status']}  passed={c['passed']} failed={c['failed']} errors={c['errors']} "
        f"skipped={c['skipped']}  ({elapsed:.1f}s)"
    ]
    frames = [f for f in parsed["frames"] if "site-packages" not in f][:6]
    for failure in parsed["failures"][:MAX_FAILURES_SHOWN]:
        out.append(f"{failure['kind']} {failure['test']} - {failure['message'][:200]}")
    if len(parsed["failures"]) > MAX_FAILURES_SHOWN:
        out.append(f"... {len(parsed['failures']) - MAX_FAILURES_SHOWN} more failures")
    if parsed["comparisons"]:
        cmp = parsed["comparisons"][0]
        out.append(f"  first comparison: {cmp['left'][:150]} {cmp['op']} {cmp['right'][:150]}")
    if parsed["exceptions"]:
        exc, msg = parsed["exceptions"][0]
        out.append(f"  first exception: {exc}: {msg[:200]}")
    if frames:
        out.append("  frames: " + " | ".join(frames))
    if parsed["status"] in {"COLLECTION_ERROR", "UNKNOWN", "NO_TESTS"} or (parsed["status"] == "FAIL" and not parsed["failures"]):
        tail = [line for line in raw.splitlines() if line.strip()][-MAX_TAIL_LINES:]
        out.append("  output tail:")
        out.extend("    " + line[:200] for line in tail)
    if parsed["status"] != "PASS":
        repeated = "REPEATED" if seen > 1 else "new"
        out.append(f"SIGNATURE: {sig}  (seen {seen} times for these arguments: {repeated})")
    return "\n".join(out)


def split_args(argv: list[str]) -> tuple[int, Path, list[str]]:
    if len(argv) == 1 and " " in argv[0]:
        argv = shlex.split(argv[0])
    timeout = 300
    repo = Path("/workspace") if Path("/workspace").is_dir() else Path.cwd()
    rest: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--timeout" and i + 1 < len(argv):
            timeout = int(argv[i + 1])
            i += 2
            continue
        if arg == "--repo" and i + 1 < len(argv):
            repo = Path(argv[i + 1])
            i += 2
            continue
        if arg == "--":
            rest.extend(argv[i + 1 :])
            break
        rest.append(arg)
        i += 1
    return timeout, repo, rest


def main(argv: list[str] | None = None) -> int:
    try:
        timeout, repo, pytest_args = split_args(sys.argv[1:] if argv is None else argv)
    except ValueError as exc:
        print(f"ERROR: bad arguments: {exc}", file=sys.stderr)
        return 2
    if not repo.is_dir():
        print(f"ERROR: repository {repo} does not exist", file=sys.stderr)
        return 2
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "pytest", *PYTEST_FLAGS, *pytest_args]
    key = " ".join(pytest_args)
    log_event("test_start", args=key[:200], timeout=timeout)
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=timeout)
        raw = proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        seen = record_history(key, "TIMEOUT", "TIMEOUT")
        log_outcome(key, "TIMEOUT", "TIMEOUT", seen, elapsed)
        print(f"RESULT: TIMEOUT after {elapsed:.0f}s; narrow the selection (-k, single file) or look for a hang")
        print(f"SIGNATURE: TIMEOUT  (seen {seen} times for these arguments)")
        return 0
    elapsed = time.monotonic() - start
    parsed = parse_pytest_output(raw)
    sig = signature(parsed)
    seen = record_history(key, sig, parsed["status"])
    log_outcome(key, parsed["status"], sig, seen, elapsed, parsed["counts"])
    print(format_report(parsed, sig, seen, elapsed, raw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
