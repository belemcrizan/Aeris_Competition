#!/usr/bin/env python3
"""Validate a submission directory or submission.zip against the competition rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from aeris_comp.validation import validate_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="submission.zip or an unpacked submission directory")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument(
        "--official-only",
        action="store_true",
        help="fail only on OFFICIAL/ADK errors, ignoring our blocking policy checks",
    )
    args = parser.parse_args(argv)
    report = validate_path(args.path)
    print(report.format())
    if args.official_only:
        return 0 if report.ok else 1
    if not report.release_ok or (args.strict and report.warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
