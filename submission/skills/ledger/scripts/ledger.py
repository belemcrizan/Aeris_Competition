#!/usr/bin/env python3
"""Evidence ledger and uncertainty gate for a single task (stdlib only)."""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import sys
import time
from pathlib import Path

MAX_PATCH_ATTEMPTS = 3
MAX_INVESTIGATION_STEPS = 8
MAX_TEXT = 200
# (budget fraction upper bound, mode)
BUDGET_MODES = ((0.5, "NORMAL"), (0.8, "CONSERVATIVE"), (float("inf"), "CRITICAL"))
# mode -> (top weight needed for LOW, top weight below which uncertainty is HIGH)
THRESHOLDS = {"NORMAL": (0.6, 0.4), "CONSERVATIVE": (0.5, 0.3), "CRITICAL": (0.5, 0.3)}


def state_dir() -> Path:
    return Path(os.environ.get("AERIS_STATE_DIR", "/tmp/aeris"))


def ledger_path() -> Path:
    return state_dir() / "ledger.json"


def empty_state() -> dict:
    return {"claims": [], "hypotheses": {}, "experiments": [], "patches": [], "budget_used": None}


def load_state() -> dict:
    path = ledger_path()
    if not path.is_file():
        return empty_state()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_suffix(".corrupt.json")
        path.replace(backup)
        print(f"WARNING: ledger was corrupt, moved to {backup}; starting fresh", file=sys.stderr)
        return empty_state()


def save_state(state: dict) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(path)


def log_event(event_type: str, success: bool | None = True, **metadata) -> None:
    # Schema: aeris_comp/telemetry.py (FIELDS).
    record = {
        "timestamp": round(time.time(), 3),
        "task_id": os.environ.get("AERIS_TASK_ID"),
        "variant": os.environ.get("AERIS_VARIANT"),
        "event_type": event_type,
        "duration": None,
        "tool": "skill:ledger",
        "success": success,
        "metadata": metadata,
    }
    try:
        state_dir().mkdir(parents=True, exist_ok=True)
        with (state_dir() / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError as exc:
        print(f"WARNING: could not write telemetry: {exc}", file=sys.stderr)


def clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 3] + "..."


# ------------------------------------------------------------------ policy
def active_hypotheses(state: dict) -> dict:
    return {k: h for k, h in state["hypotheses"].items() if not h.get("rejected")}


def normalized_weights(state: dict) -> dict[str, float]:
    active = active_hypotheses(state)
    total = sum(max(h["weight"], 0.0) for h in active.values())
    if not active:
        return {}
    if total <= 0:
        return {k: 1.0 / len(active) for k in active}
    return {k: max(h["weight"], 0.0) / total for k, h in active.items()}


def entropy(weights: dict[str, float]) -> tuple[float, float]:
    """Return (entropy in nats, entropy normalized to [0, 1] by log n)."""
    h = -sum(p * math.log(p) for p in weights.values() if p > 0)
    n = len(weights)
    return h, (h / math.log(n) if n > 1 else 0.0)


def budget_mode(budget_used: float | None) -> str:
    if budget_used is None:
        return "NORMAL"
    for bound, mode in BUDGET_MODES:
        if budget_used < bound:
            return mode
    return "CRITICAL"


def assess(state: dict, budget_used: float | None = None) -> dict:
    if budget_used is None:
        budget_used = state.get("budget_used")
    mode = budget_mode(budget_used)
    weights = normalized_weights(state)
    h, h_norm = entropy(weights)
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    low_bar, high_bar = THRESHOLDS[mode]
    patches = state["patches"]
    steps = len(state["experiments"])

    if not ranked:
        level = "HIGH"
    else:
        top_id, top_p = ranked[0]
        has_support = bool(state["hypotheses"][top_id]["for"])
        if top_p >= low_bar and has_support:
            level = "LOW"
        elif top_p < high_bar:
            level = "HIGH"
        else:
            level = "MEDIUM"

    if patches and patches[-1]["result"] == "pass":
        action = "SUBMIT: last patch passed its tests; review the diff and submit"
    elif len(patches) >= MAX_PATCH_ATTEMPTS:
        action = f"SUBMIT: {len(patches)} patch attempts reached the limit; restore the best attempt and submit"
    elif not ranked:
        action = "INVESTIGATE: no active hypotheses; localize the issue and add one to three hypotheses"
    elif mode == "CRITICAL":
        action = (
            f"PATCH {ranked[0][0]} now, validate once and submit"
            if not patches
            else "SUBMIT: budget critical; validate the best patch once and submit"
        )
    elif level == "LOW":
        action = f"PATCH {ranked[0][0]} with the minimal change"
    elif steps >= MAX_INVESTIGATION_STEPS and not patches:
        action = f"PATCH {ranked[0][0]}: investigation limit reached; let tests provide the next evidence"
    elif level == "MEDIUM" and len(ranked) > 1:
        action = f"DISCRIMINATE {ranked[0][0]} vs {ranked[1][0]} with the cheapest check whose outcome differs"
    elif level == "MEDIUM":
        action = f"CONFIRM {ranked[0][0]}: find direct evidence for or against it"
    else:
        action = "INVESTIGATE: read the top candidates or reproduce; do not edit yet"

    failed_by_hyp: dict[str, int] = {}
    for patch in patches:
        if patch["result"] == "fail" and patch.get("hypothesis"):
            failed_by_hyp[patch["hypothesis"]] = failed_by_hyp.get(patch["hypothesis"], 0) + 1
    notes = [f"{hid} has {n} failed patches; lower its weight or try the next hypothesis" for hid, n in failed_by_hyp.items() if n >= 2]

    return {
        "mode": mode,
        "level": level,
        "weights": dict(ranked),
        "entropy": h,
        "entropy_norm": h_norm,
        "action": action,
        "notes": notes,
        "investigation_steps": steps,
        "patch_attempts": len(patches),
    }


# ------------------------------------------------------------------ output
def render(state: dict, assessment: dict | None = None) -> str:
    lines = []
    if state["claims"]:
        lines.append("CLAIMS: " + " | ".join(state["claims"][-6:]))
    weights = normalized_weights(state)
    for hid, hyp in sorted(state["hypotheses"].items(), key=lambda kv: -weights.get(kv[0], -1)):
        tag = "REJECTED" if hyp.get("rejected") else f"p={weights.get(hid, 0):.2f}"
        lines.append(f"{hid} [{tag}] target={hyp['target']} :: {hyp['claim']}")
        for item in hyp["for"][-2:]:
            lines.append(f"   + {item}")
        for item in hyp["against"][-2:]:
            lines.append(f"   - {item}")
    for exp in state["experiments"][-5:]:
        lines.append(f"EXP {exp['command']} => {exp['result']}")
    for i, patch in enumerate(state["patches"], 1):
        lines.append(f"PATCH#{i} {patch['hypothesis'] or '-'} files={','.join(patch['files'])} result={patch['result']} {patch['note']}".rstrip())
    if assessment:
        top = next(iter(assessment["weights"].items()), ("-", 0.0))
        lines.append(
            f"MODE: {assessment['mode']}  UNCERTAINTY: {assessment['level']}  top={top[0]} p={top[1]:.2f} "
            f"entropy={assessment['entropy_norm']:.2f}  steps={assessment['investigation_steps']} "
            f"patches={assessment['patch_attempts']}/{MAX_PATCH_ATTEMPTS}"
        )
        lines.append(f"ACTION: {assessment['action']}")
        lines.extend(f"NOTE: {note}" for note in assessment["notes"])
    return "\n".join(lines) if lines else "ledger is empty"


# --------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("claim")
    p.add_argument("text")
    p = sub.add_parser("add")
    p.add_argument("id")
    p.add_argument("--target", required=True)
    p.add_argument("--weight", type=float, required=True)
    p.add_argument("--claim", required=True)
    p = sub.add_parser("update")
    p.add_argument("id")
    p.add_argument("--weight", type=float)
    p.add_argument("--for", dest="support", action="append", default=[])
    p.add_argument("--against", action="append", default=[])
    p.add_argument("--reject", action="store_true")
    p = sub.add_parser("experiment")
    p.add_argument("--command", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--purpose", default="")
    p = sub.add_parser("patch")
    p.add_argument("--files", required=True)
    p.add_argument("--hypothesis", default="")
    p.add_argument("--result", choices=["pass", "fail", "untested"], required=True)
    p.add_argument("--note", default="")
    p = sub.add_parser("status")
    p.add_argument("--budget-used", type=float)
    sub.add_parser("reset")
    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    if len(argv) == 1 and " " in argv[0]:
        argv = shlex.split(argv[0])
    if "--" in argv:
        # ADK renders dict args as "--opt value ... -- positional ...";
        # the subcommand must come first for argparse.
        i = argv.index("--")
        argv = argv[i + 1 :] + argv[:i]
    return argv


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    if args.cmd == "reset":
        if ledger_path().exists():
            ledger_path().unlink()
        print("ledger reset")
        return 0
    state = load_state()
    assessment = None
    if args.cmd == "claim":
        state["claims"].append(clip(args.text))
    elif args.cmd == "add":
        if args.id in state["hypotheses"]:
            print(f"ERROR: {args.id} already exists; use update", file=sys.stderr)
            return 2
        if args.weight < 0:
            print("ERROR: weight must be >= 0", file=sys.stderr)
            return 2
        state["hypotheses"][args.id] = {
            "target": clip(args.target),
            "claim": clip(args.claim),
            "weight": args.weight,
            "for": [],
            "against": [],
            "rejected": False,
        }
        log_event("hypothesis_created", id=args.id, target=args.target, weight=args.weight)
    elif args.cmd == "update":
        hyp = state["hypotheses"].get(args.id)
        if hyp is None:
            print(f"ERROR: unknown hypothesis {args.id}; known: {sorted(state['hypotheses'])}", file=sys.stderr)
            return 2
        if args.weight is not None:
            if args.weight < 0:
                print("ERROR: weight must be >= 0", file=sys.stderr)
                return 2
            hyp["weight"] = args.weight
        hyp["for"] += [clip(t) for t in args.support]
        hyp["against"] += [clip(t) for t in args.against]
        if args.reject:
            hyp["rejected"] = True
        log_event("hypothesis_updated", id=args.id, weight=hyp["weight"], rejected=hyp["rejected"])
    elif args.cmd == "experiment":
        state["experiments"].append({"command": clip(args.command), "purpose": clip(args.purpose), "result": clip(args.result)})
        log_event("tool_result", None, kind="experiment", command=clip(args.command), purpose=clip(args.purpose))
    elif args.cmd == "patch":
        files = [f.strip() for f in args.files.split(",") if f.strip()]
        state["patches"].append({"files": files, "hypothesis": args.hypothesis, "result": args.result, "note": clip(args.note)})
        outcome = {"pass": True, "fail": False}.get(args.result)
        log_event("patch_attempt", outcome, files=files, hypothesis=args.hypothesis, result=args.result, attempt=len(state["patches"]))
    elif args.cmd == "status":
        if args.budget_used is not None:
            if not 0 <= args.budget_used <= 1.5:
                print("ERROR: --budget-used is a fraction such as 0.35", file=sys.stderr)
                return 2
            state["budget_used"] = args.budget_used
        assessment = assess(state)
        top = next(iter(assessment["weights"]), None)
        log_event(
            "uncertainty_state",
            level=assessment["level"],
            entropy=round(assessment["entropy_norm"], 3),
            top=top,
            top_p=round(assessment["weights"][top], 3) if top else None,
            n_hypotheses=len(assessment["weights"]),
            action=clip(assessment["action"]),
        )
        log_event("budget_status", mode=assessment["mode"], budget_used=state["budget_used"])
    save_state(state)
    print(render(state, assessment))
    return 0


if __name__ == "__main__":
    sys.exit(main())
