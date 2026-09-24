"""ADK (authority level 6) accepts every built variant; skipped without google-adk."""

from __future__ import annotations

import pytest
from conftest import REPO_ROOT

from aeris_comp import adk_conformance as A

pytest.importorskip("google.adk", reason="google-adk not installed (pip install google-adk==2.9.2)")


def test_source_submission_passes_adk():
    report = A.check_path(REPO_ROOT / "submission")
    assert report["status"] == "PASS", report
    assert {s["skill"] for s in report["skills"]} == {"ledger", "navigation", "review", "testing"}


def test_adk_rejects_unknown_agent_field(tmp_path):
    (tmp_path / "agent.yaml").write_text("name: root\nmodel: m\ninstruction: hi\ntemprature: 1\n", encoding="utf-8")
    report = A.check_tree(tmp_path)
    assert report["status"] == "FAIL"
    assert any("temprature" in e for e in report["agents"][0]["errors"])


def test_adapter_is_reported_as_competition_extension(tmp_path):
    (tmp_path / "agent.yaml").write_text("name: root\nmodel: m\ninstruction: hi\nadapter: main\n", encoding="utf-8")
    report = A.check_tree(tmp_path)
    assert report["status"] == "PASS"
    assert report["agents"][0]["extensions"] == {"adapter": "main"}


def test_adk_rejects_bad_skill(tmp_path):
    (tmp_path / "agent.yaml").write_text("name: root\nmodel: m\ninstruction: hi\n", encoding="utf-8")
    skill = tmp_path / "skills" / "Bad_Name"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: Bad_Name\n---\nbody\n", encoding="utf-8")
    report = A.check_tree(tmp_path)
    assert report["status"] == "FAIL" and report["skills"][0]["problems"]
