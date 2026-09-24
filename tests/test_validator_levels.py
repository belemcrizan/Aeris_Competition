"""Validator severity model: ERROR only for OFFICIAL/ADK rules, POLICY never an error."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_validation import minimal, write

from aeris_comp import validation as V
from aeris_comp.validation import CATALOG, validate_tree

SOURCE = Path(V.__file__).read_text(encoding="utf-8")


def test_every_emitted_code_is_catalogued():
    emitted = set(re.findall(r"\.(?:error|warn|info|add)\(\s*\"([A-Z][A-Z0-9_]+)\"", SOURCE))
    assert emitted, "no codes found; the regex no longer matches the source"
    assert emitted <= set(CATALOG), sorted(emitted - set(CATALOG))


def test_catalog_has_no_dead_codes():
    emitted = set(re.findall(r"\"([A-Z][A-Z0-9_]{3,})\"", SOURCE.split("CATALOG: dict", 1)[1].split("}\n", 1)[1]))
    assert set(CATALOG) <= emitted, sorted(set(CATALOG) - emitted)


def test_errors_have_official_or_adk_basis():
    for code, rule in CATALOG.items():
        if rule.level == V.ERROR:
            assert rule.basis in {V.OFFICIAL, V.ADK}, code
        if rule.basis in {V.POLICY, V.UNVERIFIED}:
            assert rule.level != V.ERROR, code


def test_blocking_rules_are_policy_warnings():
    for code, rule in CATALOG.items():
        if rule.blocking:
            assert (rule.level, rule.basis) == (V.WARNING, V.POLICY), code


def test_policy_blocker_fails_release_but_not_official(tmp_path):
    minimal(tmp_path)
    write(tmp_path, "prompts/extra.md", "token ghp_" + "a" * 36)
    report = validate_tree(tmp_path)
    assert report.ok
    assert not report.release_ok
    assert "RESULT: POLICY_BLOCKED" in report.format()


def test_unexpected_root_entry_is_info(tmp_path):
    minimal(tmp_path)
    write(tmp_path, "notes.txt", "hello")
    report = validate_tree(tmp_path)
    assert [i.code for i in report.infos] == ["UNEXPECTED_ROOT_ENTRY"]
    assert report.release_ok and not report.warnings


def test_empty_instruction_is_policy_warning(tmp_path):
    minimal(tmp_path, prompt="   \n")
    report = validate_tree(tmp_path)
    assert report.ok and "EMPTY_INSTRUCTION" in {i.code for i in report.warnings}


def skill(root: Path, dirname: str, frontmatter: str) -> None:
    write(root, f"skills/{dirname}/SKILL.md", f"---\n{frontmatter}---\nbody\n")


@pytest.mark.parametrize(
    "dirname, frontmatter, level, code",
    [
        ("good-skill", "name: good-skill\ndescription: ok\n", None, None),
        ("repo_nav", "name: repo_nav\ndescription: ok\n", V.WARNING, "SKILL_NAME_SNAKE_CASE"),
        ("Bad", "name: Bad\ndescription: ok\n", V.ERROR, "SKILL_NAME_FORMAT"),
        ("a--b", "name: a--b\ndescription: ok\n", V.ERROR, "SKILL_NAME_FORMAT"),
        ("mixed_a-b", "name: mixed_a-b\ndescription: ok\n", V.ERROR, "SKILL_NAME_FORMAT"),
        ("other", "name: x\ndescription: ok\n", V.ERROR, "SKILL_NAME_MISMATCH"),
        ("nodesc", "name: nodesc\n", V.ERROR, "SKILL_MISSING_DESCRIPTION"),
        ("longdesc", "name: longdesc\ndescription: " + "d" * 1025 + "\n", V.ERROR, "SKILL_FIELD_TOO_LONG"),
        ("extra", "name: extra\ndescription: ok\nversion: 2\n", V.WARNING, "SKILL_UNKNOWN_FRONTMATTER"),
    ],
)
def test_skill_rules_follow_adk(tmp_path, dirname, frontmatter, level, code):
    minimal(tmp_path)
    skill(tmp_path, dirname, frontmatter)
    report = validate_tree(tmp_path)
    if code is None:
        assert not report.issues, report.format()
    else:
        assert code in {i.code for i in report.issues if i.level == level}, report.format()


def test_unsupported_script_suffix_warns(tmp_path):
    minimal(tmp_path)
    skill(tmp_path, "tool", "name: tool\ndescription: ok\n")
    write(tmp_path, "skills/tool/scripts/run.js", "console.log(1)\n")
    assert "SKILL_UNSUPPORTED_SCRIPT" in validate_tree(tmp_path).codes()


@pytest.mark.parametrize(
    "dirname, frontmatter",
    [
        ("good-skill", "name: good-skill\ndescription: ok\n"),
        ("Bad", "name: Bad\ndescription: ok\n"),
        ("other", "name: x\ndescription: ok\n"),
        ("nodesc", "name: nodesc\n"),
    ],
)
def test_skill_errors_agree_with_adk(tmp_path, dirname, frontmatter):
    adk_utils = pytest.importorskip("google.adk.skills._utils", reason="google-adk not installed")
    minimal(tmp_path)
    skill(tmp_path, dirname, frontmatter)
    ours = not any(i.code.startswith("SKILL_") for i in validate_tree(tmp_path).errors)
    adk = not adk_utils._validate_skill_dir(tmp_path / "skills" / dirname)
    assert ours == adk
