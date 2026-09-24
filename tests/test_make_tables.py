"""Paper table generator works on synthetic run directories and refuses to invent data."""

from __future__ import annotations

import importlib.util
import json

from conftest import REPO_ROOT

spec = importlib.util.spec_from_file_location("make_tables", REPO_ROOT / "scripts" / "make_tables.py")
make_tables = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_tables)


def run_dir(root, variant, statuses):
    d = root / variant
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"variant": variant, "submission_sha256": "ab" * 32}))
    lines = [json.dumps({"instance_id": f"t{i}", "status": s, **({"failure_category": "PATCH_FAILURE"} if s == "FAIL" else {})}) for i, s in enumerate(statuses)]
    (d / "records.jsonl").write_text("\n".join(lines) + "\n")
    return d


def test_tables_from_runs(tmp_path):
    b0 = run_dir(tmp_path, "B0", ["PASS", "FAIL", "FAIL", "FAIL"])
    full = run_dir(tmp_path, "FULL", ["PASS", "PASS", "PASS", "FAIL"])
    out = tmp_path / "tables"
    assert make_tables.main([str(b0), str(full), "--out", str(out)]) == 0
    main = (out / "main_results.md").read_text()
    assert "| B0 | 4 | 1 | 0.250 |" in main
    assert "| FULL | 4 | 3 | 0.750 |" in main and "+2 / -0" in main and "0.500" in main
    failures = (out / "failure_categories.md").read_text()
    assert "| PATCH_FAILURE | 3 | 1 |" in failures


def test_refuses_without_records(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert make_tables.main([str(tmp_path / "empty"), "--out", str(tmp_path / "t")]) == 1
    assert not (tmp_path / "t").exists()
