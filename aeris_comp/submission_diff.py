"""Structural and semantic diff of our submission against the official sample submission.

The sample is authority level 2 (docs/gaps.yaml), so it decides every difference it
covers. Verdicts:

- MATCH: same as the sample.
- COMPATIBLE_EXTENSION: we use something the sample does not, and a higher or equal
  authority documents it (Kaggle page, ADK).
- INCOMPATIBLE: the sample does it differently for the same thing; must be fixed.
- UNKNOWN: the sample says nothing either way; needs HARNESS_README or a harness run.
"""

from __future__ import annotations

import tempfile
import zipfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .constants import LLM_AGENT_KEYS, ROOT_ENTRIES
from .validation import SKILL_FRONTMATTER_KEYS
from .yaml_include import IncludeRef, load_yaml

MATCH = "MATCH"
EXTENSION = "COMPATIBLE_EXTENSION"
INCOMPATIBLE = "INCOMPATIBLE"
UNKNOWN = "UNKNOWN"
VERDICTS = (MATCH, EXTENSION, INCOMPATIBLE, UNKNOWN)


@dataclass(frozen=True)
class Finding:
    aspect: str
    ours: str
    sample: str
    verdict: str
    note: str = ""


@contextmanager
def open_submission(path: Path) -> Iterator[Path]:
    """Yield the directory that holds agent.yaml, extracting a zip into a temp dir."""
    if path.is_dir():
        yield _agent_root(path)
        return
    with tempfile.TemporaryDirectory(prefix="aeris_diff_") as tmp:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = info.filename
                if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                    raise ValueError(f"{path}: unsafe entry {name!r}")
            archive.extractall(tmp)
        yield _agent_root(Path(tmp))


def _agent_root(root: Path) -> Path:
    if (root / "agent.yaml").is_file():
        return root
    candidates = sorted(p.parent for p in root.rglob("agent.yaml") if "sub_agents" not in p.parts)
    if not candidates:
        raise FileNotFoundError(f"{root}: no agent.yaml")
    return min(candidates, key=lambda p: len(p.parts))


def _load(path: Path) -> Any:
    return load_yaml(path.read_text(encoding="utf-8"), allow_duplicates=True)


def _tool_form(tool: Any) -> str:
    if isinstance(tool, str):
        return "string"
    if isinstance(tool, dict):
        return "mapping(" + ",".join(sorted(tool)) + ")"
    return type(tool).__name__


def _tool_name(tool: Any) -> str:
    if isinstance(tool, str):
        return tool
    if isinstance(tool, dict):
        return str(tool.get("name", "?"))
    return "?"


def _fmt(values) -> str:
    values = sorted(values)
    return ", ".join(values) if values else "-"


def _frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    data = yaml.safe_load(parts[1]) if len(parts) >= 3 else None
    return data if isinstance(data, dict) else {}


def _skills(root: Path) -> dict[str, dict]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return {}
    out = {}
    for d in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        manifest = d / "SKILL.md"
        out[d.name] = {
            "frontmatter": set(_frontmatter(manifest)) if manifest.is_file() else set(),
            "subdirs": {p.name for p in d.iterdir() if p.is_dir()},
            "script_suffixes": {p.suffix for p in (d / "scripts").rglob("*") if p.is_file()} if (d / "scripts").is_dir() else set(),
        }
    return out


def _compare_scalar(aspect: str, ours: Any, sample: Any, missing_note: str) -> Finding:
    if sample is None and ours is None:
        return Finding(aspect, "-", "-", MATCH)
    if sample is None:
        return Finding(aspect, str(ours), "-", UNKNOWN, missing_note)
    if ours == sample:
        return Finding(aspect, str(ours), str(sample), MATCH)
    return Finding(aspect, str(ours), str(sample), INCOMPATIBLE, "use the sample's value")


def compare_roots(ours: Path, sample: Path) -> list[Finding]:
    findings: list[Finding] = []
    ours_root, sample_root = ({p.name for p in r.iterdir()} for r in (ours, sample))

    # Root layout
    for entry in sorted(ours_root | sample_root):
        if entry in ours_root and entry in sample_root:
            findings.append(Finding(f"root/{entry}", "present", "present", MATCH))
        elif entry in ours_root:
            verdict = EXTENSION if entry in ROOT_ENTRIES else UNKNOWN
            findings.append(Finding(f"root/{entry}", "present", "absent", verdict, "optional entry named on the Kaggle page" if verdict == EXTENSION else "not documented anywhere"))
        else:
            verdict = INCOMPATIBLE if entry == "agent.yaml" else UNKNOWN
            findings.append(Finding(f"root/{entry}", "absent", "present", verdict, "sample ships it; check whether it is required"))

    ours_cfg, sample_cfg = _load(ours / "agent.yaml"), _load(sample / "agent.yaml")
    if not isinstance(ours_cfg, dict) or not isinstance(sample_cfg, dict):
        findings.append(Finding("agent.yaml", type(ours_cfg).__name__, type(sample_cfg).__name__, INCOMPATIBLE, "agent.yaml must be a mapping"))
        return findings

    # agent.yaml keys
    for key in sorted(set(ours_cfg) | set(sample_cfg)):
        if key in ours_cfg and key in sample_cfg:
            findings.append(Finding(f"agent.yaml/{key}", "set", "set", MATCH))
        elif key in ours_cfg:
            verdict = EXTENSION if key in LLM_AGENT_KEYS else UNKNOWN
            findings.append(Finding(f"agent.yaml/{key}", "set", "absent", verdict, "ADK LlmAgentConfig field" if verdict == EXTENSION else ""))
        else:
            findings.append(Finding(f"agent.yaml/{key}", "absent", "set", UNKNOWN, "sample uses a key we do not; check whether it is required"))

    for key in ("agent_class", "model"):
        findings.append(_compare_scalar(f"agent.yaml/{key} value", ours_cfg.get(key), sample_cfg.get(key), "sample relies on the default"))

    # !include usage
    def includes(cfg: dict) -> dict[str, str]:
        return {k: Path(v.path).suffix or "(none)" for k, v in cfg.items() if isinstance(v, IncludeRef)}

    ours_inc, sample_inc = includes(ours_cfg), includes(sample_cfg)
    if sample_inc:
        verdict = MATCH if set(ours_inc) <= set(sample_inc) else UNKNOWN
        findings.append(Finding("!include usage", _fmt(f"{k}{s}" for k, s in ours_inc.items()), _fmt(f"{k}{s}" for k, s in sample_inc.items()), verdict, "sample proves !include works for these keys"))
    elif ours_inc:
        findings.append(Finding("!include usage", _fmt(f"{k}{s}" for k, s in ours_inc.items()), "-", UNKNOWN, "sample never uses !include; inline if HARNESS_README does not document it"))

    # Tools
    ours_tools, sample_tools = ours_cfg.get("tools") or [], sample_cfg.get("tools") or []
    ours_forms, sample_forms = Counter(map(_tool_form, ours_tools)), Counter(map(_tool_form, sample_tools))
    if sample_tools:
        verdict = MATCH if set(ours_forms) <= set(sample_forms) else INCOMPATIBLE
        findings.append(Finding("tools/entry form", _fmt(ours_forms), _fmt(sample_forms), verdict, "" if verdict == MATCH else "write tool entries the way the sample does"))
    else:
        findings.append(Finding("tools/entry form", _fmt(ours_forms), "-", UNKNOWN, "sample declares no tools; harness may inject them"))
    ours_names, sample_names = {_tool_name(t) for t in ours_tools}, {_tool_name(t) for t in sample_tools}
    for name in sorted(ours_names | sample_names):
        if name in ours_names and name in sample_names:
            findings.append(Finding(f"tools/{name}", "declared", "declared", MATCH))
        elif name in ours_names:
            findings.append(Finding(f"tools/{name}", "declared", "absent", UNKNOWN, "named on the Kaggle page; sample does not use it"))
        else:
            findings.append(Finding(f"tools/{name}", "absent", "declared", UNKNOWN, "sample uses a tool we do not"))

    # Sampling
    ours_gen = _resolve(ours_cfg.get("generate_content_config"), ours)
    sample_gen = _resolve(sample_cfg.get("generate_content_config"), sample)
    for key in sorted(set(ours_gen) | set(sample_gen)):
        if key in ours_gen and key in sample_gen:
            findings.append(Finding(f"sampling/{key}", str(ours_gen[key]), str(sample_gen[key]), MATCH, "values may differ; keys match"))
        elif key in ours_gen:
            findings.append(Finding(f"sampling/{key}", str(ours_gen[key]), "absent", UNKNOWN, "GenerateContentConfig field the sample does not set"))
        else:
            findings.append(Finding(f"sampling/{key}", "absent", str(sample_gen[key]), UNKNOWN, "sample sets it; consider matching"))

    # Skills
    ours_skills, sample_skills = _skills(ours), _skills(sample)
    for name in sorted(set(ours_skills) | set(sample_skills)):
        if name in ours_skills and name in sample_skills:
            findings.append(Finding(f"skills/{name}", "present", "present", MATCH))
        elif name in ours_skills:
            findings.append(Finding(f"skills/{name}", "present", "absent", UNKNOWN, "we ship a skill the sample does not"))
        else:
            findings.append(Finding(f"skills/{name}", "absent", "present", UNKNOWN, "sample ships this skill"))
    if sample_skills:
        s_keys = set().union(*(s["frontmatter"] for s in sample_skills.values()))
        o_keys = set().union(*(s["frontmatter"] for s in ours_skills.values())) if ours_skills else set()
        extra = o_keys - s_keys
        findings.append(Finding("skills/frontmatter keys", _fmt(o_keys), _fmt(s_keys), MATCH if not extra else (EXTENSION if extra <= SKILL_FRONTMATTER_KEYS else UNKNOWN)))
        s_sub = set().union(*(s["subdirs"] for s in sample_skills.values()))
        o_sub = set().union(*(s["subdirs"] for s in ours_skills.values())) if ours_skills else set()
        findings.append(Finding("skills/subdirectories", _fmt(o_sub), _fmt(s_sub), MATCH if o_sub <= s_sub else UNKNOWN, "sample shows which resource directory name the harness expects (resources/ vs references/)"))
        s_suf = set().union(*(s["script_suffixes"] for s in sample_skills.values()))
        o_suf = set().union(*(s["script_suffixes"] for s in ours_skills.values())) if ours_skills else set()
        findings.append(Finding("skills/script types", _fmt(o_suf), _fmt(s_suf), MATCH if o_suf <= s_suf else UNKNOWN))
    elif ours_skills:
        findings.append(Finding("skills", _fmt(ours_skills), "-", UNKNOWN, "sample ships no skills; discovery still unverified (C-07)"))

    # Prompts, configs, adapters: file types only
    for sub in ("prompts", "configs", "adapters", "sub_agents"):
        o = {p.suffix for p in (ours / sub).rglob("*") if p.is_file()} if (ours / sub).is_dir() else set()
        s = {p.suffix for p in (sample / sub).rglob("*") if p.is_file()} if (sample / sub).is_dir() else set()
        if o or s:
            findings.append(Finding(f"{sub}/file types", _fmt(o), _fmt(s), MATCH if o <= s else UNKNOWN))
    return findings


def _resolve(value: Any, base: Path) -> dict:
    if isinstance(value, IncludeRef):
        loaded = _load(base / value.path)
        return loaded if isinstance(loaded, dict) else {}
    return value if isinstance(value, dict) else {}


def compare(ours: Path, sample: Path) -> list[Finding]:
    with open_submission(ours) as o, open_submission(sample) as s:
        return compare_roots(o, s)


def render_markdown(sections: dict[str, list[Finding]], sample_label: str) -> str:
    out = ["# Sample submission diff\n\n", f"Sample: `{sample_label}` (authority level 2). Generated by `scripts/competition_bootstrap.py`; do not edit by hand.\n\n"]
    for title, findings in sections.items():
        counts = Counter(f.verdict for f in findings)
        out.append(f"## {title}\n\n")
        out.append(" | ".join(f"{v}: {counts.get(v, 0)}" for v in VERDICTS) + "\n\n")
        out.append("| Aspect | Ours | Sample | Verdict | Note |\n| --- | --- | --- | --- | --- |\n")
        order = {v: i for i, v in enumerate((INCOMPATIBLE, UNKNOWN, EXTENSION, MATCH))}
        for f in sorted(findings, key=lambda f: (order[f.verdict], f.aspect)):
            cells = [f.aspect, f.ours, f.sample, f.verdict, f.note]
            out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |\n")
        out.append("\n")
    return "".join(out)
