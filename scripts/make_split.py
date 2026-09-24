#!/usr/bin/env python3
"""Create or verify the deterministic dev/held-out split (research/results/data_split.json).

    python scripts/make_split.py --tasks data/tasks.jsonl
    python scripts/make_split.py --tasks data/tasks.jsonl --verify
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from aeris_comp.scoring import load_tasks
from aeris_comp.split import DEFAULT_DEV_FRACTION, DEFAULT_SEED, make_split, verify_split

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "research" / "results" / "data_split.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", type=Path, required=True, help="tasks .jsonl with instance_id (and repo)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--dev-fraction", type=float, default=DEFAULT_DEV_FRACTION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verify", action="store_true", help="check an existing split instead of writing one")
    args = parser.parse_args(argv)
    tasks = list(load_tasks(args.tasks).values())
    if args.verify:
        problems = verify_split(json.loads(args.out.read_text(encoding="utf-8")), tasks)
        for problem in problems:
            print(f"PROBLEM: {problem}")
        print("SPLIT OK" if not problems else "SPLIT INVALID")
        return 1 if problems else 0
    if args.out.exists():
        print(f"{args.out} exists; refusing to overwrite a frozen split (delete it deliberately first)", file=sys.stderr)
        return 1
    split = make_split(tasks, args.seed, args.dev_fraction)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(split, indent=1) + "\n", encoding="utf-8")
    print(f"dev={len(split['dev'])} heldout={len(split['heldout'])} split_sha256={split['split_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
