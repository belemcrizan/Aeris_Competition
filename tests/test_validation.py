"""Validator behaviour on well-formed and malformed submissions."""

from __future__ import annotations

import json
import os
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from aeris_comp.validation import validate_tree, validate_zip

MODEL = "gemma-4-31b-it-qat-w4a16-ct"


def write(root: Path, rel: str, content: str | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def minimal(root: Path, agent_extra: str = "", prompt: str = "Fix the issue.\n") -> Path:
    write(
        root,
        "agent.yaml",
        f"name: root\nmodel: {MODEL}\ninstruction: !include prompts/system.md\ntools:\n  - name: run_command\n  - name: submit_patch\n{agent_extra}",
    )
    write(root, "prompts/system.md", prompt)
    return root


def safetensors_bytes() -> bytes:
    header = json.dumps({"__metadata__": {"format": "pt"}}).encode()
    return struct.pack("<Q", len(header)) + header


def test_minimal_submission_is_valid(tmp_path):
    report = validate_tree(minimal(tmp_path))
    assert report.ok, report.format()
    assert report.tools == {"run_command", "submit_patch"}


def test_missing_agent_yaml(tmp_path):
    write(tmp_path, "prompts/system.md", "x")
    assert "MISSING_AGENT_YAML" in validate_tree(tmp_path).codes()


def test_unsupported_model(tmp_path):
    minimal(tmp_path)
    write(tmp_path, "agent.yaml", "name: root\nmodel: gemini-3.5-flash\ninstruction: hi\n")
    report = validate_tree(tmp_path)
    assert not report.ok and "UNSUPPORTED_MODEL" in report.codes()


def test_missing_model(tmp_path):
    write(tmp_path, "agent.yaml", "name: root\ninstruction: hi\n")
    assert "MISSING_MODEL" in validate_tree(tmp_path).codes()


def test_unknown_tool_and_python_tool(tmp_path):
    minimal(tmp_path, "  - name: google_search\n  - name: my_pkg.my_tool\n")
    report = validate_tree(tmp_path)
    assert [i.code for i in report.errors].count("UNKNOWN_TOOL") == 2


def test_callbacks_rejected(tmp_path):
    minimal(tmp_path, "before_model_callbacks:\n  - name: pkg.cb\n")
    assert "CODE_REFERENCE" in validate_tree(tmp_path).codes()


def test_unknown_field_rejected(tmp_path):
    minimal(tmp_path, "temperature: 0.2\n")
    assert "UNKNOWN_FIELD" in validate_tree(tmp_path).codes()


def test_duplicate_yaml_key_is_policy_warning(tmp_path):
    # PyYAML (and so ADK) silently keeps the last value, so this is not officially invalid.
    minimal(tmp_path, f"model: {MODEL}\n")
    report = validate_tree(tmp_path)
    assert "DUPLICATE_KEY" in {i.code for i in report.warnings}
    assert report.ok and report.release_ok


@pytest.mark.parametrize(
    "include, code",
    [
        ("../outside.md", "PATH_TRAVERSAL"),
        ("/etc/passwd", "ABSOLUTE_PATH"),
        ("prompts/missing.md", "MISSING_INCLUDE"),
        ("prompts\\system.md", "BACKSLASH_PATH"),
    ],
)
def test_malformed_includes(tmp_path, include, code):
    root = tmp_path / "sub"
    minimal(root)
    write(tmp_path, "outside.md", "secret prompt")
    write(root, "agent.yaml", f"name: root\nmodel: {MODEL}\ninstruction: !include {include}\n")
    report = validate_tree(root)
    assert code in report.codes(), report.format()
    assert not report.ok


def test_include_relative_to_containing_file(tmp_path):
    minimal(tmp_path, "sub_agents:\n  - config_path: sub_agents/helper.yaml\n")
    write(tmp_path, "sub_agents/helper.yaml", f"name: helper\nmodel: {MODEL}\ninstruction: !include ../prompts/helper.md\n")
    write(tmp_path, "prompts/helper.md", "Help.")
    report = validate_tree(tmp_path)
    assert report.ok, report.format()
    assert report.agents == ["agent.yaml", "sub_agents/helper.yaml"]


def test_symlink_include_rejected(tmp_path):
    minimal(tmp_path)
    target = tmp_path / "prompts" / "system.md"
    link = tmp_path / "prompts" / "link.md"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")
    write(tmp_path, "agent.yaml", f"name: root\nmodel: {MODEL}\ninstruction: !include prompts/link.md\n")
    assert "SYMLINK" in validate_tree(tmp_path).codes()


def test_sub_agent_missing_and_wrong_model(tmp_path):
    minimal(tmp_path, "sub_agents:\n  - config_path: sub_agents/missing.yaml\n  - config_path: sub_agents/bad.yaml\n")
    write(tmp_path, "sub_agents/bad.yaml", "name: bad\nmodel: gemma-3-27b\ninstruction: x\n")
    codes = [i.code for i in validate_tree(tmp_path).errors]
    assert "MISSING_INCLUDE" in codes and "UNSUPPORTED_MODEL" in codes


def test_agent_tool_resolves_and_validates(tmp_path):
    minimal(tmp_path, "  - name: AgentTool\n    args:\n      agent: sub_agents/analyzer.yaml\n")
    write(tmp_path, "sub_agents/analyzer.yaml", f"name: analyzer\nmodel: {MODEL}\ninstruction: Analyze.\ntools:\n  - name: read_file\n")
    report = validate_tree(tmp_path)
    assert report.ok, report.format()
    assert "sub_agents/analyzer.yaml" in report.agents


def test_adapter_reference_validation(tmp_path):
    minimal(tmp_path, "adapter: main_lora\n")
    assert "MISSING_ADAPTER" in validate_tree(tmp_path).codes()
    write(tmp_path, "adapters/main_lora/adapter_config.json", json.dumps({"base_model_name_or_path": "google/gemma-4-31B-it", "peft_type": "LORA"}))
    assert "ADAPTER_MISSING_FILE" in validate_tree(tmp_path).codes()
    write(tmp_path, "adapters/main_lora/adapter_model.safetensors", b"not a safetensors file")
    assert "ADAPTER_BAD_SAFETENSORS" in validate_tree(tmp_path).codes()
    write(tmp_path, "adapters/main_lora/adapter_model.safetensors", safetensors_bytes())
    report = validate_tree(tmp_path)
    assert report.ok, report.format()


def test_adapter_name_traversal(tmp_path):
    minimal(tmp_path, "adapter: ../evil\n")
    assert "BAD_ADAPTER_NAME" in validate_tree(tmp_path).codes()


def test_unreferenced_adapter_warns(tmp_path):
    minimal(tmp_path)
    write(tmp_path, "adapters/extra/adapter_config.json", "{}")
    report = validate_tree(tmp_path)
    assert report.ok and "UNREFERENCED_ADAPTER" in report.codes()


def test_skill_manifest_checks(tmp_path):
    minimal(tmp_path)
    (tmp_path / "skills" / "empty").mkdir(parents=True)
    write(tmp_path, "skills/nofront/SKILL.md", "# no frontmatter\n")
    write(tmp_path, "skills/noname/SKILL.md", "---\ndescription: x\n---\nbody\n")
    write(tmp_path, "skills/good/SKILL.md", "---\nname: good\ndescription: ok\n---\nbody\n")
    write(tmp_path, "skills/good/scripts/broken.py", "def f(:\n")
    report = validate_tree(tmp_path)
    codes = [i.code for i in report.errors]
    for code in ("MISSING_SKILL_MANIFEST", "SKILL_NO_FRONTMATTER", "SKILL_MISSING_NAME"):
        assert code in codes
    assert "SCRIPT_SYNTAX" in {i.code for i in report.blockers}


def test_adk_state_placeholder_in_instruction(tmp_path):
    minimal(tmp_path, prompt="Use the {task_id} to decide.\n")
    assert "ADK_STATE_PLACEHOLDER" in validate_tree(tmp_path).codes()
    minimal(tmp_path, prompt="Optional {task_id?} is fine; JSON like {\"a\": 1} is fine.\n")
    assert validate_tree(tmp_path).ok


def test_secrets_and_env_files(tmp_path):
    minimal(tmp_path)
    write(tmp_path, "configs/.env", "X=1")
    write(tmp_path, "prompts/extra.md", "token ghp_" + "a" * 36)
    codes = validate_tree(tmp_path).codes()
    assert {"FORBIDDEN_FILE", "POSSIBLE_SECRET"} <= codes


def test_disabled_tool_mentioned_in_prompt_warns(tmp_path):
    minimal(tmp_path, prompt="Call search_similar_code first.\n")
    report = validate_tree(tmp_path)
    assert report.ok and "PROMPT_MENTIONS_DISABLED_TOOL" in report.codes()


def _zip(path: Path, entries: dict[str, bytes], symlink: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/passwd")
    return path


def test_zip_valid_and_nested_root(tmp_path):
    agent = f"name: root\nmodel: {MODEL}\ninstruction: hi\n".encode()
    assert validate_zip(_zip(tmp_path / "ok.zip", {"agent.yaml": agent})).ok
    nested = validate_zip(_zip(tmp_path / "nested.zip", {"submission/agent.yaml": agent}))
    assert not nested.ok
    assert any("zip the directory contents" in i.message for i in nested.errors)


def test_zip_traversal_and_symlink(tmp_path):
    agent = f"name: root\nmodel: {MODEL}\ninstruction: hi\n".encode()
    report = validate_zip(_zip(tmp_path / "bad.zip", {"agent.yaml": agent, "../evil.md": b"x"}, symlink="prompts/link.md"))
    assert {"PATH_TRAVERSAL", "SYMLINK"} <= report.codes()
    assert not report.ok


def test_not_a_zip(tmp_path):
    path = write(tmp_path, "submission.zip", b"garbage")
    assert "BAD_ZIP" in validate_zip(path).codes()
