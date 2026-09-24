#!/usr/bin/env python3
"""Build and validate submission.zip for one variant.

    python scripts/build_submission.py                      # FULL -> dist/submission.zip
    python scripts/build_submission.py --variant B0         # -> dist/B0/submission.zip
    python scripts/build_submission.py --sync               # refresh submission/agent.yaml + prompts/system.md
    python scripts/build_submission.py --check-sync         # fail if those files are stale
    python scripts/build_submission.py --all --require-clean   # release manifest from a clean tree
    python scripts/build_submission.py --check-release      # provenance + content check of the manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import zipfile
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


def content_sha256(path: Path) -> str:
    """Hash of entry names, modes and uncompressed bytes; independent of the zlib build."""
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            digest.update(f"{info.filename}\0{info.external_attr >> 16:o}\0".encode())
            digest.update(hashlib.sha256(archive.read(info)).digest())
    return digest.hexdigest()


def component_hashes(stage: Path) -> dict:
    """Per-component SHA-256 so a run can be traced to its exact prompt and sampling."""

    def files(sub: str) -> dict[str, str]:
        root = stage / sub
        if not root.is_dir():
            return {}
        return {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}

    sampling = stage / "configs" / "sampling.yaml"
    return {
        "agent_yaml": sha256(stage / "agent.yaml"),
        "prompts": files("prompts"),
        "sampling": sha256(sampling) if sampling.is_file() else None,
        "adapters": files("adapters") or None,
    }


def build(variant_id: str, out: Path, strict: bool = False, manifest: list[dict] | None = None) -> int:
    variant = V.load_variant(variant_id)
    with tempfile.TemporaryDirectory(prefix="aeris_stage_") as tmp:
        stage = Path(tmp) / "submission"
        resolved = V.stage(variant, stage)
        tree_report = validate_tree(stage)
        if not tree_report.release_ok:
            print(tree_report.format())
            print("build aborted: staged tree is invalid or blocked by policy", file=sys.stderr)
            return 1
        hashes = component_hashes(stage)
        V.write_zip(stage, out)
    report = validate_zip(out)
    print(report.format())
    print(f"variant={variant.id} tools={list(resolved.tools)} modules={list(resolved.prompt_modules)} skills={list(resolved.skills)}")
    digest = sha256(out)
    print(f"archive={out} sha256={digest}")
    if manifest is not None:
        manifest.append(
            {
                "variant": variant.id,
                "archive": out.relative_to(V.REPO_ROOT).as_posix() if out.is_relative_to(V.REPO_ROOT) else str(out),
                "sha256": digest,
                "content_sha256": content_sha256(out),
                "bytes": out.stat().st_size,
                "tools": list(resolved.tools),
                "prompt_modules": list(resolved.prompt_modules),
                "skills": list(resolved.skills),
                "adapter": variant.adapter,
                "hashes": hashes,
                "validator": {
                    "result": "VALID" if report.release_ok else "INVALID",
                    "errors": len(report.errors),
                    "warnings": len(report.warnings),
                    "info": len(report.infos),
                },
            }
        )
    if not report.release_ok or (strict and report.warnings):
        return 1
    return 0


def git_state() -> dict:
    def run(*args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=V.REPO_ROOT, capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else ""

    return {"commit": run("rev-parse", "HEAD") or None, "dirty": bool(run("status", "--porcelain"))}


def write_manifest(entries: list[dict], path: Path) -> None:
    data = {
        "schema": "aeris-release-manifest/1",
        "model": V.MODEL,
        "default_variant": V.DEFAULT_VARIANT,
        "git": git_state(),
        "python": platform.python_version(),
        "variants": sorted(entries, key=lambda e: e["variant"]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"manifest={path}")


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


def check_manifest(path: Path) -> int:
    committed = {v["variant"]: v for v in json.loads(path.read_text(encoding="utf-8"))["variants"]}
    entries: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="aeris_manifest_") as tmp:
        for variant_id in V.list_variants():
            if build(variant_id, Path(tmp) / variant_id / "submission.zip", manifest=entries) != 0:
                return 1
    problems = []
    for entry in entries:
        old = committed.pop(entry["variant"], None)
        if old is None:
            problems.append(f"{entry['variant']}: missing from manifest")
        elif old.get("content_sha256") != entry["content_sha256"]:
            problems.append(f"{entry['variant']}: content changed since the manifest was written")
    problems += [f"{name}: in manifest but no longer a variant" for name in committed]
    for problem in problems:
        print(f"MANIFEST: {problem}", file=sys.stderr)
    if problems:
        print("run python scripts/build_submission.py --all and commit dist/release_manifest.json", file=sys.stderr)
        return 1
    print(f"manifest matches {len(entries)} rebuilt variants")
    return 0


def check_release(path: Path) -> int:
    """A release manifest must come from a clean tree whose only later change is the manifest."""
    data = json.loads(path.read_text(encoding="utf-8"))
    commit, dirty = data["git"].get("commit"), data["git"].get("dirty")
    problems = []
    if dirty is not False:
        problems.append("manifest was written from a dirty working tree")
    if not commit:
        problems.append("manifest has no git commit")
    else:
        proc = subprocess.run(["git", "diff", "--name-only", commit, "HEAD"], cwd=V.REPO_ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            problems.append(f"commit {commit[:12]} not available locally (fetch full history)")
        else:
            changed = {line for line in proc.stdout.splitlines() if line}
            other = sorted(changed - {path.relative_to(V.REPO_ROOT).as_posix()})
            if other:
                problems.append(f"{len(other)} files changed since {commit[:12]}: {other[:5]}")
    for problem in problems:
        print(f"RELEASE: {problem}", file=sys.stderr)
    if problems:
        print("commit everything, then run python scripts/build_submission.py --all --require-clean and commit the manifest alone", file=sys.stderr)
        return 1
    print(f"release manifest provenance OK: source commit {commit[:12]}, clean")
    return check_manifest(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", default=V.DEFAULT_VARIANT, help=f"one of {V.list_variants()}")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat validator warnings as errors")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--check-sync", action="store_true")
    parser.add_argument("--all", action="store_true", help="build every variant into dist/<variant>/")
    parser.add_argument(
        "--check-manifest",
        action="store_true",
        help="rebuild every variant in a temp dir and compare content hashes with dist/release_manifest.json",
    )
    parser.add_argument("--require-clean", action="store_true", help="with --all: refuse to write the manifest from a dirty tree")
    parser.add_argument(
        "--check-release",
        action="store_true",
        help="--check-manifest plus provenance: clean source commit, nothing but the manifest changed since",
    )
    args = parser.parse_args(argv)
    try:
        if args.sync or args.check_sync:
            return sync(check_only=args.check_sync)
        if args.check_manifest:
            return check_manifest(V.REPO_ROOT / "dist" / "release_manifest.json")
        if args.check_release:
            return check_release(V.REPO_ROOT / "dist" / "release_manifest.json")
        if args.all:
            if args.require_clean and git_state()["dirty"]:
                print("ERROR: working tree is dirty; commit first (--require-clean)", file=sys.stderr)
                return 1
            entries: list[dict] = []
            code = max(build(v, default_out(v), args.strict, entries) for v in V.list_variants())
            write_manifest(entries, V.REPO_ROOT / "dist" / "release_manifest.json")
            return code
        return build(args.variant, args.out or default_out(args.variant), args.strict)
    except V.VariantError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
