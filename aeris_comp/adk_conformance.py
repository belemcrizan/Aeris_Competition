"""Check a submission against Google ADK's own config and skill parsers.

ADK is authority level 6 (below the harness and the sample submission), so a pass
here means "ADK accepts it", not "the harness accepts it". ``google-adk`` is an
optional dependency; everything degrades to ``status: ADK_UNAVAILABLE``.

``adapter`` is a competition extension of LlmAgent that ADK does not know; it is
removed before ADK validation and reported under ``extensions``.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from .yaml_include import IncludeRef, load_yaml_file

COMPETITION_EXTENSIONS = ("adapter",)


def adk_version() -> str | None:
    try:
        import google.adk
    except ImportError:
        return None
    return getattr(google.adk, "__version__", "unknown")


def resolve_includes(value: Any, base: Path) -> Any:
    if isinstance(value, IncludeRef):
        target = base / value.path
        if target.suffix in {".yaml", ".yml"}:
            return resolve_includes(load_yaml_file(target), target.parent)
        return target.read_text(encoding="utf-8")
    if isinstance(value, dict):
        return {k: resolve_includes(v, base) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_includes(v, base) for v in value]
    return value


def check_agent_file(path: Path, seen: set[Path] | None = None) -> list[dict[str, Any]]:
    from google.adk.agents.agent_config import AgentConfig
    from pydantic import ValidationError

    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    results: list[dict[str, Any]] = []
    entry: dict[str, Any] = {"file": path.name, "errors": [], "extensions": {}}
    try:
        data = resolve_includes(load_yaml_file(path), path.parent)
    except (OSError, yaml.YAMLError) as exc:
        entry["errors"].append(f"load: {exc}")
        return [entry]
    if isinstance(data, dict):
        for key in COMPETITION_EXTENSIONS:
            if key in data:
                entry["extensions"][key] = data.pop(key)
    try:
        AgentConfig.model_validate(data)
    except ValidationError as exc:
        entry["errors"].extend(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors(include_url=False)
        )
    entry["harness_provided_tools"] = _tools_stock_adk_cannot_resolve(data)
    results.append(entry)
    for sub in (data.get("sub_agents") or []) if isinstance(data, dict) else []:
        if isinstance(sub, dict) and isinstance(sub.get("config_path"), str):
            results += check_agent_file(path.parent / sub["config_path"], seen)
    return results


def _tools_stock_adk_cannot_resolve(data: Any) -> list[str]:
    """Undotted tool names that google.adk.tools does not export as a tool.

    Stock ADK resolves ``name: X`` as ``google.adk.tools.X``; the competition harness
    must supply these itself (run_command, submit_patch, ...). Informational only.
    """
    import inspect

    import google.adk.tools as adk_tools
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.base_toolset import BaseToolset

    names = []
    for tool in (data.get("tools") or []) if isinstance(data, dict) else []:
        name = tool.get("name") if isinstance(tool, dict) else tool
        if not isinstance(name, str) or "." in name:
            continue
        obj = getattr(adk_tools, name, None)
        usable = isinstance(obj, (BaseTool, BaseToolset)) or (
            inspect.isclass(obj) and issubclass(obj, (BaseTool, BaseToolset))
        ) or (callable(obj) and not inspect.ismodule(obj))
        if not usable:
            names.append(name)
    return names


def check_skills(skills_dir: Path) -> list[dict[str, Any]]:
    from google.adk.skills import _utils

    results = []
    if not skills_dir.is_dir():
        return results
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        entry: dict[str, Any] = {"skill": skill_dir.name, "problems": list(_utils._validate_skill_dir(skill_dir))}
        if not entry["problems"]:
            try:
                skill = _utils._load_skill_from_dir(skill_dir)
                entry["scripts"] = sorted(skill.resources.list_scripts())
                entry["references"] = sorted(skill.resources.list_references())
                entry["assets"] = sorted(skill.resources.list_assets())
            except Exception as exc:  # noqa: BLE001 - report whatever ADK raises
                entry["problems"].append(f"load: {type(exc).__name__}: {exc}")
        results.append(entry)
    return results


def check_tree(root: Path) -> dict[str, Any]:
    version = adk_version()
    if version is None:
        return {"status": "ADK_UNAVAILABLE", "adk_version": None}
    agents = check_agent_file(root / "agent.yaml")
    skills = check_skills(root / "skills")
    ok = all(not a["errors"] for a in agents) and all(not s["problems"] for s in skills)
    return {
        "status": "PASS" if ok else "FAIL",
        "adk_version": version,
        "authority": "ADK (level 6); not the official harness",
        "agents": agents,
        "skills": skills,
    }


def check_path(path: Path) -> dict[str, Any]:
    if path.is_dir():
        return check_tree(path)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        return check_tree(Path(tmp))
