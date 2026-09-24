"""Compose a submission from independently switchable components.

A *component* (experiments/components.yaml) contributes harness tools, prompt modules and
skills. A *variant* (experiments/configs/*.yaml) is a list of enabled components. This
keeps every ablation a pure configuration change: the same prompt module text is used in
every variant that enables it.
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import constants as C

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_SRC = REPO_ROOT / "submission"
MODULES_DIR = SUBMISSION_SRC / "prompts" / "modules"
COMPONENTS_FILE = REPO_ROOT / "experiments" / "components.yaml"
VARIANTS_DIR = REPO_ROOT / "experiments" / "configs"
ADAPTERS_SRC = REPO_ROOT / "adapters"
DEFAULT_VARIANT = "FULL"
MODEL = "gemma-4-31b-it-qat-w4a16-ct"
AGENT_NAME = "aeris_swe_agent"
AGENT_DESCRIPTION = "Autonomous software engineer that localizes, fixes and validates one repository issue."
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
# Explains how to invoke skill scripts; inserted after the core module whenever skills ship.
SKILLS_MODULE = "skills"


class VariantError(ValueError):
    pass


@dataclass(frozen=True)
class Component:
    name: str
    tools: tuple[str, ...] = ()
    prompt_modules: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    required: bool = False


@dataclass(frozen=True)
class Variant:
    id: str
    description: str
    components: tuple[str, ...]
    adapter: str | None = None
    sampling: str = "sampling.yaml"


@dataclass(frozen=True)
class Resolved:
    variant: Variant
    tools: tuple[str, ...]
    prompt_modules: tuple[str, ...]
    skills: tuple[str, ...]


def load_components(path: Path = COMPONENTS_FILE) -> dict[str, Component]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("components"), dict):
        raise VariantError(f"{path}: expected a 'components' mapping")
    components: dict[str, Component] = {}
    for name, spec in raw["components"].items():
        spec = spec or {}
        unknown = set(spec) - {"tools", "prompt_modules", "skills", "requires", "required", "description"}
        if unknown:
            raise VariantError(f"component {name!r}: unknown fields {sorted(unknown)}")
        tools = tuple(spec.get("tools", ()))
        bad = [t for t in tools if t not in C.HARNESS_TOOLS]
        if bad:
            raise VariantError(f"component {name!r}: tools {bad} are not harness tools")
        components[name] = Component(
            name=name,
            tools=tools,
            prompt_modules=tuple(spec.get("prompt_modules", ())),
            skills=tuple(spec.get("skills", ())),
            requires=tuple(spec.get("requires", ())),
            required=bool(spec.get("required", False)),
        )
    return components


def variant_path(variant_id: str) -> Path:
    return VARIANTS_DIR / f"{variant_id}.yaml"


def list_variants() -> list[str]:
    return sorted(p.stem for p in VARIANTS_DIR.glob("*.yaml"))


def load_variant(variant: str | Path) -> Variant:
    path = Path(variant) if str(variant).endswith(".yaml") else variant_path(str(variant))
    if not path.is_file():
        raise VariantError(f"variant file {path} not found; known: {list_variants()}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = set(raw) - {"id", "description", "components", "adapter", "sampling"}
    if unknown:
        raise VariantError(f"{path}: unknown fields {sorted(unknown)}")
    if raw.get("id") != path.stem:
        raise VariantError(f"{path}: id {raw.get('id')!r} must equal file name {path.stem!r}")
    return Variant(
        id=raw["id"],
        description=str(raw.get("description", "")).strip(),
        components=tuple(raw.get("components") or ()),
        adapter=raw.get("adapter"),
        sampling=raw.get("sampling", "sampling.yaml"),
    )


def _ordered_unique(items):
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return tuple(seen)


def resolve(variant: Variant, components: dict[str, Component] | None = None) -> Resolved:
    components = components or load_components()
    enabled = set(variant.components)
    unknown = enabled - set(components)
    if unknown:
        raise VariantError(f"variant {variant.id}: unknown components {sorted(unknown)}")
    for comp in components.values():
        if comp.required and comp.name not in enabled:
            raise VariantError(f"variant {variant.id}: component {comp.name!r} is required")
        if comp.name in enabled:
            missing = [r for r in comp.requires if r not in enabled]
            if missing:
                raise VariantError(f"variant {variant.id}: {comp.name!r} requires {missing}")
    ordered = [c for c in components.values() if c.name in enabled]
    modules = list(_ordered_unique(m for c in ordered for m in c.prompt_modules))
    skills = _ordered_unique(s for c in ordered for s in c.skills)
    if skills:
        modules.insert(1, SKILLS_MODULE)
    return Resolved(
        variant=variant,
        tools=_ordered_unique(t for c in ordered for t in c.tools),
        prompt_modules=tuple(modules),
        skills=skills,
    )


def render_system_prompt(resolved: Resolved, modules_dir: Path = MODULES_DIR) -> str:
    parts = []
    for module in resolved.prompt_modules:
        path = modules_dir / f"{module}.md"
        if not path.is_file():
            raise VariantError(f"prompt module {path} not found")
        parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts) + "\n"


def render_agent_yaml(resolved: Resolved) -> str:
    lines = [
        f"# Generated by scripts/build_submission.py from experiments/configs/{resolved.variant.id}.yaml.",
        "# Edit the variant, components or prompt modules instead of this file.",
        "agent_class: LlmAgent",
        f"name: {AGENT_NAME}",
        f"model: {MODEL}",
        f"description: {AGENT_DESCRIPTION}",
    ]
    if resolved.variant.adapter:
        lines.append(f"adapter: {resolved.variant.adapter}")
    lines += [
        "instruction: !include prompts/system.md",
        "generate_content_config: !include configs/sampling.yaml",
        "tools:",
    ]
    lines += [f"  - name: {tool}" for tool in resolved.tools]
    return "\n".join(lines) + "\n"


def stage(variant: Variant, dest: Path, components: dict[str, Component] | None = None) -> Resolved:
    """Write the archive tree for ``variant`` into an empty directory ``dest``."""
    resolved = resolve(variant, components)
    if dest.exists() and any(dest.iterdir()):
        raise VariantError(f"staging directory {dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "agent.yaml").write_text(render_agent_yaml(resolved), encoding="utf-8", newline="\n")
    (dest / "prompts").mkdir()
    (dest / "prompts" / "system.md").write_text(render_system_prompt(resolved), encoding="utf-8", newline="\n")
    sampling = SUBMISSION_SRC / "configs" / variant.sampling
    if not sampling.is_file():
        raise VariantError(f"sampling config {sampling} not found")
    (dest / "configs").mkdir()
    shutil.copyfile(sampling, dest / "configs" / "sampling.yaml")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for skill in resolved.skills:
        src = SUBMISSION_SRC / "skills" / skill
        if not src.is_dir():
            raise VariantError(f"skill {src} not found")
        shutil.copytree(src, dest / "skills" / skill, ignore=ignore)
    if variant.adapter:
        src = ADAPTERS_SRC / variant.adapter
        if not src.is_dir():
            raise VariantError(f"adapter directory {src} not found")
        dest_adapter = dest / "adapters" / variant.adapter
        dest_adapter.mkdir(parents=True)
        for name in C.ADAPTER_REQUIRED_FILES:
            if (src / name).is_file():
                shutil.copyfile(src / name, dest_adapter / name)
    return resolved


TEXT_SUFFIXES = frozenset({".md", ".yaml", ".yml", ".py", ".sh", ".json", ".txt"})


def write_zip(src_dir: Path, zip_path: Path) -> None:
    """Deterministic archive: sorted entries, fixed timestamps and permissions, LF text files."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in src_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            rel = path.relative_to(src_dir).as_posix()
            info = zipfile.ZipInfo(rel, date_time=ZIP_EPOCH)
            executable = "/scripts/" in f"/{rel}" and path.suffix in {".py", ".sh"}
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            data = path.read_bytes()
            if path.suffix in TEXT_SUFFIXES:
                data = data.replace(b"\r\n", b"\n")
            archive.writestr(info, data)
