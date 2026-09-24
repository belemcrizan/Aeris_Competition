"""Static validation of a submission directory or ``submission.zip``.

The checks encode verified competition rules (see docs/COMPETITION_REQUIREMENTS.md) plus
defensive checks for failure modes that would silently cost tasks (for example ADK state
placeholders in instructions). Rules whose harness behaviour is unverified produce
warnings instead of errors.
"""

from __future__ import annotations

import json
import posixpath
import re
import stat
import struct
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from . import constants as C
from .yaml_include import DuplicateKeyError, IncludeRef, load_yaml

ERROR = "ERROR"
WARNING = "WARNING"

MAX_NON_ADAPTER_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024**3

# ADK's instruction templating replaces {name}, {name?}, {app:name}, {artifact.x} with
# session state and raises KeyError when a non-optional key is missing.
ADK_STATE_PLACEHOLDER = re.compile(r"\{+\s*((?:app:|user:|temp:)?[A-Za-z_][A-Za-z0-9_]*|artifact\.[^{}\s]+)\s*(\?)?\s*\}+")

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_\-]{32,}"),
    "huggingface_token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "kaggle_key": re.compile(r"(?i)kaggle_key\s*[:=]\s*['\"]?[0-9a-f]{32}"),
}
FORBIDDEN_NAMES = {".env", ".netrc", "id_rsa", "id_ed25519", "kaggle.json", "credentials.json"}
JUNK_PARTS = {"__pycache__", ".git", ".DS_Store", ".pytest_cache", ".ipynb_checkpoints"}
NETWORK_IMPORTS = re.compile(
    r"^\s*(?:import|from)\s+(socket|requests|httpx|urllib\.request|urllib3|http\.client|aiohttp|ftplib|smtplib)\b",
    re.MULTILINE,
)
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".sh", ".txt", ".toml", ".cfg", ".ini"}


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str
    path: str = ""

    def format(self) -> str:
        where = f" [{self.path}]" if self.path else ""
        return f"{self.level:7} {self.code}{where}: {self.message}"


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    tools: set[str] = field(default_factory=set)
    adapters: set[str] = field(default_factory=set)
    skills: list[str] = field(default_factory=list)

    def error(self, code: str, message: str, path: str = "") -> None:
        self.issues.append(Issue(ERROR, code, message, path))

    def warn(self, code: str, message: str, path: str = "") -> None:
        self.issues.append(Issue(WARNING, code, message, path))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}

    def format(self) -> str:
        lines = [i.format() for i in self.issues]
        lines.append(
            f"agents={len(self.agents)} tools={sorted(self.tools)} adapters={sorted(self.adapters)} "
            f"skills={self.skills}"
        )
        lines.append(f"RESULT: {'VALID' if self.ok else 'INVALID'} ({len(self.errors)} errors, {len(self.warnings)} warnings)")
        return "\n".join(lines)


class _TreeValidator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.report = Report()
        self._visited_agents: set[str] = set()

    def run(self) -> Report:
        agent = self.root / "agent.yaml"
        if not agent.is_file():
            self.report.error("MISSING_AGENT_YAML", "agent.yaml must exist at the archive root")
        else:
            self._validate_agent_file("agent.yaml", is_root=True)
        self._validate_root_entries()
        self._validate_skills()
        self._validate_adapters()
        self._scan_files()
        return self.report

    # ---------------------------------------------------------------- paths
    def _resolve(self, base_rel: str, ref: str, context: str) -> str | None:
        """Resolve ``ref`` relative to directory ``base_rel``; return root-relative posix path."""
        if not isinstance(ref, str) or not ref.strip():
            self.report.error("EMPTY_PATH", f"{context}: empty path", base_rel)
            return None
        ref = ref.strip()
        if "\\" in ref:
            self.report.error("BACKSLASH_PATH", f"{context}: use forward slashes in {ref!r}", base_rel)
            return None
        if ref.startswith("/") or re.match(r"^[A-Za-z]:", ref):
            self.report.error("ABSOLUTE_PATH", f"{context}: absolute path {ref!r} not allowed", base_rel)
            return None
        joined = posixpath.normpath(posixpath.join(base_rel, ref)) if base_rel else posixpath.normpath(ref)
        if joined == ".." or joined.startswith("../"):
            self.report.error("PATH_TRAVERSAL", f"{context}: {ref!r} escapes the submission root", base_rel)
            return None
        current = self.root
        for part in PurePosixPath(joined).parts:
            current = current / part
            if current.is_symlink():
                self.report.error("SYMLINK", f"{context}: {joined!r} goes through a symlink", base_rel)
                return None
        target = self.root / joined
        if not target.exists():
            self.report.error("MISSING_INCLUDE", f"{context}: {joined!r} does not exist", base_rel)
            return None
        if not str(target.resolve()).startswith(str(self.root)):
            self.report.error("PATH_TRAVERSAL", f"{context}: {joined!r} resolves outside the root", base_rel)
            return None
        return joined

    def _load_yaml(self, rel: str) -> Any:
        try:
            return load_yaml((self.root / rel).read_text(encoding="utf-8"))
        except (yaml.YAMLError, DuplicateKeyError) as exc:
            self.report.error("YAML_PARSE", str(exc).splitlines()[0], rel)
        except UnicodeDecodeError:
            self.report.error("NOT_UTF8", "file is not valid UTF-8", rel)
        return None

    def _include_text(self, file_rel: str, value: Any, context: str) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, IncludeRef):
            target = self._resolve(posixpath.dirname(file_rel), value.path, f"{context} !include")
            if target is None:
                return None
            if not (self.root / target).is_file():
                self.report.error("INCLUDE_NOT_FILE", f"{context}: {target!r} is not a file", file_rel)
                return None
            return (self.root / target).read_text(encoding="utf-8")
        self.report.error("BAD_TYPE", f"{context} must be a string or !include", file_rel)
        return None

    def _include_mapping(self, file_rel: str, value: Any, context: str) -> dict | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, IncludeRef):
            target = self._resolve(posixpath.dirname(file_rel), value.path, f"{context} !include")
            if target is None:
                return None
            data = self._load_yaml(target)
            if data is None:
                return None
            if not isinstance(data, dict):
                self.report.error("BAD_TYPE", f"{context}: included file must be a YAML mapping", target)
                return None
            return data
        self.report.error("BAD_TYPE", f"{context} must be a mapping or !include", file_rel)
        return None

    # --------------------------------------------------------------- agents
    def _validate_agent_file(self, rel: str, is_root: bool = False) -> None:
        if rel in self._visited_agents:
            return
        self._visited_agents.add(rel)
        data = self._load_yaml(rel)
        if data is None:
            return
        if not isinstance(data, dict):
            self.report.error("BAD_TYPE", "agent config must be a YAML mapping", rel)
            return
        self.report.agents.append(rel)
        agent_class = data.get("agent_class", "LlmAgent")
        if agent_class in C.WORKFLOW_AGENT_CLASSES:
            self._validate_workflow_agent(rel, data)
        elif agent_class == "LlmAgent":
            self._validate_llm_agent(rel, data)
        else:
            self.report.error("UNSUPPORTED_AGENT_CLASS", f"agent_class {agent_class!r} is not supported", rel)
        if is_root and not data.get("name"):
            self.report.error("MISSING_NAME", "root agent needs a name", rel)

    def _check_keys(self, rel: str, data: dict, allowed: frozenset[str]) -> None:
        for key in data:
            if key in C.CODE_REFERENCE_KEYS:
                self.report.error("CODE_REFERENCE", f"{key!r} references Python code outside the sandbox", rel)
            elif key not in allowed:
                self.report.error("UNKNOWN_FIELD", f"field {key!r} is not in the ADK Agent Config schema", rel)

    def _validate_workflow_agent(self, rel: str, data: dict) -> None:
        self._check_keys(rel, data, C.WORKFLOW_AGENT_KEYS)
        self.report.warn("WORKFLOW_AGENT", f"{data.get('agent_class')} support in the harness is UNVERIFIED", rel)
        self._validate_sub_agents(rel, data.get("sub_agents"))

    def _validate_llm_agent(self, rel: str, data: dict) -> None:
        self._check_keys(rel, data, C.LLM_AGENT_KEYS)
        if not data.get("name"):
            self.report.error("MISSING_NAME", "agent needs a name", rel)
        elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(data["name"])):
            self.report.error("BAD_NAME", f"agent name {data['name']!r} must be a Python identifier", rel)

        model = data.get("model")
        if model is None:
            self.report.error("MISSING_MODEL", "every LlmAgent must set model", rel)
        elif model not in C.ALLOWED_MODELS:
            self.report.error("UNSUPPORTED_MODEL", f"model {model!r} not in {sorted(C.ALLOWED_MODELS)}", rel)

        enabled_tools: set[str] = set()
        text_blob = ""
        for key in ("instruction", "static_instruction"):
            if key in data:
                text = self._include_text(rel, data[key], key)
                if text is not None:
                    self._check_instruction(rel, key, text)
                    text_blob += text
        if "instruction" not in data and "static_instruction" not in data:
            self.report.warn("NO_INSTRUCTION", "agent has no instruction", rel)

        if "generate_content_config" in data:
            cfg = self._include_mapping(rel, data["generate_content_config"], "generate_content_config")
            if cfg is not None:
                for key in cfg:
                    if key not in C.GENERATE_CONTENT_KEYS:
                        self.report.warn("UNKNOWN_SAMPLING_FIELD", f"generate_content_config field {key!r} is unverified", rel)

        if "adapter" in data and data["adapter"] is not None:
            name = data["adapter"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}:
                self.report.error("BAD_ADAPTER_NAME", f"adapter {name!r} must be a plain directory name", rel)
            else:
                self.report.adapters.add(name)
                adapter_dir = self.root / "adapters" / name
                if not adapter_dir.is_dir():
                    self.report.error("MISSING_ADAPTER", f"adapters/{name}/ does not exist", rel)

        tools = data.get("tools") or []
        if not isinstance(tools, list):
            self.report.error("BAD_TYPE", "tools must be a list", rel)
            tools = []
        for tool in tools:
            enabled_tools |= self._validate_tool(rel, tool)
        self._validate_sub_agents(rel, data.get("sub_agents"))

        for tool_name in sorted(C.HARNESS_TOOLS - enabled_tools):
            if re.search(rf"\b{tool_name}\b", text_blob):
                self.report.warn("PROMPT_MENTIONS_DISABLED_TOOL", f"instruction mentions {tool_name!r} but it is not enabled", rel)

    def _check_instruction(self, rel: str, key: str, text: str) -> None:
        if not text.strip():
            self.report.error("EMPTY_INSTRUCTION", f"{key} is empty", rel)
        if key == "instruction":
            for match in ADK_STATE_PLACEHOLDER.finditer(text):
                if match.group(2) == "?":
                    continue
                self.report.error(
                    "ADK_STATE_PLACEHOLDER",
                    f"{match.group(0)!r} would be interpreted as a session-state variable by ADK",
                    rel,
                )

    def _validate_tool(self, rel: str, tool: Any) -> set[str]:
        if isinstance(tool, str):
            tool = {"name": tool}
        if not isinstance(tool, dict) or "name" not in tool:
            self.report.error("BAD_TOOL", f"tool entry {tool!r} must be a mapping with a name", rel)
            return set()
        extra = set(tool) - {"name", "args"}
        if extra:
            self.report.error("BAD_TOOL", f"tool entry has unknown fields {sorted(extra)}", rel)
        name = tool["name"]
        if name in C.HARNESS_TOOLS:
            if tool.get("args"):
                self.report.warn("TOOL_ARGS", f"harness tool {name!r} does not document args", rel)
            self.report.tools.add(name)
            return {name}
        if name in C.AGENT_TOOL_NAMES:
            if name != "AgentTool":
                self.report.warn("AGENT_TOOL_SPELLING", "tool name 'agent_tool' is unverified; ADK uses 'AgentTool'", rel)
            args = tool.get("args") or {}
            agent_ref = args.get("agent") if isinstance(args, dict) else None
            if isinstance(agent_ref, dict):
                if "code" in agent_ref:
                    self.report.error("CODE_REFERENCE", "AgentTool agent.code references Python code", rel)
                agent_ref = agent_ref.get("config_path")
            if not isinstance(agent_ref, str):
                self.report.error("BAD_TOOL", "AgentTool needs args.agent as a config path", rel)
                return set()
            target = self._resolve(posixpath.dirname(rel), agent_ref, "AgentTool agent")
            if target:
                self._validate_agent_file(target)
            return set()
        self.report.error("UNKNOWN_TOOL", f"tool {name!r} is not a competition harness tool or AgentTool", rel)
        return set()

    def _validate_sub_agents(self, rel: str, sub_agents: Any) -> None:
        if sub_agents is None:
            return
        if not isinstance(sub_agents, list):
            self.report.error("BAD_TYPE", "sub_agents must be a list", rel)
            return
        for ref in sub_agents:
            if not isinstance(ref, dict) or set(ref) - {"config_path", "code"}:
                self.report.error("BAD_SUB_AGENT", f"sub_agents entry {ref!r} must be {{config_path: ...}}", rel)
                continue
            if "code" in ref:
                self.report.error("CODE_REFERENCE", "sub_agents code reference is not allowed", rel)
                continue
            target = self._resolve(posixpath.dirname(rel), ref.get("config_path"), "sub_agents config_path")
            if target:
                self._validate_agent_file(target)

    # ---------------------------------------------------------- directories
    def _validate_root_entries(self) -> None:
        for entry in sorted(self.root.iterdir()):
            if entry.name not in C.ROOT_ENTRIES:
                self.report.warn("UNEXPECTED_ROOT_ENTRY", f"{entry.name!r} is not part of the documented layout", entry.name)

    def _validate_skills(self) -> None:
        skills_dir = self.root / "skills"
        if not skills_dir.exists():
            return
        for skill in sorted(p for p in skills_dir.iterdir()):
            rel = f"skills/{skill.name}"
            if not skill.is_dir():
                self.report.error("SKILL_NOT_DIR", "every entry under skills/ must be a directory", rel)
                continue
            manifest = skill / "SKILL.md"
            if not manifest.is_file():
                self.report.error("MISSING_SKILL_MANIFEST", "skill directory has no SKILL.md", rel)
                continue
            meta = self._frontmatter(manifest, f"{rel}/SKILL.md")
            if meta is None:
                continue
            name = meta.get("name")
            if not isinstance(name, str) or not name.strip():
                self.report.error("SKILL_MISSING_NAME", "SKILL.md frontmatter must define name", f"{rel}/SKILL.md")
                continue
            self.report.skills.append(name)
            if name != skill.name:
                self.report.warn("SKILL_NAME_MISMATCH", f"name {name!r} differs from directory {skill.name!r}", rel)
            if not SKILL_NAME.fullmatch(name):
                self.report.warn("SKILL_NAME_FORMAT", f"{name!r} is not lowercase-hyphenated", rel)
            if not meta.get("description"):
                self.report.warn("SKILL_MISSING_DESCRIPTION", "frontmatter has no description", rel)
            for script in sorted((skill / "scripts").glob("**/*.py")) if (skill / "scripts").is_dir() else []:
                srel = script.relative_to(self.root).as_posix()
                source = script.read_text(encoding="utf-8")
                try:
                    compile(source, srel, "exec")
                except SyntaxError as exc:
                    self.report.error("SCRIPT_SYNTAX", f"line {exc.lineno}: {exc.msg}", srel)
                if NETWORK_IMPORTS.search(source):
                    self.report.warn("SCRIPT_NETWORK_IMPORT", "script imports a network module; sandbox is offline", srel)

    def _frontmatter(self, path: Path, rel: str) -> dict | None:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", text, re.DOTALL)
        if not match:
            self.report.error("SKILL_NO_FRONTMATTER", "SKILL.md must start with YAML frontmatter", rel)
            return None
        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            self.report.error("SKILL_FRONTMATTER_PARSE", str(exc).splitlines()[0], rel)
            return None
        if not isinstance(meta, dict):
            self.report.error("SKILL_FRONTMATTER_PARSE", "frontmatter must be a mapping", rel)
            return None
        return meta

    def _validate_adapters(self) -> None:
        adapters_dir = self.root / "adapters"
        present = {p.name for p in adapters_dir.iterdir() if p.is_dir()} if adapters_dir.is_dir() else set()
        for name in sorted(self.report.adapters & present):
            base = adapters_dir / name
            rel = f"adapters/{name}"
            for required in C.ADAPTER_REQUIRED_FILES:
                if not (base / required).is_file():
                    self.report.error("ADAPTER_MISSING_FILE", f"missing {required}", rel)
            config_path = base / "adapter_config.json"
            if config_path.is_file():
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    self.report.error("ADAPTER_CONFIG_JSON", str(exc), rel)
                    config = {}
                base_model = str(config.get("base_model_name_or_path", ""))
                if "gemma-4-31b" not in base_model.lower():
                    self.report.warn("ADAPTER_BASE_MODEL", f"base_model_name_or_path {base_model!r} is not Gemma 4 31B", rel)
                if config.get("peft_type", "LORA") != "LORA":
                    self.report.error("ADAPTER_NOT_LORA", f"peft_type {config.get('peft_type')!r} is not LORA", rel)
            weights = base / "adapter_model.safetensors"
            if weights.is_file() and not _looks_like_safetensors(weights):
                self.report.error("ADAPTER_BAD_SAFETENSORS", "adapter_model.safetensors has an invalid header", rel)
        for name in sorted(present - self.report.adapters):
            self.report.warn("UNREFERENCED_ADAPTER", "adapter directory is not referenced by any agent", f"adapters/{name}")

    def _scan_files(self) -> None:
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            if path.is_symlink():
                self.report.error("SYMLINK", "symlinks are not allowed in the submission", rel)
                continue
            if not path.is_file():
                continue
            parts = set(PurePosixPath(rel).parts)
            if path.name in FORBIDDEN_NAMES or path.name.startswith(".env"):
                self.report.error("FORBIDDEN_FILE", "credential/environment files must not be shipped", rel)
            if parts & JUNK_PARTS or path.suffix == ".pyc":
                self.report.error("JUNK_FILE", "build or VCS artifact must not be shipped", rel)
            is_adapter_weight = rel.startswith("adapters/") and path.suffix == ".safetensors"
            if not is_adapter_weight and path.stat().st_size > MAX_NON_ADAPTER_FILE_BYTES:
                self.report.error("LARGE_FILE", f"{path.stat().st_size} bytes; only adapter weights may be large", rel)
            if path.suffix in TEXT_SUFFIXES or path.name == "SKILL.md":
                text = path.read_text(encoding="utf-8", errors="replace")
                for label, pattern in SECRET_PATTERNS.items():
                    if pattern.search(text):
                        self.report.error("POSSIBLE_SECRET", f"matches {label} pattern", rel)


def _looks_like_safetensors(path: Path) -> bool:
    with path.open("rb") as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            return False
        (header_len,) = struct.unpack("<Q", prefix)
        if header_len <= 0 or header_len > 100 * 1024 * 1024:
            return False
        header = handle.read(header_len)
    try:
        return isinstance(json.loads(header), dict)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


def validate_tree(root: Path) -> Report:
    if not root.is_dir():
        report = Report()
        report.error("NOT_A_DIRECTORY", f"{root} is not a directory")
        return report
    return _TreeValidator(root).run()


def validate_zip(zip_path: Path) -> Report:
    report = Report()
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, FileNotFoundError) as exc:
        report.error("BAD_ZIP", str(exc))
        return report
    with archive, tempfile.TemporaryDirectory(prefix="aeris_validate_") as tmp:
        names: set[str] = set()
        total = 0
        safe_members = []
        for info in archive.infolist():
            name = info.filename
            mode = info.external_attr >> 16
            if "\\" in name:
                report.error("BACKSLASH_PATH", "archive entry uses backslashes", name)
                continue
            normalized = posixpath.normpath(name)
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or normalized == ".." or normalized.startswith("../"):
                report.error("PATH_TRAVERSAL", "archive entry escapes the extraction root", name)
                continue
            if stat.S_ISLNK(mode):
                report.error("SYMLINK", "archive entry is a symlink", name)
                continue
            if normalized in names:
                report.error("DUPLICATE_ENTRY", "archive contains duplicate entry", name)
                continue
            names.add(normalized)
            total += info.file_size
            safe_members.append(info)
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            report.error("ARCHIVE_TOO_LARGE", f"uncompressed size {total} bytes")
            return report
        if "agent.yaml" not in names:
            nested = sorted(n for n in names if n.endswith("/agent.yaml"))
            hint = f" (found {nested[0]!r}; zip the directory contents, not the directory)" if nested else ""
            report.error("MISSING_AGENT_YAML", "agent.yaml must be at the archive root" + hint)
        for info in safe_members:
            archive.extract(info, tmp)
        tree_report = validate_tree(Path(tmp))
        tree_report.issues = report.issues + [i for i in tree_report.issues if i.code != "MISSING_AGENT_YAML" or "agent.yaml" in names]
        return tree_report


def validate_path(path: Path) -> Report:
    return validate_zip(path) if path.suffix == ".zip" else validate_tree(path)
