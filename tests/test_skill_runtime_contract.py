"""Skill scripts vs. the ADK run_skill_script contract and the telemetry schema.

ADK 2.9.2 (google/adk/tools/skill_toolset.py) builds argv as
``[file_path, --k v ..., -k v ..., "--", positional ...]`` for dict ``args`` and passes a
list ``args`` through unchanged; the code executor also chdirs into a temp directory.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import SKILLS, load_script, make_repo

from aeris_comp.telemetry import EVENT_TYPES, read_events

ledger = load_script("ledger", "ledger")
run_tests = load_script("testing", "run_tests")
review = load_script("review", "review_diff")
locate = load_script("navigation", "locate_symbol")
find_tests = load_script("navigation", "find_tests")


def adk_argv(args=None, short_options=None, positional_args=None) -> list[str]:
    """Documented ADK layout, minus argv[0]."""
    if isinstance(args, list):
        return [str(a) for a in args]
    out: list[str] = []
    for k, v in (args or {}).items():
        out += [f"--{k}", str(v)]
    for k, v in (short_options or {}).items():
        out += [f"-{k}", str(v)]
    if positional_args:
        out += ["--", *map(str, positional_args)]
    return out


def events(state_dir: Path) -> list[dict]:
    return read_events(state_dir / "events.jsonl")


def test_ledger_accepts_adk_dict_args(state_dir, capsys):
    argv = adk_argv({"target": "pkg.mod.f", "weight": 0.6, "claim": "off by one"}, positional_args=["add", "H1"])
    assert argv[0] == "--target" and "--" in argv
    assert ledger.main(argv) == 0
    assert ledger.main(adk_argv({"budget-used": 0.3}, positional_args=["status"])) == 0
    out = capsys.readouterr().out
    assert "H1" in out and "MODE: NORMAL" in out


def test_ledger_accepts_adk_list_args(state_dir, capsys):
    assert ledger.main(adk_argv(["claim", "-- literal text"])) == 0
    assert ledger.main(adk_argv(["add", "H1", "--target", "a", "--weight", "1", "--claim", "x"])) == 0
    assert "H1" in capsys.readouterr().out


def test_navigation_accepts_adk_dict_args(tmp_path, capsys):
    repo = make_repo(tmp_path / "repo", {"pkg/__init__.py": "", "pkg/mod.py": "def f():\n    return 1\n", "tests/test_mod.py": "from pkg.mod import f\n"})
    assert locate.main(adk_argv({"repo": repo}, positional_args=["pkg.mod.f"])) == 0
    assert "pkg/mod.py" in capsys.readouterr().out
    assert find_tests.main(adk_argv({"repo": repo}, positional_args=["pkg.mod"])) == 0
    assert "tests/test_mod.py" in capsys.readouterr().out


def test_review_and_tests_accept_adk_dict_args(tmp_path, capsys):
    repo = make_repo(tmp_path / "repo", {"pkg/a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    assert True\n"})
    assert review.main(adk_argv({"repo": repo})) == 0
    assert "EMPTY_DIFF" in capsys.readouterr().out
    assert run_tests.main(adk_argv({"repo": repo, "timeout": 120}, positional_args=["tests/test_a.py"])) == 0
    assert "RESULT: PASS" in capsys.readouterr().out


def test_review_flags_materialized_skill_copies(tmp_path, capsys):
    repo = make_repo(tmp_path / "repo", {"pkg/a.py": "x = 1\n"})
    copy = repo / "skills" / "ledger" / "scripts" / "ledger.py"
    copy.parent.mkdir(parents=True)
    copy.write_text("print(1)\n", newline="\n")
    (repo / "skills" / "ledger" / "SKILL.md").write_text("---\nname: ledger\n---\n", newline="\n")
    assert review.main(["--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "MATERIALIZED_SKILL_FILE skills/ledger/scripts/ledger.py" in out
    assert "MATERIALIZED_SKILL_FILE skills/ledger/SKILL.md" in out


def test_tracked_repo_skills_dir_is_not_flagged(tmp_path, capsys):
    repo = make_repo(tmp_path / "repo", {"skills/review/SKILL.md": "project file\n"})
    (repo / "skills" / "review" / "SKILL.md").write_text("project file, edited\n", newline="\n")
    assert review.main(["--repo", str(repo)]) == 0
    assert "MATERIALIZED_SKILL_FILE" not in capsys.readouterr().out


def test_skill_events_follow_schema(tmp_path, state_dir, capsys):
    repo = make_repo(
        tmp_path / "repo",
        {"pkg/__init__.py": "", "pkg/calc.py": "def add(a, b):\n    return a - b\n", "tests/test_calc.py": "from pkg.calc import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"},
    )
    ledger.main(["add", "H1", "--target", "pkg.calc.add", "--weight", "0.7", "--claim", "sign error"])
    ledger.main(["update", "H1", "--for", "test fails with 0"])
    ledger.main(["status", "--budget-used", "0.2"])
    for _ in range(2):
        run_tests.main(["--repo", str(repo), "tests/test_calc.py"])
    ledger.main(["patch", "--files", "pkg/calc.py", "--hypothesis", "H1", "--result", "fail"])
    review.main(["--repo", str(repo)])
    capsys.readouterr()
    got = events(state_dir)
    types = [e["event_type"] for e in got]
    assert set(types) <= set(EVENT_TYPES)
    for expected in ("hypothesis_created", "hypothesis_updated", "uncertainty_state", "budget_status", "test_start", "test_result", "failure_signature", "retry", "patch_attempt", "review"):
        assert expected in types, expected
    patch = next(e for e in got if e["event_type"] == "patch_attempt")
    assert patch["success"] is False and patch["metadata"]["files"] == ["pkg/calc.py"]
    budget = next(e for e in got if e["event_type"] == "budget_status")
    assert budget["metadata"] == {"mode": "NORMAL", "budget_used": 0.2}


def test_events_pick_up_task_and_variant_from_env(state_dir, monkeypatch, capsys):
    monkeypatch.setenv("AERIS_TASK_ID", "demo__repo-1")
    monkeypatch.setenv("AERIS_VARIANT", "FULL")
    ledger.main(["claim", "x"])
    ledger.main(["status"])
    capsys.readouterr()
    assert {(e["task_id"], e["variant"]) for e in events(state_dir)} == {("demo__repo-1", "FULL")}


# ------------------------------------------------ real ADK wrapper (optional)
def adk_wrapper(skill_name: str, file_path: str, args=None, positional_args=None) -> str:
    utils = pytest.importorskip("google.adk.skills._utils", reason="google-adk not installed")
    toolset = pytest.importorskip("google.adk.tools.skill_toolset")
    skill = utils._load_skill_from_dir(SKILLS / skill_name)
    executor = toolset._SkillScriptCodeExecutor(base_executor=None, script_timeout=60)
    return executor._build_wrapper_code(skill, file_path, args, None, positional_args)


def test_adk_builds_the_argv_we_expect():
    code = adk_wrapper("ledger", "scripts/ledger.py", {"weight": 0.5}, ["update", "H1"])
    argv = ast.literal_eval(re.search(r"sys\.argv = (\[.*?\])\n", code).group(1))
    assert argv == ["scripts/ledger.py", "--weight", "0.5", "--", "update", "H1"]


def test_ledger_runs_inside_real_adk_wrapper(tmp_path, state_dir):
    code = adk_wrapper("ledger", "scripts/ledger.py", {"target": "a.b", "weight": 0.9, "claim": "why"}, ["add", "H1"])
    proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "H1" in proc.stdout
    assert json.loads((state_dir / "ledger.json").read_text())["hypotheses"]["H1"]["weight"] == 0.9


def test_review_inside_real_adk_wrapper_finds_repo_despite_temp_cwd(tmp_path):
    repo = make_repo(tmp_path / "repo", {"pkg/a.py": "x = 1\n"})
    (repo / "pkg" / "a.py").write_text("x = 2\n", newline="\n")
    code = adk_wrapper("review", "scripts/review_diff.py", {"repo": repo.as_posix()})
    proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "M pkg/a.py" in proc.stdout
