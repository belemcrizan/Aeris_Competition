"""Taxonomy, telemetry schema, localization/calibration metrics, data split, scorer agreement."""

from __future__ import annotations

import pytest

from aeris_comp import metrics as M
from aeris_comp import taxonomy as T
from aeris_comp import telemetry as E
from aeris_comp.split import make_split, repo_of, verify_split

REQUIRED_CATEGORIES = {
    "INFRASTRUCTURE_FAILURE", "CONFIG_FAILURE", "MODEL_LOAD_FAILURE", "TOOL_SCHEMA_FAILURE", "TOOL_MISUSE",
    "LOCALIZATION_FAILURE", "GRAPH_EXPLOSION", "CONTEXT_FAILURE", "ROOT_CAUSE_FAILURE", "PREMATURE_PATCH",
    "PATCH_FAILURE", "SYNTAX_REGRESSION", "BEHAVIOR_REGRESSION", "TEST_SELECTION_FAILURE", "REPEATED_FAILURE",
    "LOOPING", "OVER_EDITING", "UNDER_EDITING", "BUDGET_EXHAUSTION", "TIMEOUT", "NO_PATCH",
    "INVALID_SUBMISSION", "UNKNOWN",
}  # fmt: skip


# ----------------------------------------------------------------- taxonomy
def test_taxonomy_matches_required_list():
    assert set(T.FAILURE_CATEGORIES) == REQUIRED_CATEGORIES


def test_scorer_statuses_all_map_to_known_categories():
    for status, category in T.AUTOMATIC_CATEGORY.items():
        assert status in T.SCORER_STATUSES and category in T.FAILURE_CATEGORIES


def test_legacy_alias_and_secondary_labels():
    T.validate_labels("REGRESSION_FAILURE", ["LOOPING"])
    with pytest.raises(ValueError):
        T.validate_labels(None, ["LOOPING"])
    with pytest.raises(ValueError):
        T.validate_labels("LOOPING", ["LOOPING"])
    with pytest.raises(ValueError):
        T.validate_labels("MADE_UP")


def test_summary_counts_primary_secondary_and_families():
    summary = M.summarize(
        [
            {"instance_id": "a", "status": "PASS"},
            {"instance_id": "b", "status": "FAIL", "failure_category": "REGRESSION_FAILURE", "failure_secondary": ["LOOPING"]},
            {"instance_id": "c", "status": "NO_PATCH", "failure_category": "NO_PATCH"},
        ]
    )
    assert summary["failure_categories"] == {"BEHAVIOR_REGRESSION": 1, "NO_PATCH": 1}
    assert summary["failure_secondary"] == {"LOOPING": 1}
    assert summary["failure_families"] == {"patch": 1, "submission": 1}


# ---------------------------------------------------------------- telemetry
def test_make_event_has_exact_fields():
    event = E.make_event("test_result", task_id="t", variant="B0", duration=1.5, tool="skill:testing", success=False)
    assert tuple(event) == E.FIELDS
    assert set(E.EVENT_SOURCES) == set(E.EVENT_TYPES) and len(E.EVENT_TYPES) == 20


@pytest.mark.parametrize(
    "patch",
    [{"event_type": "nope"}, {"duration": -1}, {"success": "yes"}, {"metadata": []}, {"timestamp": "now"}, {"extra": 1}],
)
def test_invalid_events_rejected(patch):
    event = E.make_event("review")
    event.update(patch)
    with pytest.raises(E.TelemetryError):
        E.validate_event(event)


def test_read_events_fills_ids_and_reports_line(tmp_path):
    path = tmp_path / "events.jsonl"
    E.write_events([E.make_event("review")], path)
    assert E.read_events(path, task_id="t1", variant="B0")[0]["task_id"] == "t1"
    path.write_text(path.read_text() + "{bad json\n")
    with pytest.raises(E.TelemetryError, match=":2:"):
        E.read_events(path)


def ev(event_type, **metadata):
    return E.make_event(event_type, metadata=metadata)


def test_suggest_labels_rules():
    repeated = [ev("test_result"), *[ev("failure_signature", signature="s1") for _ in range(3)]]
    assert "REPEATED_FAILURE" in E.suggest_labels(repeated)
    assert "PREMATURE_PATCH" in E.suggest_labels([ev("hypothesis_created"), ev("patch_attempt")])
    assert "PREMATURE_PATCH" not in E.suggest_labels([ev("test_result"), ev("patch_attempt")])
    assert "GRAPH_EXPLOSION" in E.suggest_labels([ev("graph_expansion")] * 16)
    assert "NO_PATCH" in E.suggest_labels([ev("task_start"), ev("task_end")], "NO_PATCH")
    assert "BUDGET_EXHAUSTION" in E.suggest_labels([ev("budget_status", mode="CRITICAL", budget_used=0.97)], "FAIL")
    assert "BUDGET_EXHAUSTION" not in E.suggest_labels([ev("budget_status", mode="CRITICAL", budget_used=0.85)], "FAIL")
    assert E.suggest_labels([]) == []


# ------------------------------------------------------------- localization
def test_localization_metrics():
    tasks = [
        {"ranked": ["a.py", "b.py", "c.py"], "gold": ["b.py"]},
        {"ranked": ["x.py", "x.py", "y.py"], "gold": ["y.py", "z.py"]},
        {"ranked": ["q.py"], "gold": []},
    ]
    out = M.localization_metrics(tasks, ks=(1, 2))
    assert out["n_tasks"] == 2
    assert out["mrr"] == pytest.approx((1 / 2 + 1 / 2) / 2)
    assert out["hit@1"] == 0.0 and out["hit@2"] == 1.0
    assert out["recall@2"] == pytest.approx((1.0 + 0.5) / 2)


# -------------------------------------------------------------- calibration
def test_calibration_perfect_and_uninformative():
    assert M.auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert M.auroc([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == 0.5
    assert M.auroc([0.3, 0.7], [1, 1]) is None
    assert M.brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert M.expected_calibration_error([0.8] * 10, [1] * 8 + [0] * 2) == pytest.approx(0.0)
    assert M.expected_calibration_error([0.9] * 10, [1] * 5 + [0] * 5) == pytest.approx(0.4)


def test_calibration_report_signal_decision():
    strong = M.calibration_report([0.9] * 30 + [0.1] * 30, [1] * 30 + [0] * 30)
    assert strong["confidence_has_signal"] and strong["auroc"] == 1.0
    weak = M.calibration_report([0.6, 0.4, 0.6, 0.4], [1, 1, 0, 0])
    assert not weak["confidence_has_signal"]
    assert sum(b["n"] for b in weak["reliability"]) == 4


def test_calibration_input_checks():
    with pytest.raises(ValueError):
        M.brier_score([1.2], [1])
    with pytest.raises(ValueError):
        M.brier_score([0.5], [2])


# -------------------------------------------------------------------- split
def tasks_fixture():
    tasks = [{"instance_id": f"tiangolo__fastapi-{i}"} for i in range(40)]
    tasks += [{"instance_id": f"encode__httpx-{i}"} for i in range(10)]
    tasks += [{"instance_id": "solo__repo-1"}]
    return tasks


def test_split_is_deterministic_stratified_and_disjoint():
    tasks = tasks_fixture()
    a = make_split(tasks)
    b = make_split(list(reversed(tasks)))
    assert a == b
    assert a["per_repo"]["tiangolo__fastapi"] == {"total": 40, "dev": 28, "heldout": 12}
    assert a["per_repo"]["encode__httpx"] == {"total": 10, "dev": 7, "heldout": 3}
    assert not set(a["dev"]) & set(a["heldout"])
    assert len(a["dev"]) + len(a["heldout"]) == len(tasks)
    assert verify_split(a, tasks) == []
    assert make_split(tasks, seed=1)["dev"] != a["dev"]


def test_split_verification_detects_tampering():
    tasks = tasks_fixture()
    split = make_split(tasks)
    moved = split["heldout"].pop()
    split["dev"] = sorted(split["dev"] + [moved])
    problems = verify_split(split, tasks)
    assert any("split_sha256" in p for p in problems)
    assert verify_split(make_split(tasks), tasks[:-1])


def test_repo_of():
    assert repo_of({"instance_id": "psf__requests-6028"}) == "psf__requests"
    assert repo_of({"instance_id": "x", "repo": "encode/httpx"}) == "encode/httpx"


def test_split_rejects_duplicates():
    with pytest.raises(ValueError):
        make_split([{"instance_id": "a-1"}, {"instance_id": "a-1"}])


# ---------------------------------------------------------- scorer fidelity
def test_scorer_agreement():
    ours = [{"instance_id": i, "status": s} for i, s in [("a", "PASS"), ("b", "FAIL"), ("c", "PASS"), ("d", "PASS")]]
    official = [{"instance_id": i, "status": s} for i, s in [("a", "PASS"), ("b", "PASS"), ("c", "FAIL"), ("e", "FAIL")]]
    out = M.scorer_agreement(ours, official)
    assert out["n_shared"] == 3 and out["agreement"] == pytest.approx(1 / 3)
    assert out["we_pass_official_fails"] == ["c"] and out["we_fail_official_passes"] == ["b"]
    assert out["only_ours"] == ["d"] and out["only_official"] == ["e"]
