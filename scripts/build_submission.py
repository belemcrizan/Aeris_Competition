#!/usr/bin/env python3
"""Build and validate submission.zip for one variant.

    python scripts/build_submission.py                      # FULL -> dist/submission.zip
    python scripts/build_submission.py --variant B0         # -> dist/B0/submission.zip
    python scripts/build_submission.py --sync               # refresh submission/agent.yaml + prompts/system.md
    python scripts/build_submission.py --check-sync         # fail if those files are stale
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

import _bootstrap  # noqa: F401

from aeris_comp import variants as V
from aeris_comp.validation import validate_tree, validate_zip

SYNCED_FILES = ("agent.yaml", "prompts/system.md")


def default_out(variant_id: str) -> Path:
    if variant_id == V.DEFAULT_VARIANT:
        return V.REPO_ROOT / "dist" / "submission.zip"
    return V.REPO_ROOT / "dist" / variant_id / "submission.zip"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(variant_id: str, out: Path, strict: bool = False) -> int:
    variant = V.load_variant(variant_id)
    with tempfile.TemporaryDirectory(prefix="aeris_stage_") as tmp:
        stage = Path(tmp) / "submission"
        resolved = V.stage(variant, stage)
        tree_report = validate_tree(stage)
        if not tree_report.ok:
            print(tree_report.format())
            print("build aborted: staged tree is invalid", file=sys.stderr)
            return 1
        V.write_zip(stage, out)
    report = validate_zip(out)
    print(report.format())
    print(f"variant={variant.id} tools={list(resolved.tools)} modules={list(resolved.prompt_modules)} skills={list(resolved.skills)}")
    print(f"archive={out} sha256={sha256(out)}")
    if not report.ok or (strict and report.warnings):
        return 1
    return 0


def sync(check_only: bool) -> int:
    variant = V.load_variant(V.DEFAULT_VARIANT)
    with tempfile.TemporaryDirectory(prefix="aeris_sync_") as tmp:
        stage = Path(tmp) / "submission"
        V.stage(variant, stage)
        stale = []
        for rel in SYNCED_FILES:
            rendered = (stage / rel).read_text(encoding="utf-8")
            target = V.SUBMISSION_SRC / rel
            current = target.read_text(encoding="utf-8") if target.is_file() else None
            if current != rendered:
                stale.append(rel)
                if not check_only:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(rendered, encoding="utf-8", newline="\n")
    if check_only and stale:
        print(f"stale: {stale}; run python scripts/build_submission.py --sync", file=sys.stderr)
        return 1
    print(f"{'checked' if check_only else 'synced'}: {list(SYNCED_FILES)}" + (f" (updated {stale})" if stale and not check_only else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", default=V.DEFAULT_VARIANT, help=f"one of {V.list_variants()}")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat validator warnings as errors")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--check-sync", action="store_true")
    parser.add_argument("--all", action="store_true", help="build every variant into dist/<variant>/")
    args = parser.parse_args(argv)
    try:
        if args.sync or args.check_sync:
            return sync(check_only=args.check_sync)
        if args.all:
            return max(build(v, default_out(v), args.strict) for v in V.list_variants())
        return build(args.variant, args.out or default_out(args.variant), args.strict)
    except V.VariantError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
