"""Locate official competition artifacts supplied by a human (docs/HUMAN_HANDOFF.md).

The directory is gitignored: competition data is never committed. Only names, sizes
and SHA-256 hashes are recorded, never contents.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .constants import ALLOWED_MODELS, HARNESS_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO_ROOT / "external" / "competition"
ENV_VAR = "AERIS_COMPETITION_DIR"
MAX_DEPTH = 6

# Terms whose presence in HARNESS_README decides open questions in
# docs/COMPETITION_REQUIREMENTS.md. A mention is a pointer for the human audit, not a verdict.
README_TERMS = {
    "!include": "R-INC-*",
    "run_skill_script": "R-SKILL-3b",
    "load_skill_resource": "R-SKILL-2",
    "resources/": "open question 2",
    "references/": "open question 2",
    "eval_config": "C-12",
    "agent_tool": "R-TOOLS-3",
    "AgentTool": "R-TOOLS-3",
    "compaction": "C-15",
    "get_status": "C-13",
    "adapter": "R-LORA-*",
    "generate_content_config": "R-CFG-*",
    "skills_folder": "R-SKILL-5",
}


def competition_dir() -> Path:
    return Path(os.environ.get(ENV_VAR) or DEFAULT_DIR)


@dataclass
class Artifacts:
    root: Path
    harness_readme: list[Path] = field(default_factory=list)
    sample_submission: list[Path] = field(default_factory=list)
    tasks: list[Path] = field(default_factory=list)
    other: list[Path] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        return [name for name in ("harness_readme", "sample_submission", "tasks") if not getattr(self, name)]


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in sorted(dirnames) if not d.startswith(".") and depth < MAX_DEPTH]
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _is_task_file(path: Path) -> bool:
    if path.suffix != ".jsonl" or path.stat().st_size == 0:
        return False
    with path.open(encoding="utf-8", errors="replace") as handle:
        first = handle.readline()
    try:
        row = json.loads(first)
    except json.JSONDecodeError:
        return False
    return isinstance(row, dict) and "instance_id" in row


def locate(root: Path | None = None) -> Artifacts:
    root = root or competition_dir()
    found = Artifacts(root=root)
    if not root.is_dir():
        return found
    sample_dirs: set[Path] = set()
    for path in _walk(root):
        name = path.name.lower()
        if name.startswith("harness_readme") and path.suffix.lower() in {".md", ".txt", ""}:
            found.harness_readme.append(path)
        elif name == "agent.yaml" and any(p.lower().startswith("sample_submission") for p in path.relative_to(root).parts[:-1]):
            if "sub_agents" not in path.relative_to(root).parts:
                sample_dirs.add(path.parent)
        elif name.startswith("sample_submission") and path.suffix == ".zip":
            found.sample_submission.append(path)
        elif _is_task_file(path):
            found.tasks.append(path)
        else:
            found.other.append(path)
    # Keep the outermost agent.yaml of each sample tree.
    for d in sorted(sample_dirs, key=lambda p: len(p.parts)):
        if not any(d.is_relative_to(k) for k in found.sample_submission if k.is_dir()):
            found.sample_submission.append(d)
    found.other = [p for p in found.other if not any(p.is_relative_to(d) for d in found.sample_submission if d.is_dir())]
    return found


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(found: Artifacts) -> dict:
    def entry(path: Path) -> dict:
        rel = path.relative_to(found.root).as_posix()
        if path.is_dir():
            files = [p for p in _walk(path)]
            return {"path": rel, "kind": "dir", "files": len(files), "bytes": sum(p.stat().st_size for p in files)}
        return {"path": rel, "kind": "file", "bytes": path.stat().st_size, "sha256": _sha256(path)}

    suffixes: dict[str, int] = {}
    for p in found.other:
        suffixes[p.suffix or "(none)"] = suffixes.get(p.suffix or "(none)", 0) + 1
    return {
        "schema": "aeris-competition-inventory/1",
        "harness_readme": [entry(p) for p in found.harness_readme],
        "sample_submission": [entry(p) for p in found.sample_submission],
        "tasks": [entry(p) | {"rows": sum(1 for line in p.open(encoding="utf-8") if line.strip())} for p in found.tasks],
        "other_by_suffix": dict(sorted(suffixes.items())),
        "missing": found.missing,
    }


def readme_mentions(text: str) -> dict:
    """Which of our assumptions HARNESS_README mentions; pointers for the manual audit."""
    lowered = text.lower()
    tools = {t: bool(re.search(rf"\b{re.escape(t)}\b", text)) for t in sorted(HARNESS_TOOLS)}
    models = {m: m in text for m in sorted(ALLOWED_MODELS)}
    terms = {term: {"mentioned": term.lower() in lowered, "decides": ref} for term, ref in README_TERMS.items()}
    return {"tools": tools, "models": models, "terms": terms}
