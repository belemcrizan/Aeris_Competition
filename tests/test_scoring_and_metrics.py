"""Local scorer on a synthetic task and metric aggregation."""

from __future__ import annotations

import tarfile

import pytest
from conftest import make_repo

from aeris_comp import scoring
from aeris_comp.metrics import paired_comparison, summarize, wilson_interval

FIX = """\
diff --git a/pkg/calc.py b/pkg/calc.py
--- a/pkg/calc.py
+++ b/pkg/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""

TEST_PATCH = """\
diff --git a/tests/test_calc.py b/tests/test_calc.py
new file mode 100644
--- /dev/null
+++ b/tests/test_calc.py
@@ -0,0 +1,5 @@
+from pkg.calc import add
+
+
+def test_add():
+    assert add(2, 2) == 4
"""


@pytest.fixture
def task(tmp_path):
    repo = make_repo(
        tmp_path / "calc_1",
        {"pkg/__init__.py": "", "pkg/calc.py": "def add(a, b):\n    return a - b\n", "tests/__init__.py": ""},
    )
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    with tarfile.open(snapshots / "calc_1.tgz", "w:gz") as tar:
        tar.add(repo, arcname="calc_1")
    return {"instance_id": "calc_1", "patch": FIX, "test_patch": TEST_PATCH}, snapshots


def test_reference_fix_passes(task):
    t, snapshots = task
    result = scoring.score_task(t, t["patch"], snapshots)
    assert result.status == "PASS", result.detail
    assert result.files_changed == ["pkg/calc.py"] and result.lines_added == 1 and result.lines_removed == 1
    assert result.test_files == ["tests/test_calc.py"]


def test_failure_modes(task):
    t, snapshots = task
    assert scoring.score_task(t, None, snapshots).status == "NO_PATCH"
    assert scoring.score_task(t, "NO_PATCH", snapshots).failure_category == "NO_PATCH"
    assert scoring.score_task(t, FIX.replace("a + b", "a + b + 1"), snapshots).status == "FAIL"
    bogus = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-x\n+y\n"
    assert scoring.score_task(t, bogus, snapshots).status == "APPLY_FAILED"
    result = scoring.score_task(t, FIX + TEST_PATCH.replace("add(2, 2) == 4", "True"), snapshots)
    assert result.status == "TEST_PATCH_CONFLICT" and result.failure_category == "OVER_EDITING"
    assert scoring.score_task({**t, "instance_id": "missing"}, FIX, snapshots).status == "MISSING_SNAPSHOT"


def test_patch_helpers():
    assert scoring.diff_stats(FIX) == (["pkg/calc.py"], 1, 1)
    assert scoring.test_files_from_patch(TEST_PATCH) == ["tests/test_calc.py"]


def test_summarize_and_categories():
    records = [
        {"instance_id": "a", "status": "PASS", "wall_time_s": 10, "lines_added": 2, "lines_removed": 1, "files_changed": ["x.py"]},
        {"instance_id": "b", "status": "FAIL", "failure_category": "LOCALIZATION_FAILURE", "wall_time_s": 30},
        {"instance_id": "c", "status": "NO_PATCH", "failure_category": "INVALID_SUBMISSION"},
        {"instance_id": "d", "status": "FAIL"},
    ]
    summary = summarize(records)
    assert summary["pass_rate"] == 0.25
    assert summary["failure_categories"] == {"INVALID_SUBMISSION": 1, "LOCALIZATION_FAILURE": 1, "UNLABELED": 1}
    assert summary["secondary"]["wall_time_s"]["mean"] == 20
    assert summary["secondary"]["changed_loc"]["n"] == 1
    with pytest.raises(ValueError):
        summarize([{"instance_id": "e", "status": "FAIL", "failure_category": "MADE_UP"}])


def test_wilson_and_paired_comparison():
    lo, hi = wilson_interval(5, 10)
    assert 0.2 < lo < 0.5 < hi < 0.8
    a = [{"instance_id": str(i), "status": "PASS" if i < 8 else "FAIL"} for i in range(10)]
    b = [{"instance_id": str(i), "status": "PASS" if i < 2 else "FAIL"} for i in range(10)]
    cmp = paired_comparison(a, b)
    assert cmp["n_shared"] == 10 and len(cmp["only_a_pass"]) == 6 and cmp["only_b_pass"] == []
    assert cmp["mcnemar_exact_p"] == pytest.approx(2 / 64)
    assert paired_comparison(a, a)["mcnemar_exact_p"] == 1.0
