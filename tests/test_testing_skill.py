"""Pytest output parsing, failure signatures and repeat detection."""

from __future__ import annotations

from conftest import git, load_script, make_repo

run_tests = load_script("testing", "run_tests")

FAIL_OUTPUT = """\
F.                                                                       [100%]
=================================== FAILURES ===================================
_______________________________ test_exclude ___________________________________
tests/test_api.py:12: in test_exclude
    assert serialize({"a": 1}, exclude_unset=True) == {}
pkg/api.py:40: in serialize
    return _dump(obj)
E   AssertionError: assert {'a': 1} == {}
E     Left contains 1 more item:
=========================== short test summary info ============================
FAILED tests/test_api.py::test_exclude - AssertionError: assert {'a': 1} == {}
1 failed, 1 passed in 0.05s
"""

COLLECTION_OUTPUT = """\
==================================== ERRORS ====================================
______________________ ERROR collecting tests/test_api.py ______________________
ImportError while importing test module '/workspace/tests/test_api.py'.
E   ModuleNotFoundError: No module named 'pkg.missing'
=========================== short test summary info ============================
ERROR tests/test_api.py
1 error in 0.10s
"""


def test_parse_failure():
    parsed = run_tests.parse_pytest_output(FAIL_OUTPUT)
    assert parsed["status"] == "FAIL"
    assert parsed["counts"] == {"passed": 1, "failed": 1, "errors": 0, "skipped": 0}
    assert parsed["failures"][0]["test"] == "tests/test_api.py::test_exclude"
    assert parsed["failures"][0]["exception"] == "AssertionError"
    assert parsed["comparisons"][0] == {"left": "{'a': 1}", "op": "==", "right": "{}"}
    assert "pkg/api.py:40 serialize" in parsed["frames"]


def test_parse_collection_error_and_pass():
    parsed = run_tests.parse_pytest_output(COLLECTION_OUTPUT)
    assert parsed["status"] == "COLLECTION_ERROR"
    assert parsed["counts"]["errors"] == 1
    assert run_tests.parse_pytest_output("..\n2 passed in 0.01s\n")["status"] == "PASS"
    assert run_tests.parse_pytest_output("\nno tests ran in 0.01s\n")["status"] == "NO_TESTS"


def test_signature_ignores_volatile_tokens():
    a = run_tests.parse_pytest_output(FAIL_OUTPUT)
    b = run_tests.parse_pytest_output(FAIL_OUTPUT.replace("{'a': 1}", "{'a': 2}").replace("0.05s", "9.99s"))
    assert run_tests.signature(a) == run_tests.signature(b)
    c = run_tests.parse_pytest_output(FAIL_OUTPUT.replace("AssertionError", "KeyError"))
    assert run_tests.signature(a) != run_tests.signature(c)


def test_repeated_signature_detection(state_dir):
    assert run_tests.record_history("tests/x.py", "abc", "FAIL") == 1
    assert run_tests.record_history("tests/x.py", "abc", "FAIL") == 2
    assert run_tests.record_history("tests/y.py", "abc", "FAIL") == 1


def test_split_args_single_string(tmp_path):
    timeout, repo, rest = run_tests.split_args([f"--timeout 5 --repo {tmp_path.as_posix()} tests/a.py -k 'x or y'"])
    assert timeout == 5 and repo == tmp_path and rest == ["tests/a.py", "-k", "x or y"]


def test_real_pytest_run_leaves_repo_clean(tmp_path, state_dir, capsys):
    repo = make_repo(
        tmp_path / "repo",
        {
            "pkg/__init__.py": "",
            "pkg/calc.py": "def add(a, b):\n    return a - b\n",
            "tests/test_calc.py": "from pkg.calc import add\n\ndef test_add():\n    assert add(2, 2) == 4\n",
        },
    )
    argv = ["--repo", str(repo), "tests/test_calc.py"]
    assert run_tests.main(argv) == 0
    first = capsys.readouterr().out
    assert "RESULT: FAIL" in first and "tests/test_calc.py::test_add" in first and "new" in first
    assert run_tests.main(argv) == 0
    assert "REPEATED" in capsys.readouterr().out

    (repo / "pkg" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    assert run_tests.main(argv) == 0
    assert "RESULT: PASS" in capsys.readouterr().out

    status = git(repo, "status", "--porcelain", "--untracked-files=all")
    assert status.strip() == "M pkg/calc.py", status
