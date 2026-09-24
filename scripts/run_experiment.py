#!/usr/bin/env python3
"""Reproducible experiment bookkeeping.

    prepare   build a variant into artifacts/runs/<run_id>/ with a manifest
    score     score harness predictions locally (needs the competition dataset)
    summarize print metrics for a run
    compare   paired comparison of two runs on shared tasks
    fidelity  agreement of our local scorer with official grades

Running the agent itself requires the competition harness (HARNESS_README.md); this
script does not simulate it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import _bootstrap  # noqa: F401
from build_submission import component_hashes

from aeris_comp import variants as V
from aeris_comp.metrics import paired_comparison, scorer_agreement, summarize
from aeris_comp.scoring import load_predictions, load_tasks, score_task
from aeris_comp.telemetry import make_event, write_events
from aeris_comp.validation import validate_zip

RUNS_DIR = V.REPO_ROOT / "artifacts" / "runs"


def git_state() -> dict:
    def run(*args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=V.REPO_ROOT, capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else ""

    return {"commit": run("rev-parse", "HEAD") or None, "dirty": bool(run("status", "--porcelain"))}


def cmd_prepare(args: argparse.Namespace) -> int:
    variant = V.load_variant(args.variant)
    if args.require_clean and git_state()["dirty"]:
        print("ERROR: working tree is dirty; a reportable run must be reconstructible (commit first)", file=sys.stderr)
        return 2
    run_id = args.run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}_{variant.id}"
    run_dir = RUNS_DIR / run_id
    if run_dir.exists():
        print(f"ERROR: {run_dir} already exists", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="aeris_stage_") as tmp:
        stage = Path(tmp) / "submission"
        resolved = V.stage(variant, stage)
        hashes = component_hashes(stage)
        zip_path = run_dir / "submission.zip"
        V.write_zip(stage, zip_path)
    report = validate_zip(zip_path)
    manifest = {
        "run_id": run_id,
        "variant": variant.id,
        "description": variant.description,
        "components": list(variant.components),
        "tools": list(resolved.tools),
        "prompt_modules": list(resolved.prompt_modules),
        "skills": list(resolved.skills),
        "adapter": variant.adapter,
        "submission_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        "hashes": hashes,
        "valid": report.release_ok,
        "git": git_state(),
        "created_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "notes": args.notes or "",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(report.format())
    print(f"prepared {run_dir}")
    if manifest["git"]["dirty"]:
        print("WARNING: working tree is dirty; commit before running a reportable experiment")
    return 0 if report.release_ok else 1


def cmd_score(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    predictions = load_predictions(args.predictions)
    ids = args.task_ids or sorted(predictions)
    if args.split:
        split = json.loads(args.split_file.read_text(encoding="utf-8"))
        allowed = set(split[args.split])
        ids = [i for i in ids if i in allowed]
    if args.limit:
        ids = ids[: args.limit]
    missing = [i for i in ids if i not in tasks]
    if missing:
        print(f"ERROR: predictions for unknown tasks: {missing[:5]}", file=sys.stderr)
        return 2
    args.run_dir.mkdir(parents=True, exist_ok=True)
    records_path = args.run_dir / "records.jsonl"
    manifest_path = args.run_dir / "manifest.json"
    variant = json.loads(manifest_path.read_text(encoding="utf-8")).get("variant") if manifest_path.is_file() else None
    records = []
    with records_path.open("w", encoding="utf-8") as out:
        for instance_id in ids:
            result = score_task(tasks[instance_id], predictions.get(instance_id), args.snapshots, python=args.python, timeout=args.timeout, setup_cmd=args.setup_cmd)
            record = result.to_dict()
            records.append(record)
            out.write(json.dumps(record) + "\n")
            event = make_event(
                "grade_result",
                task_id=instance_id,
                variant=variant,
                duration=record.get("scoring_seconds"),
                tool="local_scorer",
                success=result.status == "PASS",
                metadata={"status": result.status, "failure_category": result.failure_category},
            )
            write_events([event], args.run_dir / "events.jsonl")
            print(f"{instance_id}: {result.status} {result.detail[:120]}")
    summary = summarize(records)
    (args.run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def read_records(path: Path) -> list[dict]:
    path = path / "records.jsonl" if path.is_dir() else path
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_summarize(args: argparse.Namespace) -> int:
    print(json.dumps(summarize(read_records(args.run)), indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    print(json.dumps(paired_comparison(read_records(args.a), read_records(args.b)), indent=2))
    return 0


def cmd_fidelity(args: argparse.Namespace) -> int:
    report = scorer_agreement(read_records(args.ours), read_records(args.official))
    print(json.dumps(report, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--variant", required=True)
    p.add_argument("--run-id")
    p.add_argument("--notes")
    p.add_argument("--require-clean", action="store_true", help="refuse to prepare from a dirty working tree")
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("score")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--tasks", type=Path, required=True, help="dataset tasks.jsonl")
    p.add_argument("--snapshots", type=Path, required=True, help="dataset snapshots/ directory")
    p.add_argument("--predictions", type=Path, required=True, help="submission.parquet or .jsonl with id,prediction")
    p.add_argument("--task-ids", nargs="*")
    p.add_argument("--limit", type=int)
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--setup-cmd", help="shell command run in the repo before tests, e.g. the dataset sandbox/setup.py")
    p.add_argument("--split", choices=["dev", "heldout"], help="score only tasks in this part of the split")
    p.add_argument("--split-file", type=Path, default=V.REPO_ROOT / "research" / "results" / "data_split.json")
    p.set_defaults(func=cmd_score)
    p = sub.add_parser("summarize")
    p.add_argument("run", type=Path, help="run directory or records.jsonl")
    p.set_defaults(func=cmd_summarize)
    p = sub.add_parser("compare")
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    p.set_defaults(func=cmd_compare)
    p = sub.add_parser("fidelity", help="agreement of our scorer with official grades on the same predictions")
    p.add_argument("ours", type=Path, help="our records.jsonl (or run dir)")
    p.add_argument("official", type=Path, help="official grades as records with instance_id,status")
    p.set_defaults(func=cmd_fidelity)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except V.VariantError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
