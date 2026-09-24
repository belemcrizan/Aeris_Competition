"""Variant composition and packaging."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from aeris_comp import variants as V
from aeris_comp.validation import validate_zip

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("variant_id", V.list_variants())
def test_every_variant_builds_a_valid_archive(tmp_path, variant_id):
    stage = tmp_path / "stage"
    V.stage(V.load_variant(variant_id), stage)
    out = tmp_path / "submission.zip"
    V.write_zip(stage, out)
    report = validate_zip(out)
    assert report.ok, report.format()
    assert not report.warnings, report.format()


def test_archive_layout_and_determinism(tmp_path):
    builds = []
    for i in range(2):
        stage = tmp_path / f"stage{i}"
        V.stage(V.load_variant("FULL"), stage)
        out = tmp_path / f"s{i}.zip"
        V.write_zip(stage, out)
        builds.append(out.read_bytes())
    assert builds[0] == builds[1]
    names = zipfile.ZipFile(tmp_path / "s0.zip").namelist()
    assert "agent.yaml" in names
    assert "prompts/system.md" in names
    assert not any(n.startswith("prompts/modules/") for n in names)
    assert all(not n.startswith(("/", "..")) for n in names)


def test_archive_text_files_use_lf(tmp_path):
    stage = tmp_path / "stage"
    V.stage(V.load_variant("FULL"), stage)
    script = stage / "skills" / "ledger" / "scripts" / "ledger.py"
    script.write_bytes(script.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    out = tmp_path / "s.zip"
    V.write_zip(stage, out)
    with zipfile.ZipFile(out) as archive:
        for name in archive.namelist():
            assert b"\r\n" not in archive.read(name), name


def test_baseline_has_no_graph_tools_or_skills():
    resolved = V.resolve(V.load_variant("B0"))
    assert set(resolved.tools) == {"run_command", "read_file", "edit_file", "write_file", "submit_patch", "get_status"}
    assert resolved.skills == ()
    assert resolved.prompt_modules == ("core",)


def test_ladder_is_monotone():
    ladder = ["B0", "B1", "B2", "B3", "B4", "B5", "FULL"]
    previous: set[str] = set()
    for variant_id in ladder:
        components = set(V.load_variant(variant_id).components)
        assert previous < components, variant_id
        previous = components


def test_ablations_remove_exactly_their_component():
    full = set(V.load_variant("FULL").components)
    expected = {
        "ABL_no_retrieval": {"semantic_retrieval"},
        "ABL_no_graph": {"graph_navigation"},
        "ABL_no_hypotheses": {"hypothesis_tracking", "uncertainty_gating"},
        "ABL_no_uncertainty": {"uncertainty_gating"},
        "ABL_no_feedback": {"failure_feedback"},
    }
    for variant_id, removed in expected.items():
        assert full - set(V.load_variant(variant_id).components) == removed, variant_id


def test_dependency_enforced():
    variant = V.Variant(id="X", description="", components=("core", "uncertainty_gating"))
    with pytest.raises(V.VariantError, match="requires"):
        V.resolve(variant)


def test_core_is_required():
    with pytest.raises(V.VariantError, match="required"):
        V.resolve(V.Variant(id="X", description="", components=("reviewer",)))


def test_adapter_variant_requires_adapter_dir(tmp_path):
    variant = V.Variant(id="X", description="", components=("core",), adapter="does_not_exist")
    with pytest.raises(V.VariantError, match="adapter"):
        V.stage(variant, tmp_path / "stage")


def test_checked_in_rendering_is_in_sync():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_submission.py"), "--check-sync"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_prompt_modules_only_mention_their_own_tools():
    components = V.load_components()
    tool_owner = {t: c.name for c in components.values() for t in c.tools}
    module_owner = {m: c.name for c in components.values() for m in c.prompt_modules}
    for module, owner in module_owner.items():
        text = (V.MODULES_DIR / f"{module}.md").read_text(encoding="utf-8")
        for tool, tool_comp in tool_owner.items():
            if tool in text and tool_comp not in {owner, "core"}:
                pytest.fail(f"module {module} mentions {tool} owned by {tool_comp}")
