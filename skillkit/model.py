"""Load the repo: standard.yaml, skills, workspace instructions."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RUNTIME_DIRS = ("references", "assets", "scripts")
REPO_ONLY = ("skill.yaml", "evals")          # never deployed
EVALS_FILE = "evals/evals.json"              # Agent Skills convention
STATUSES = ("draft", "active", "deprecated")
SPEC_FRONTMATTER = ("name", "description", "license", "compatibility", "metadata", "allowed-tools")

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


def estimate_tokens(text: str) -> int:
    """Token estimate used everywhere in the standard: characters / 4."""
    return (len(text) + 3) // 4


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` to the folder that holds standard.yaml."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "standard.yaml").is_file():
            return candidate
    raise FileNotFoundError("standard.yaml not found; run skillkit inside the genie-context repo or pass --root")


@dataclass
class Standard:
    raw: dict[str, Any]

    @property
    def limits(self) -> dict[str, int]:
        return self.raw.get("limits", {})

    def limit(self, key: str) -> int:
        return int(self.limits[key])

    @property
    def prefixes(self) -> dict[str, str]:
        return self.raw.get("prefixes", {})

    @property
    def teams(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("teams", {})

    @property
    def platform_team(self) -> str:
        return self.raw.get("platform_team", "")

    @property
    def review_period_days(self) -> int:
        return int(self.raw.get("review_period_days", 120))

    @property
    def required_sections(self) -> list[str]:
        return list(self.raw.get("sections", {}).get("required", ["Steps", "Verify"]))

    @property
    def optional_sections(self) -> list[str]:
        return list(self.raw.get("sections", {}).get("optional", ["Rules", "Examples", "References"]))

    def forbidden(self, kind: str = "skills") -> list[tuple[str, re.Pattern[str]]]:
        key = "forbidden_patterns" if kind == "skills" else "forbidden_patterns_context"
        return [(p["name"], re.compile(p["regex"])) for p in self.raw.get(key, [])]

    @property
    def workspace(self) -> dict[str, str]:
        return self.raw.get("workspace", {})

    @property
    def eval(self) -> dict[str, Any]:
        return self.raw.get("eval", {})

    def team_for_prefix(self, name: str) -> str | None:
        return self.prefixes.get(name.split("-", 1)[0])

    @property
    def manifest_path(self) -> str:
        return self.workspace.get("manifest_path", "/Workspace/.assistant/genie-context-manifest.json")


def load_standard(root: Path) -> Standard:
    return Standard(yaml.safe_load((root / "standard.yaml").read_text(encoding="utf-8")) or {})


@dataclass
class Skill:
    name: str
    path: Path
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    raw: str = ""
    meta: dict[str, Any] = field(default_factory=dict)   # skill.yaml
    evals: dict[str, Any] = field(default_factory=dict)  # evals/evals.json
    parse_errors: list[str] = field(default_factory=list)

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description", "") or "").strip()

    @property
    def status(self) -> str:
        return str(self.meta.get("status", "draft"))

    @property
    def owner(self) -> str:
        return str(self.meta.get("owner", ""))

    @property
    def sources(self) -> list[dict[str, Any]]:
        return list(self.meta.get("sources", []) or [])

    @property
    def cases(self) -> list[dict[str, Any]]:
        """Eval cases from evals/evals.json, normalized. `assertions` are judged by an LLM;
        `must_include` / `must_not_include` are regexes; `type` is trigger (default) or near_miss."""
        out = []
        for raw in self.evals.get("evals", []) or []:
            case = dict(raw)
            case["id"] = str(case.get("id", ""))
            case.setdefault("type", "trigger")
            case["rubric"] = list(case.get("assertions", []) or [])
            out.append(case)
        return out

    @property
    def uses(self) -> list[str]:
        return [str(u) for u in (self.meta.get("uses", []) or [])]

    @property
    def supersedes(self) -> list[str]:
        """Skills this one replaces once active: repo skills or skills already installed in the workspace."""
        return [str(u) for u in (self.meta.get("supersedes", []) or [])]

    @property
    def eval_max_tokens(self) -> int | None:
        """Per-skill answer limit for evals (skill.yaml `eval: {max_tokens: N}`), for tasks that span several files."""
        value = (self.meta.get("eval") or {}).get("max_tokens")
        return int(value) if value else None

    @property
    def requires(self) -> list[str]:
        return [str(r) for r in (self.meta.get("requires", []) or [])]

    @property
    def last_reviewed(self) -> dt.date | None:
        value = self.meta.get("last_reviewed")
        if isinstance(value, dt.date):
            return value
        try:
            return dt.date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def runtime_files(self) -> list[Path]:
        """Every file that is deployed to the workspace for this skill."""
        files = [self.path / "SKILL.md"]
        for sub in RUNTIME_DIRS:
            folder = self.path / sub
            if folder.is_dir():
                files += sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        return files

    def reference_text(self) -> str:
        """SKILL.md body plus every reference file, as the agent would see after opening them."""
        parts = [self.body]
        ref_dir = self.path / "references"
        if ref_dir.is_dir():
            for ref in sorted(ref_dir.rglob("*.md")):
                parts.append(f"\n\n--- {ref.relative_to(self.path).as_posix()} ---\n{ref.read_text(encoding='utf-8')}")
        for sub in ("assets", "scripts"):
            folder = self.path / sub
            if folder.is_dir():
                names = ", ".join(p.relative_to(self.path).as_posix() for p in sorted(folder.rglob("*")) if p.is_file())
                if names:
                    parts.append(f"\n\n--- {sub} available: {names} ---")
        return "".join(parts)


def parse_skill_md(text: str) -> tuple[dict[str, Any], str, list[str]]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text, ["SKILL.md has no YAML frontmatter between --- lines"]
    try:
        front = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return {}, match.group(2), [f"frontmatter is not valid YAML: {exc}"]
    if not isinstance(front, dict):
        return {}, match.group(2), ["frontmatter must be a mapping"]
    return front, match.group(2), []


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    import json

    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name} is not valid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.name} must be a JSON object")
        return {}
    return data


def _load_yaml(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        errors.append(f"{path.name} is not valid YAML: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.name} must be a mapping")
        return {}
    return data


def load_skill(folder: Path) -> Skill:
    skill = Skill(name=folder.name, path=folder)
    skill_md = folder / "SKILL.md"
    if skill_md.is_file():
        skill.raw = skill_md.read_text(encoding="utf-8")
        skill.frontmatter, skill.body, errs = parse_skill_md(skill.raw)
        skill.parse_errors += errs
    skill.meta = _load_yaml(folder / "skill.yaml", skill.parse_errors)
    skill.evals = _load_json(folder / EVALS_FILE, skill.parse_errors)
    return skill


def load_skills(root: Path, names: list[str] | None = None) -> list[Skill]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return []
    folders = sorted(p for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
    if names:
        wanted = set(names)
        missing = wanted - {f.name for f in folders}
        if missing:
            raise SystemExit(f"unknown skill(s): {', '.join(sorted(missing))}")
        folders = [f for f in folders if f.name in wanted]
    return [load_skill(f) for f in folders]


def workspace_instructions_path(root: Path) -> Path:
    return root / "context" / "workspace-instructions.md"


EXAMPLE_MARKER = "<!-- EXAMPLE"


def is_example_instructions(root: Path) -> bool:
    """True while context/workspace-instructions.md is still the framework's example. Evals inject
    this file into every answer, so example values (catalog names, rules) would leak into them, and
    deploying it would replace the workspace's real instructions."""
    path = workspace_instructions_path(root)
    return path.is_file() and EXAMPLE_MARKER in path.read_text(encoding="utf-8")


EXAMPLE_INSTRUCTIONS_HELP = (
    "context/workspace-instructions.md is still the framework's example (it contains '<!-- EXAMPLE'). "
    "Copy your workspace's real instructions (/Workspace/.assistant_workspace_instructions.md) into it, "
    "or leave it empty if the workspace has none, and remove the marker.")


@dataclass
class InstalledSkill:
    """A skill already installed in a workspace skills folder, outside this repo."""
    name: str
    description: str
    path: Path


def load_installed(folder: Path, exclude: set[str] | None = None) -> list[InstalledSkill]:
    """Read name and description of every skill in an installed skills folder, for example
    /Workspace/.assistant/skills in a notebook, or a local export of it. Skills named in
    `exclude` (this repo's own, already deployed) are left out."""
    out: list[InstalledSkill] = []
    if not folder.is_dir():
        raise SystemExit(f"installed skills folder not found: {folder}")
    for skill_md in sorted(folder.glob("*/SKILL.md")):
        front, _, _ = parse_skill_md(skill_md.read_text(encoding="utf-8"))
        name = str(front.get("name") or skill_md.parent.name)
        if exclude and name in exclude:
            continue
        out.append(InstalledSkill(name, str(front.get("description", "") or "").strip(), skill_md.parent))
    return out
