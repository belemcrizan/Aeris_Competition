"""Shared fixtures. All tests are local: none needs the competition harness or model."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "submission" / "skills"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(1, str(REPO_ROOT / "scripts"))
# Importing skill scripts must not leave __pycache__ inside the shippable submission tree.
sys.dont_write_bytecode = True


def load_script(skill: str, script: str):
    path = SKILLS / skill / "scripts" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(f"skill_{skill}_{script}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return proc.stdout


def make_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Skill scripts write state/telemetry under AERIS_STATE_DIR; never let them hit /tmp/aeris."""
    path = tmp_path / "state"
    monkeypatch.setenv("AERIS_STATE_DIR", str(path))
    monkeypatch.delenv("AERIS_TASK_ID", raising=False)
    monkeypatch.delenv("AERIS_VARIANT", raising=False)
    return path


# Test levels (docs/TESTING.md). Modules that spawn git, pytest or build archives are
# LOCAL_INTEGRATION; OFFICIAL_HARNESS tests must be marked explicitly and skip here.
LOCAL_INTEGRATION_MODULES = {
    "test_build.py",
    "test_review_and_navigation.py",
    "test_testing_skill.py",
    "test_scoring_and_metrics.py",
    "test_adk_conformance.py",
    "test_skill_runtime_contract.py",
    "test_security_skills.py",
    "test_competition_bootstrap.py",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.get_closest_marker("official_harness"):
            item.add_marker(pytest.mark.skip(reason="needs the official competition harness (not available)"))
        elif item.path.name in LOCAL_INTEGRATION_MODULES:
            item.add_marker(pytest.mark.local_integration)
        else:
            item.add_marker(pytest.mark.unit)
