#!/usr/bin/env python3
"""Validate a submission with google-adk's own AgentConfig model and skill loader."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from aeris_comp.adk_conformance import check_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="submission.zip or an unpacked submission directory")
    parser.add_argument("--out", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)
    report = check_path(args.path)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return {"PASS": 0, "FAIL": 1}.get(report["status"], 3)


if __name__ == "__main__":
    sys.exit(main())
