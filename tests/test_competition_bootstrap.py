"""Artifact detection, sample-submission diff, smoke selection and release provenance.

Every "official" artifact here is SYNTHETIC, built in tmp_path from our own B0, so the
tests exercise the machinery without inventing competition content.
"""

from __future__ import annotations

import importlib.util
import json
import zipfile

import yaml
from conftest import REPO_ROOT

from aeris_comp import competition_artifacts as CA
from aeris_comp import variants as V
from aeris_comp.split import make_split, select_smoke
from aeris_comp.submission_diff import EXTENSION, INCOMPATIBLE, MATCH, UNKNOWN, compare


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage_b0(dest):
    V.stage(V.load_variant("B0"), dest)
    return dest


def tasks(n_per_repo=(5, 4, 3, 1)):
    rows = []
    for r, n in enumerate(n_per_repo):
        rows += [{"instance_id": f"owner__repo{r}-{i}", "repo": f"owner/repo{r}"} for i in range(n)]
    return rows


def fake_competition(root, *, readme=True, sample=True, task_rows=True):
    root.mkdir(parents=True)
    if readme:
        (root / "HARNESS_README.md").write_text("SYNTHETIC. Tools: run_command, submit_patch. Use !include.\n", encoding="utf-8")
    if sample:
        stage_b0(root / "sample_submission")
    if task_rows:
        (root / "tasks.jsonl").write_text("".join(json.dumps(t) + "\n" for t in tasks()), encoding="utf-8")
    (root / "notes.txt").write_text("x", encoding="utf-8")
    return root


def verdicts(findings):
    return {f.aspect: f.verdict for f in findings}


# ------------------------------------------------------------------ detection


def test_locate_finds_each_artifact_kind(tmp_path):
    root = fake_competition(tmp_path / "comp")
    found = CA.locate(root)
    assert [p.name for p in found.harness_readme] == ["HARNESS_README.md"]
    assert [p.name for p in found.sample_submission] == ["sample_submission"]
    assert [p.name for p in found.tasks] == ["tasks.jsonl"]
    assert found.missing == []


def test_locate_reports_missing_and_handles_absent_dir(tmp_path):
    assert CA.locate(tmp_path / "nope").missing == ["harness_readme", "sample_submission", "tasks"]
    root = fake_competition(tmp_path / "comp", sample=False, task_rows=False)
    assert CA.locate(root).missing == ["sample_submission", "tasks"]


def test_nested_sample_zip_and_non_task_jsonl(tmp_path):
    root = tmp_path / "comp"
    (root / "data").mkdir(parents=True)
    (root / "data" / "predictions.jsonl").write_text('{"id": "a", "prediction": ""}\n', encoding="utf-8")
    with zipfile.ZipFile(root / "sample_submission.zip", "w") as z:
        z.writestr("agent.yaml", "name: x\n")
    found = CA.locate(root)
    assert found.tasks == [] and [p.name for p in found.sample_submission] == ["sample_submission.zip"]


def test_inventory_records_hashes_not_contents(tmp_path):
    root = fake_competition(tmp_path / "comp")
    inv = CA.inventory(CA.locate(root))
    text = json.dumps(inv)
    assert "SYNTHETIC" not in text and "owner__repo0" not in text
    assert len(inv["tasks"][0]["sha256"]) == 64 and inv["tasks"][0]["rows"] == 13
    assert inv["sample_submission"][0]["kind"] == "dir"


def test_readme_mentions():
    m = CA.readme_mentions("run_command and submit_patch; skills use resources/")
    assert m["tools"]["run_command"] and not m["tools"]["get_code_subgraph"]
    assert m["terms"]["resources/"]["mentioned"] and not m["terms"]["references/"]["mentioned"]


# ------------------------------------------------------------------ diff


def test_identical_submission_has_no_incompatibility(tmp_path):
    ours, sample = stage_b0(tmp_path / "ours"), stage_b0(tmp_path / "sample")
    findings = compare(ours, sample)
    assert all(f.verdict == MATCH for f in findings), [f for f in findings if f.verdict != MATCH]


def test_model_and_tool_form_differences_are_incompatible(tmp_path):
    ours, sample = stage_b0(tmp_path / "ours"), stage_b0(tmp_path / "sample")
    cfg = yaml.safe_load((sample / "agent.yaml").read_text(encoding="utf-8").replace("!include", ""))
    cfg["model"] = "gemma-4-31b-it"
    cfg["tools"] = [t["name"] if isinstance(t, dict) else t for t in cfg["tools"]]
    cfg["instruction"] = "inline instruction"
    (sample / "agent.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    v = verdicts(compare(ours, sample))
    assert v["agent.yaml/model value"] == INCOMPATIBLE
    assert v["tools/entry form"] == INCOMPATIBLE
    assert v["!include usage"] == UNKNOWN


def test_extra_optional_entries_are_extensions_and_sample_only_entries_unknown(tmp_path):
    ours, sample = stage_b0(tmp_path / "ours"), stage_b0(tmp_path / "sample")
    (ours / "skills" / "demo").mkdir(parents=True)
    (ours / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
    (sample / "eval_config.yaml").write_text("budget: 1\n", encoding="utf-8")
    v = verdicts(compare(ours, sample))
    assert v["root/skills"] == EXTENSION
    assert v["root/eval_config.yaml"] == UNKNOWN
    assert v["skills"] == UNKNOWN
    assert v["skills/demo"] == UNKNOWN


def test_diff_accepts_zip_and_rejects_traversal(tmp_path):
    ours = stage_b0(tmp_path / "ours")
    good = tmp_path / "good.zip"
    V.write_zip(ours, good)
    assert all(f.verdict == MATCH for f in compare(good, ours))
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil/agent.yaml", "x")
    try:
        compare(ours, bad)
    except ValueError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("traversal accepted")


# ------------------------------------------------------------------ bootstrap


def test_bootstrap_missing_dir_exits_blocked(tmp_path, capsys):
    boot = load_script("competition_bootstrap")
    assert boot.main(["--dir", str(tmp_path / "none"), "--audits", str(tmp_path / "a")]) == 3
    assert "HUMAN_HANDOFF" in capsys.readouterr().out


def test_bootstrap_full_synthetic_run(tmp_path, capsys):
    boot = load_script("competition_bootstrap")
    root = fake_competition(tmp_path / "comp")
    audits, split = tmp_path / "audits", tmp_path / "split.json"
    code = boot.main(["--dir", str(root), "--audits", str(audits), "--split-out", str(split)])
    out = capsys.readouterr().out
    # FULL declares graph tools and skills B0's sample lacks: UNKNOWN, never INCOMPATIBLE.
    assert code == 0, out
    diff = (audits / "sample_submission_diff.md").read_text(encoding="utf-8")
    assert "## B0 vs sample" in diff and "## FULL vs sample" in diff and "INCOMPATIBLE: 0" in diff
    assert json.loads(split.read_text())["n_tasks"] == 13
    assert (audits / "harness_readme_mentions.json").is_file()
    assert "prepare --variant B0" in out
    # Rerun verifies instead of overwriting the frozen split.
    assert boot.main(["--dir", str(root), "--audits", str(audits), "--split-out", str(split)]) == 0
    assert "frozen split verified" in capsys.readouterr().out


def test_bootstrap_flags_incompatible_sample(tmp_path, capsys):
    boot = load_script("competition_bootstrap")
    root = fake_competition(tmp_path / "comp", task_rows=False)
    agent = root / "sample_submission" / "agent.yaml"
    agent.write_text(agent.read_text(encoding="utf-8").replace("gemma-4-31b-it-qat-w4a16-ct", "gemma-4-other"), encoding="utf-8")
    assert boot.main(["--dir", str(root), "--audits", str(tmp_path / "a"), "--split-out", str(tmp_path / "s.json")]) == 1
    assert "INCOMPAT" in capsys.readouterr().out


# ------------------------------------------------------------------ smoke selection


def test_smoke_selection_is_deterministic_dev_only_and_spread():
    rows = tasks()
    split = make_split(rows)
    a, b = select_smoke(rows, split, 4), select_smoke(rows, split, 4)
    assert a == b and a["n"] == 4
    assert set(a["task_ids"]) <= set(split["dev"])
    assert len(set(a["repos"].values())) == 4
    assert select_smoke(rows, split, 100)["n"] == len(split["dev"])


# ------------------------------------------------------------------ release provenance


def test_manifest_records_component_hashes(tmp_path):
    build = load_script("build_submission")
    entries: list[dict] = []
    assert build.build("B0", tmp_path / "B0.zip", manifest=entries) == 0
    hashes = entries[0]["hashes"]
    assert len(hashes["agent_yaml"]) == 64 and "prompts/system.md" in hashes["prompts"]
    assert hashes["adapters"] is None and entries[0]["adapter"] is None


def test_require_clean_refuses_dirty_tree(monkeypatch, capsys):
    build = load_script("build_submission")
    monkeypatch.setattr(build, "git_state", lambda: {"commit": "abc", "dirty": True})
    assert build.main(["--all", "--require-clean"]) == 1
    assert "dirty" in capsys.readouterr().err


def test_check_release_rejects_dirty_manifest(tmp_path, capsys):
    build = load_script("build_submission")
    path = tmp_path / "release_manifest.json"
    path.write_text(json.dumps({"git": {"commit": None, "dirty": True}, "variants": []}), encoding="utf-8")
    assert build.check_release(path) == 1
    err = capsys.readouterr().err
    assert "dirty working tree" in err and "no git commit" in err
