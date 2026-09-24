"""Local approximation of the competition PASS/FAIL grading.

Documented grading (competition Overview > Issue Scoring, dataset page): the submitted
patch is applied to the task repository at ``base_commit``, the task's ``test_patch`` is
applied, and the validation tests run under pytest. The exact test selection and apply
command of the official grader are not published; we run every test file touched by
``test_patch`` and use ``git apply``. See docs/EXPERIMENTS.md for the consequences.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .taxonomy import AUTOMATIC_CATEGORY

NO_PATCH_MARKER = "NO_PATCH"


@dataclass
class TaskResult:
    instance_id: str
    status: str
    detail: str = ""
    files_changed: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    test_files: list[str] = field(default_factory=list)
    scoring_seconds: float = 0.0
    failure_category: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def diff_stats(patch: str) -> tuple[list[str], int, int]:
    files, added, removed = [], 0, 0
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if match:
                files.append(match.group(2))
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return files, added, removed


def test_files_from_patch(test_patch: str) -> list[str]:
    files = []
    for line in test_patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[len("+++ b/") :].strip()
            if path.endswith(".py") and path not in files:
                files.append(path)
    return files


def load_tasks(path: Path) -> dict[str, dict]:
    tasks = {}
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                task = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            tasks[task["instance_id"]] = task
    return tasks


def load_predictions(path: Path) -> dict[str, str]:
    if path.suffix == ".jsonl":
        preds = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    preds[row["id"]] = row["prediction"]
        return preds
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq  # optional dependency, only needed for parquet
        except ImportError as exc:
            raise RuntimeError("reading .parquet predictions needs pyarrow (pip install pyarrow)") from exc
        table = pq.read_table(path, columns=["id", "prediction"]).to_pydict()
        return dict(zip(table["id"], table["prediction"], strict=True))
    raise ValueError(f"unsupported predictions format {path.suffix!r}; use .jsonl or .parquet")


def extract_snapshot(archive: Path, dest: Path) -> Path:
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    for candidate in [dest, *sorted(p for p in dest.iterdir() if p.is_dir())]:
        if (candidate / ".git").exists():
            return candidate
    raise FileNotFoundError(f"{archive}: no git repository found in snapshot")


def _run(cmd: list[str] | str, cwd: Path, timeout: float, shell: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=shell)


def _apply(repo: Path, patch: str, label: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False, encoding="utf-8", newline="\n") as handle:
        handle.write(patch if patch.endswith("\n") else patch + "\n")
        patch_file = handle.name
    try:
        check = _run(["git", "apply", "--check", "--whitespace=nowarn", patch_file], repo, 60)
        if check.returncode != 0:
            return False, f"{label}: {check.stderr.strip()[:500]}"
        done = _run(["git", "apply", "--whitespace=nowarn", patch_file], repo, 60)
        return done.returncode == 0, done.stderr.strip()[:500]
    finally:
        Path(patch_file).unlink(missing_ok=True)


def score_repo(
    repo: Path,
    task: dict,
    prediction: str | None,
    python: str = sys.executable,
    timeout: float = 900,
    setup_cmd: str | None = None,
) -> TaskResult:
    """Score one prediction against an already extracted repository at base_commit."""
    start = time.monotonic()
    result = TaskResult(instance_id=task["instance_id"], status="FAIL")
    result.test_files = test_files_from_patch(task.get("test_patch", ""))

    def finish(status: str, detail: str = "") -> TaskResult:
        result.status = status
        result.detail = detail
        result.failure_category = AUTOMATIC_CATEGORY.get(status)
        result.scoring_seconds = round(time.monotonic() - start, 2)
        return result

    if not prediction or prediction.strip() in {"", NO_PATCH_MARKER}:
        return finish("NO_PATCH")
    result.files_changed, result.lines_added, result.lines_removed = diff_stats(prediction)
    ok, message = _apply(repo, prediction, "prediction")
    if not ok:
        return finish("APPLY_FAILED", message)
    ok, message = _apply(repo, task.get("test_patch", ""), "test_patch")
    if not ok:
        return finish("TEST_PATCH_CONFLICT", message)
    if setup_cmd:
        setup = _run(setup_cmd, repo, timeout, shell=True)
        if setup.returncode != 0:
            return finish("SETUP_FAILED", (setup.stdout + setup.stderr)[-500:])
    if not result.test_files:
        return finish("FAIL", "test_patch touches no Python test files")
    try:
        proc = _run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider", *result.test_files], repo, timeout)
    except subprocess.TimeoutExpired:
        return finish("TIMEOUT", f"pytest exceeded {timeout}s")
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
    return finish("PASS" if proc.returncode == 0 else "FAIL", tail[-500:])


def score_task(
    task: dict,
    prediction: str | None,
    snapshots_dir: Path,
    python: str = sys.executable,
    timeout: float = 900,
    setup_cmd: str | None = None,
    keep_dir: Path | None = None,
) -> TaskResult:
    archive = snapshots_dir / f"{task['instance_id']}.tgz"
    if not archive.is_file():
        return TaskResult(instance_id=task["instance_id"], status="MISSING_SNAPSHOT", detail=str(archive))
    work = Path(tempfile.mkdtemp(prefix=f"score_{task['instance_id']}_", dir=keep_dir))
    try:
        repo = extract_snapshot(archive, work)
        return score_repo(repo, task, prediction, python=python, timeout=timeout, setup_cmd=setup_cmd)
    finally:
        if keep_dir is None:
            shutil.rmtree(work, ignore_errors=True)
