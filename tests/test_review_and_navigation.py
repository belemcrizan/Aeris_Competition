"""Diff review flags and symbol/test navigation."""

from __future__ import annotations

from conftest import load_script, make_repo

review = load_script("review", "review_diff")
locate = load_script("navigation", "locate_symbol")
find_tests = load_script("navigation", "find_tests")

SOURCE = """\
import os


class Router:
    prefix = "/"

    def add(self, path):
        if path:
            return self._norm(path)
        return None

    def _norm(self, path):
        return path.strip("/")


async def serve(app):
    return app
"""


def test_review_flags(tmp_path, capsys):
    repo = make_repo(tmp_path / "repo", {"pkg/router.py": SOURCE, "tests/test_router.py": "def test_x():\n    pass\n"})
    (repo / "pkg" / "router.py").write_text(SOURCE.replace("return None", "print('debug')\n        return None"), newline="\n")
    (repo / "tests" / "test_router.py").write_text("def test_x():\n    assert True\n", newline="\n")
    (repo / "repro.py").write_text("import pkg\n")
    assert review.main(["--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "DEBUG_STATEMENT pkg/router.py" in out
    assert "TEST_FILE_CHANGED tests/test_router.py" in out
    assert "SCRATCH_FILE repro.py" in out
    assert "repro.py (untracked, will be included by submit_patch)" in out
    assert "VERDICT: REVIEW" in out


def test_review_clean_and_empty(tmp_path, capsys):
    repo = make_repo(tmp_path / "repo", {"pkg/router.py": SOURCE})
    assert review.main(["--repo", str(repo)]) == 0
    assert "EMPTY_DIFF" in capsys.readouterr().out
    target = repo / "pkg" / "router.py"
    target.write_text(SOURCE.replace('strip("/")', 'strip("/ ")'), newline="\n")
    assert review.main(["--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "VERDICT: OK" in out and "+1 -1" in out

    target.write_bytes(SOURCE.replace("\n", "\r\n").encode())
    assert review.main(["--repo", str(repo)]) == 0
    assert "LINE_ENDINGS_CHANGED pkg/router.py" in capsys.readouterr().out


def test_review_whitespace_only():
    files = review.parse_diff("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@\n-a = 1\n+a =  1\n+\n")
    files["x.py"]["added"] = ["    a = 1"]
    files["x.py"]["removed"] = ["a = 1"]
    assert any(code == "WHITESPACE_ONLY" for code, _, _ in review.analyze(files, {}))


def test_locate_nested_symbols(tmp_path):
    repo = make_repo(tmp_path / "repo", {"src/pkg/__init__.py": "", "src/pkg/router.py": SOURCE})
    assert locate.locate(repo, "pkg.router.Router.add") == ["pkg.router.Router.add -> src/pkg/router.py:7-10  def add(self, path):"]
    assert locate.locate(repo, "pkg.router.serve")[0].startswith("pkg.router.serve -> src/pkg/router.py:16-17")
    assert "src/pkg/router.py:5-5" in locate.locate(repo, "pkg.router.Router.prefix")[0]
    assert locate.locate(repo, "pkg.router") == ["pkg.router -> src/pkg/router.py (module)"]


def test_locate_fallback_and_missing(tmp_path):
    repo = make_repo(tmp_path / "repo", {"pkg/router.py": SOURCE})
    lines = locate.locate(repo, "other.module._norm")
    assert "module not found" in lines[0] and "pkg/router.py:12-13" in lines[1]
    assert "NOT FOUND" in locate.locate(repo, "nothing.here.zzz")[0]


def test_find_tests_ranking(tmp_path, capsys):
    repo = make_repo(
        tmp_path / "repo",
        {
            "pkg/router.py": SOURCE,
            "tests/test_router.py": "from pkg.router import Router\n\ndef test_add():\n    Router().add('x')\n",
            "tests/test_other.py": "def test_other():\n    pass\n",
            "tests/test_misc.py": "import pkg\n# Router mentioned\n",
        },
    )
    ranked = find_tests.rank(repo, ["pkg/router.py", "Router"])
    assert ranked[0][1] == "tests/test_router.py"
    assert all(rel != "tests/test_other.py" for _, rel, _ in ranked)
    assert find_tests.main(["--repo", str(repo), "pkg.router.Router"]) == 0
    assert "SUGGESTED: python -m pytest -x -q tests/test_router.py" in capsys.readouterr().out
