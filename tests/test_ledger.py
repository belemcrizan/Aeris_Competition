"""Evidence ledger, uncertainty levels, budget modes and retry limits."""

from __future__ import annotations

import json
import math

import pytest
from conftest import load_script

ledger = load_script("ledger", "ledger")


def run(capsys, *argv: str) -> str:
    assert ledger.main(list(argv)) == 0
    return capsys.readouterr().out


def test_entropy_values():
    assert ledger.entropy({"H1": 1.0}) == (0.0, 0.0)
    h, h_norm = ledger.entropy({"H1": 0.5, "H2": 0.5})
    assert h == pytest.approx(math.log(2))
    assert h_norm == pytest.approx(1.0)


@pytest.mark.parametrize(
    "used, mode",
    [(None, "NORMAL"), (0.0, "NORMAL"), (0.49, "NORMAL"), (0.5, "CONSERVATIVE"), (0.79, "CONSERVATIVE"), (0.8, "CRITICAL"), (1.2, "CRITICAL")],
)
def test_budget_mode_transitions(used, mode):
    assert ledger.budget_mode(used) == mode


def test_levels_and_actions(state_dir, capsys):
    out = run(capsys, "status")
    assert "UNCERTAINTY: HIGH" in out and "INVESTIGATE" in out

    run(capsys, "add", "H1", "--target", "pkg.a", "--weight", "0.5", "--claim", "a drops flag")
    run(capsys, "add", "H2", "--target", "pkg.b", "--weight", "0.5", "--claim", "b converts wrong")
    out = run(capsys, "status")
    assert "UNCERTAINTY: MEDIUM" in out and "DISCRIMINATE H1 vs H2" in out

    run(capsys, "update", "H1", "--weight", "0.9", "--for", "repro shows flag dropped in a")
    out = run(capsys, "status")
    assert "UNCERTAINTY: LOW" in out and "PATCH H1" in out


def test_low_requires_supporting_evidence(state_dir, capsys):
    run(capsys, "add", "H1", "--target", "pkg.a", "--weight", "1", "--claim", "x")
    out = run(capsys, "status")
    assert "UNCERTAINTY: MEDIUM" in out and "CONFIRM H1" in out


def test_budget_pressure_lowers_threshold(state_dir, capsys):
    run(capsys, "add", "H1", "--target", "a", "--weight", "0.55", "--claim", "x")
    run(capsys, "add", "H2", "--target", "b", "--weight", "0.45", "--claim", "y")
    run(capsys, "update", "H1", "--for", "evidence")
    assert "UNCERTAINTY: MEDIUM" in run(capsys, "status", "--budget-used", "0.1")
    assert "UNCERTAINTY: LOW" in run(capsys, "status", "--budget-used", "0.6")
    out = run(capsys, "status", "--budget-used", "0.9")
    assert "MODE: CRITICAL" in out and "PATCH H1 now" in out


def test_investigation_limit_forces_patch(state_dir, capsys):
    run(capsys, "add", "H1", "--target", "a", "--weight", "0.5", "--claim", "x")
    run(capsys, "add", "H2", "--target", "b", "--weight", "0.5", "--claim", "y")
    for i in range(ledger.MAX_INVESTIGATION_STEPS):
        run(capsys, "experiment", "--command", f"grep {i}", "--result", "nothing")
    assert "investigation limit reached" in run(capsys, "status")


def test_retry_limit_and_repeated_failures(state_dir, capsys):
    run(capsys, "add", "H1", "--target", "a", "--weight", "0.9", "--claim", "x")
    run(capsys, "update", "H1", "--for", "e")
    run(capsys, "patch", "--files", "a.py", "--hypothesis", "H1", "--result", "fail")
    run(capsys, "patch", "--files", "a.py", "--hypothesis", "H1", "--result", "fail")
    out = run(capsys, "status")
    assert "H1 has 2 failed patches" in out
    run(capsys, "patch", "--files", "b.py", "--hypothesis", "H1", "--result", "fail")
    assert f"{ledger.MAX_PATCH_ATTEMPTS} patch attempts reached the limit" in run(capsys, "status")


def test_passing_patch_recommends_submit(state_dir, capsys):
    run(capsys, "patch", "--files", "a.py", "--result", "pass")
    assert "SUBMIT: last patch passed" in run(capsys, "status")


def test_rejected_hypothesis_excluded(state_dir, capsys):
    run(capsys, "add", "H1", "--target", "a", "--weight", "0.9", "--claim", "x")
    run(capsys, "add", "H2", "--target", "b", "--weight", "0.1", "--claim", "y")
    run(capsys, "update", "H1", "--reject", "--against", "code path never reached")
    out = run(capsys, "status")
    assert "H1 [REJECTED]" in out and "top=H2 p=1.00" in out


def test_state_persists_and_is_compact(state_dir, capsys):
    run(capsys, "claim", "x" * 1000)
    state = json.loads((state_dir / "ledger.json").read_text())
    assert len(state["claims"][0]) == ledger.MAX_TEXT
    assert not (state_dir / "events.jsonl").exists()
    run(capsys, "add", "H1", "--target", "a", "--weight", "1", "--claim", "x")
    assert json.loads((state_dir / "events.jsonl").read_text().splitlines()[-1])["event_type"] == "hypothesis_created"


def test_single_string_argument_is_split(state_dir, capsys):
    assert ledger.main(['add H1 --target a --weight 0.3 --claim "two words"']) == 0
    assert "two words" in capsys.readouterr().out


def test_invalid_inputs(state_dir, capsys):
    assert ledger.main(["update", "H9", "--weight", "1"]) == 2
    assert ledger.main(["add", "H1", "--target", "a", "--weight", "-1", "--claim", "x"]) == 2
    assert ledger.main(["status", "--budget-used", "5"]) == 2


def test_corrupt_state_recovers(state_dir, capsys):
    state_dir.mkdir(parents=True)
    (state_dir / "ledger.json").write_text("{not json")
    assert ledger.main(["status"]) == 0
    assert (state_dir / "ledger.corrupt.json").exists()
