#!/usr/bin/env python3
"""Detect official competition artifacts, audit what can be audited, print the next step.

    python scripts/competition_bootstrap.py                 # uses external/competition/
    python scripts/competition_bootstrap.py --dir D:/kaggle/gemma-4-developer-agent

Safe to rerun. Reads the artifacts, never modifies them, never needs credentials.
Writes only:
    artifacts/audits/competition_inventory.json   names, sizes, SHA-256 (no contents)
    artifacts/audits/harness_readme_mentions.json which open questions HARNESS_README touches
    artifacts/audits/sample_submission_diff.md    B0 and FULL vs the official sample
    research/results/data_split.json              only if absent (then frozen)

Exit codes: 0 all artifacts present and no INCOMPATIBLE finding; 1 INCOMPATIBLE finding
or invalid split; 3 artifacts missing (see docs/HUMAN_HANDOFF.md).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import _bootstrap  # noqa: F401
from build_submission import build

from aeris_comp import adk_conformance
from aeris_comp import competition_artifacts as CA
from aeris_comp.scoring import load_tasks
from aeris_comp.split import make_split, verify_split
from aeris_comp.submission_diff import INCOMPATIBLE, compare, render_markdown
from aeris_comp.validation import validate_tree, validate_zip

REPO = Path(__file__).resolve().parents[1]
AUDITS = REPO / "artifacts" / "audits"
SPLIT = REPO / "research" / "results" / "data_split.json"


def log(tag: str, message: str) -> None:
    print(f"[{tag:<7}] {message}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, help=f"artifact directory (default ${CA.ENV_VAR} or external/competition)")
    parser.add_argument("--audits", type=Path, default=AUDITS)
    parser.add_argument("--split-out", type=Path, default=SPLIT)
    args = parser.parse_args(argv)

    found = CA.locate(args.dir or CA.competition_dir())
    if not found.root.is_dir():
        log("BLOCKED", f"{found.root} does not exist")
        log("NEXT", "follow docs/HUMAN_HANDOFF.md, then rerun this command")
        return 3
    write_json(args.audits / "competition_inventory.json", CA.inventory(found))
    for name in ("harness_readme", "sample_submission", "tasks"):
        paths = getattr(found, name)
        log("FOUND" if paths else "MISSING", f"{name}: {', '.join(p.relative_to(found.root).as_posix() for p in paths) or '-'}")
    code = 0

    if found.harness_readme:
        text = found.harness_readme[0].read_text(encoding="utf-8", errors="replace")
        mentions = CA.readme_mentions(text)
        write_json(args.audits / "harness_readme_mentions.json", {"source": found.harness_readme[0].name, **mentions})
        missing_tools = [t for t, hit in mentions["tools"].items() if not hit]
        log("AUDIT", f"HARNESS_README mentions {sum(mentions['tools'].values())}/{len(mentions['tools'])} of our tools; not mentioned: {missing_tools or 'none'}")
        log("MANUAL", "read HARNESS_README in full and update docs/OFFICIAL_ARTIFACT_AUDIT.md rows C-01, C-07, C-12..C-15")

    if found.sample_submission:
        sample = found.sample_submission[0]
        sections = {}
        with tempfile.TemporaryDirectory(prefix="aeris_boot_") as tmp:
            for variant in ("B0", "FULL"):
                out = Path(tmp) / variant / "submission.zip"
                if build(variant, out) != 0:
                    log("FAIL", f"{variant} does not build")
                    return 1
                sections[f"{variant} vs sample"] = compare(out, sample)
        (args.audits / "sample_submission_diff.md").write_text(
            render_markdown(sections, sample.relative_to(found.root).as_posix()), encoding="utf-8", newline="\n"
        )
        bad = [f for fs in sections.values() for f in fs if f.verdict == INCOMPATIBLE]
        for f in bad:
            log("INCOMPAT", f"{f.aspect}: ours={f.ours} sample={f.sample} ({f.note})")
        log("AUDIT", f"sample diff written: {len(bad)} INCOMPATIBLE findings -> artifacts/audits/sample_submission_diff.md")
        if bad:
            code = 1
        ours = validate_tree(sample) if sample.is_dir() else validate_zip(sample)
        log("VALID", f"our validator on the official sample: {len(ours.errors)} errors, {len(ours.warnings)} warnings")
        for issue in ours.errors:
            log("WARN", f"validator rejects the official sample ({issue.code}): relax this rule; authority 2 outranks it")
        code = code or (1 if ours.errors else 0)
        report = adk_conformance.check_path(sample)
        log("ADK", f"official sample under ADK {report.get('adk_version')}: {report['status']}")
        if report["status"] == "FAIL":
            log("WARN", "our ADK checker rejects the official sample: the checker is stricter than authority 2; fix the checker, not the sample")

    if found.tasks:
        tasks = list(load_tasks(found.tasks[0]).values())
        if args.split_out.exists():
            problems = verify_split(json.loads(args.split_out.read_text(encoding="utf-8")), tasks)
            log("SPLIT", "frozen split verified" if not problems else f"INVALID: {problems}")
            code = code or (1 if problems else 0)
        else:
            split = make_split(tasks)
            write_json(args.split_out, split)
            log("SPLIT", f"created dev={len(split['dev'])} heldout={len(split['heldout'])} sha256={split['split_sha256'][:16]}; commit it now (frozen)")

    if found.missing:
        log("BLOCKED", f"still missing: {found.missing}; see docs/HUMAN_HANDOFF.md")
        return 3 if code == 0 else code
    log("NEXT", "python scripts/run_experiment.py prepare --variant B0 --require-clean  (then run it with the harness per HARNESS_README)")
    return code


if __name__ == "__main__":
    sys.exit(main())
