"""Checks for skills, the skill catalog, workspace instructions and AGENTS.md files.

Each finding has a code so reviewers and docs can refer to it:

  SK001-SK023  one skill
  CT001-CT004  the catalog of skills
  WI001-WI003  workspace instructions
  AG001-AG002  AGENTS.md files
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from .model import (
    EVALS_FILE,
    SPEC_FRONTMATTER,
    STATUSES,
    Skill,
    Standard,
    estimate_tokens,
)

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){2,}$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
TODO_RE = re.compile(r"\bTODO\b")
CONTENTS_RE = re.compile(r"(?im)^#{1,6}\s*contents\b")
ALLOWED_FRONTMATTER = set(SPEC_FRONTMATTER)   # Agent Skills specification fields
WORD_RE = re.compile(r"[a-z0-9]+")
# Assertions an eval model cannot satisfy without running anything: live values and lookups.
UNVERIFIABLE_ASSERTION_RES = [
    re.compile(r"(?i)\b(latest|newest|most recent|today'?s|current)\b.*\b(branch|date|version|run|release)\b"),
    re.compile(r"(?i)\b(lists?|names?|returns?|shows?)\b.*\b(actual|existing|downstream|live)\b.*"
               r"\b(tables?|views?|rows?|jobs?|columns?|values?)\b"),
    re.compile(r"(?i)\b(row|record) counts?\b|\bhow many rows\b"),
]
# ...unless the assertion asks for the way to find out, which the model can give.
ASKS_FOR_METHOD_RE = re.compile(r"(?i)\b(query|queries|sql|command|statement|step|steps|how to|code)\b")
STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "when", "use", "user", "asks",
             "is", "it", "this", "that", "by", "as", "from", "not", "skill", "be", "are", "any", "into"}

# Agent Skills enterprise guidance: these patterns need a security reviewer's attention.
SECURITY_PATTERNS = [
    ("network call", re.compile(r"\b(requests\.(get|post|put|delete)|urllib|curl |wget |fetch\()")),
    ("external URL", re.compile(r"https?://")),
    # %run of repo notebooks is expected, quoted or not: %run ../x, %run "../x", %run '../x'
    ("path outside the skill", re.compile(r"(?<!%run )(?<!%run \")(?<!%run ')\.\./")),
]


@dataclass
class Finding:
    code: str
    severity: str  # "error" or "warning"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7} {self.code} {self.where}: {self.message}"


def _err(out: list[Finding], code: str, where: str, msg: str) -> None:
    out.append(Finding(code, "error", where, msg))


def _warn(out: list[Finding], code: str, where: str, msg: str) -> None:
    out.append(Finding(code, "warning", where, msg))


def _local_links(text: str) -> list[str]:
    links = []
    for target in LINK_RE.findall(text):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue  # URL or in-page anchor
        links.append(target.split("#", 1)[0])
    return [link for link in links if link]


def lint_skill(skill: Skill, std: Standard) -> list[Finding]:
    out: list[Finding] = []
    where = f"skills/{skill.name}"

    if not (skill.path / "SKILL.md").is_file():
        _err(out, "SK001", where, "SKILL.md is missing")
        return out
    for problem in skill.parse_errors:
        _err(out, "SK001", where, problem)

    # Frontmatter
    extra = set(skill.frontmatter) - ALLOWED_FRONTMATTER
    if extra:
        _err(out, "SK002", where, f"frontmatter fields not in the Agent Skills specification: {', '.join(sorted(extra))}")
    meta_field = skill.frontmatter.get("metadata")
    if meta_field is not None and not (isinstance(meta_field, dict)
                                       and all(isinstance(v, (str, int, float)) for v in meta_field.values())):
        _err(out, "SK002", where, "metadata must map string keys to string values")
    compat = skill.frontmatter.get("compatibility")
    if compat is not None and not 1 <= len(str(compat)) <= 500:
        _err(out, "SK002", where, "compatibility must be 1-500 characters")
    name = str(skill.frontmatter.get("name", ""))
    if name != skill.name:
        _err(out, "SK003", where, f"frontmatter name '{name}' must equal the folder name '{skill.name}'")
    if not NAME_RE.match(skill.name):
        _err(out, "SK003", where, "name must be <team-prefix>-<verb>-<object>: lowercase words joined by hyphens, at least three")
    if len(skill.name) > std.limit("name_max_chars"):
        _err(out, "SK003", where, f"name is longer than {std.limit('name_max_chars')} characters")
    team = std.team_for_prefix(skill.name)
    if team is None:
        _err(out, "SK004", where, f"prefix '{skill.name.split('-', 1)[0]}' is not registered in standard.yaml")

    desc = skill.description
    lo, hi = std.limit("description_min_chars"), std.limit("description_max_chars")
    if not lo <= len(desc) <= hi:
        _err(out, "SK005", where, f"description is {len(desc)} characters; allowed {lo}-{hi}")
    if "use when" not in desc.lower():
        _err(out, "SK006", where, "description must contain 'Use when' followed by the situations and terms people type")

    # Body size
    body = skill.body.strip("\n")
    lines = body.count("\n") + 1 if body else 0
    if lines > std.limit("body_max_lines"):
        _err(out, "SK007", where, f"SKILL.md body has {lines} lines; limit {std.limit('body_max_lines')}. Move detail to references/")
    tokens = estimate_tokens(body)
    if tokens > std.limit("body_max_tokens"):
        _err(out, "SK008", where, f"SKILL.md body is about {tokens} tokens; limit {std.limit('body_max_tokens')}")

    # Sections
    headings = [h.strip() for h in H2_RE.findall(body)]
    required, optional = std.required_sections, std.optional_sections
    positions = []
    for section in required:
        if section not in headings:
            _err(out, "SK009", where, f"required section '## {section}' is missing")
        else:
            positions.append(headings.index(section))
    if positions != sorted(positions):
        _err(out, "SK009", where, f"required sections must appear in this order: {', '.join(required)}")
    for heading in headings:
        if heading not in required and heading not in optional:
            _err(out, "SK009", where, f"section '## {heading}' is not allowed; use {', '.join(required + optional)}")

    # Links from SKILL.md resolve; reference files do not link further
    for target in _local_links(skill.body):
        if not (skill.path / target).exists():
            _err(out, "SK010", where, f"link target '{target}' does not exist")
    ref_dir = skill.path / "references"
    if ref_dir.is_dir():
        for ref in sorted(ref_dir.rglob("*.md")):
            text = ref.read_text(encoding="utf-8")
            rel = ref.relative_to(skill.path).as_posix()
            if _local_links(text):
                _err(out, "SK011", f"{where}/{rel}", "reference files must not link to other files; link everything from SKILL.md")
            n_lines = text.count("\n") + 1
            if n_lines > std.limit("reference_toc_after_lines"):
                head = "\n".join(text.splitlines()[:15])
                if not CONTENTS_RE.search(head):
                    _err(out, "SK012", f"{where}/{rel}", f"{n_lines} lines; files over {std.limit('reference_toc_after_lines')} lines start with a '## Contents' list")
        unlinked = [r.relative_to(skill.path).as_posix() for r in ref_dir.rglob("*.md")
                    if r.relative_to(skill.path).as_posix() not in _local_links(skill.body)]
        for rel in unlinked:
            _warn(out, "SK010", where, f"{rel} is not linked from SKILL.md, so the agent will not know when to open it")

    # Forbidden patterns in everything deployed
    for path in skill.runtime_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(skill.path).as_posix()
        if path.name == "SKILL.md":
            text = skill.body  # frontmatter is checked by SK005/SK006 only
        for label, pattern in std.forbidden("skills"):
            match = pattern.search(text)
            if match:
                _err(out, "SK013", f"{where}/{rel}", f"contains {label}: '{match.group(0)}'")
        if skill.status == "active" and TODO_RE.search(text):
            _err(out, "SK017", f"{where}/{rel}", "active skills must not contain TODO markers")

    # skill.yaml
    meta = skill.meta
    if not (skill.path / "skill.yaml").is_file():
        _err(out, "SK014", where, "skill.yaml is missing")
    else:
        if meta.get("owner") != team and team is not None:
            _err(out, "SK014", where, f"owner must be '{team}', the team registered for this prefix")
        if meta.get("status") not in STATUSES:
            _err(out, "SK014", where, f"status must be one of {', '.join(STATUSES)}")
        if skill.last_reviewed is None:
            _err(out, "SK014", where, "last_reviewed must be a date (YYYY-MM-DD)")
        elif skill.last_reviewed > dt.date.today():
            _err(out, "SK014", where, "last_reviewed is in the future")
        sources = skill.sources
        if not sources:
            _err(out, "SK014", where, "sources must list where the knowledge came from")
        for i, src in enumerate(sources):
            if not isinstance(src, dict):
                _err(out, "SK014", where, f"sources[{i}] must be a mapping")
                continue
            if "repo" in src:
                if not src.get("paths"):
                    _err(out, "SK014", where, f"sources[{i}] (repo {src['repo']}) needs a non-empty paths list")
            elif "confluence" in src:
                page = src["confluence"] or {}
                if not page.get("page_id"):
                    _err(out, "SK014", where, f"sources[{i}] confluence entry needs page_id")
                if "version" not in page:
                    _warn(out, "SK014", where, f"sources[{i}] confluence entry has no version; changes to the page cannot be detected")
            elif "doc" in src:
                doc = src["doc"] or {}
                if not doc.get("url") and not doc.get("title"):
                    _err(out, "SK014", where, f"sources[{i}] doc entry needs a url or title")
            elif "note" not in src:
                _err(out, "SK014", where, f"sources[{i}] must have repo, confluence, doc or note")

        # Variants owned by other teams
        for name in skill.supersedes:
            if name == skill.name:
                _err(out, "SK022", where, "a skill cannot supersede itself")
        for i, var in enumerate(meta.get("variants", []) or []):
            ref = var.get("reference", "")
            if not (skill.path / ref).is_file():
                _err(out, "SK016", where, f"variants[{i}] reference '{ref}' does not exist")
            if var.get("owner") not in std.teams:
                _err(out, "SK016", where, f"variants[{i}] owner '{var.get('owner')}' is not a team in standard.yaml")
            if ref and ref not in _local_links(skill.body):
                _err(out, "SK016", where, f"variant reference '{ref}' must be linked from SKILL.md with the condition that selects it")

    # evals/evals.json
    if not (skill.path / EVALS_FILE).is_file():
        _err(out, "SK015", where, f"{EVALS_FILE} is missing")
    else:
        cases = skill.cases
        ids = [c.get("id") for c in cases]
        if len(ids) != len(set(ids)) or None in ids:
            _err(out, "SK015", where, "every eval case needs a unique id")
        triggers = [c for c in cases if c.get("type") == "trigger"]
        near = [c for c in cases if c.get("type") == "near_miss"]
        if len(triggers) < 2:
            _err(out, "SK015", where, f"needs at least 2 trigger cases; found {len(triggers)}")
        if len(near) < 1:
            _err(out, "SK015", where, "needs at least 1 near_miss case")
        for case in cases:
            if case.get("type") not in ("trigger", "near_miss"):
                _err(out, "SK015", where, f"case {case.get('id')}: type must be trigger or near_miss")
            if not str(case.get("prompt", "")).strip():
                _err(out, "SK015", where, f"case {case.get('id')}: prompt is empty")
            if case.get("type") == "trigger" and not (case.get("must_include") or case.get("rubric")):
                _err(out, "SK015", where, f"case {case.get('id')}: trigger cases need must_include or assertions")
            for item in case.get("rubric", []) or []:
                if any(r.search(str(item)) for r in UNVERIFIABLE_ASSERTION_RES) and not ASKS_FOR_METHOD_RE.search(str(item)):
                    _warn(out, "SK023", where, f"case {case.get('id')}: '{item}' needs facts the model cannot know "
                          "without running anything; expect the query or the step instead")
            for key in ("must_include", "must_not_include"):
                for pattern in case.get(key, []) or []:
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        _err(out, "SK015", where, f"case {case.get('id')}: bad regex in {key}: {exc}")

    # Folder hygiene
    for child in skill.path.iterdir():
        if child.name.startswith(".") or child.name == "__pycache__":
            continue
        allowed = {"SKILL.md", "skill.yaml", "evals", "references", "assets", "scripts"}
        if child.name not in allowed:
            _err(out, "SK018", where, f"'{child.name}' is not part of the skill layout")

    # Security review signals (warnings: they need a reviewer, not a rejection)
    if (skill.path / "scripts").is_dir() and any((skill.path / "scripts").rglob("*")):
        _warn(out, "SK020", where, "contains scripts: security review required (scripts run with the user's access)")
    for path in skill.runtime_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(skill.path).as_posix()
        for label, pattern in SECURITY_PATTERNS:
            match = pattern.search(text)
            if match:
                _warn(out, "SK020", f"{where}/{rel}", f"{label} ('{match.group(0).strip()}'): security review required")

    if skill.status == "deprecated":
        _warn(out, "SK019", where, "deprecated: not deployed; remove the folder when no longer needed")
    return out


def lint_uses(skill: Skill, by_name: dict[str, Skill]) -> list[Finding]:
    """`uses` in skill.yaml must match the skills named in the body, exist, and be deployable."""
    out: list[Finding] = []
    where = f"skills/{skill.name}"
    body = skill.body
    for dep in skill.uses:
        if dep == skill.name:
            _err(out, "SK021", where, "a skill cannot use itself")
            continue
        if dep not in by_name:
            _err(out, "SK021", where, f"uses unknown skill '{dep}'")
            continue
        if not re.search(rf"(?<![\w-]){re.escape(dep)}(?![\w-])", body):
            _err(out, "SK021", where, f"uses '{dep}' but never names it in SKILL.md; name it at the step that needs it")
        if skill.status == "active" and by_name[dep].status != "active":
            _err(out, "SK021", where, f"active skill uses '{dep}', which is {by_name[dep].status}")
    for other in by_name:
        if other != skill.name and other not in skill.uses and re.search(rf"(?<![\w-]){re.escape(other)}(?![\w-])", body):
            _err(out, "SK021", where, f"names skill '{other}' in SKILL.md but does not list it in uses")
    return out


def lint_catalog(skills: list[Skill], std: Standard) -> list[Finding]:
    out: list[Finding] = []
    active = [s for s in skills if s.status == "active"]
    total = sum(estimate_tokens(f"{s.name}: {s.description}") for s in active)
    budget = std.limit("catalog_max_tokens")
    if total > budget:
        _err(out, "CT001", "catalog", f"active skill descriptions total about {total} tokens; budget {budget}. Merge or retire a skill")
    elif total > 0.8 * budget:
        _warn(out, "CT001", "catalog", f"active skill descriptions use {total} of {budget} tokens")
    # Drafts are the planned catalog: warn before they are activated, not after.
    superseded = {n for s in skills if s.status != "deprecated" for n in s.supersedes}
    planned = [s for s in skills if s.status in ("active", "draft") and s.name not in superseded]
    planned_total = sum(estimate_tokens(f"{s.name}: {s.description}") for s in planned)
    if planned_total > budget and total <= budget:
        _warn(out, "CT001", "catalog", f"active and draft skill descriptions together total about {planned_total} "
              f"tokens; budget {budget}. Merge drafts or retire skills before activating them all. "
              "Skills already installed in the workspace count too: `skillkit catalog --installed <folder>`")
    by_status = {s.name: s.status for s in skills}
    for s in skills:
        for name in s.supersedes:
            if s.status == "active" and by_status.get(name) == "active":
                _warn(out, "SK022", f"skills/{s.name}", f"supersedes '{name}', which is still active; deprecate it "
                      "so the two do not compete for the same prompts")
    names = [s.name for s in skills]
    dupes = {n for n in names if names.count(n) > 1}
    for name in dupes:
        _err(out, "CT002", "catalog", f"duplicate skill name {name}")

    # Overlapping descriptions compete for the same prompts (coexistence)
    threshold = float(std.raw.get("catalog", {}).get("overlap_warning", 0.5))
    live = [s for s in skills if s.status != "deprecated"]
    words = {s.name: {w for w in WORD_RE.findall(s.description.lower()) if w not in STOPWORDS} for s in live}
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            wa, wb = words[a.name], words[b.name]
            if wa and wb:
                jaccard = len(wa & wb) / len(wa | wb)
                if jaccard >= threshold:
                    _warn(out, "CT003", "catalog", f"descriptions of {a.name} and {b.name} overlap ({jaccard:.0%}); "
                          "check the routing eval and add 'Not for ...' clauses")

    # Dependencies: no cycles, limited depth, platform skills do not depend on team skills
    by_name = {s.name: s for s in skills}
    max_depth = int(std.raw.get("catalog", {}).get("max_dependency_depth", 2))
    platform = std.platform_team

    def depth(name: str, seen: tuple[str, ...]) -> int:
        if name in seen:
            raise ValueError(" -> ".join(seen + (name,)))
        deps = [d for d in by_name[name].uses if d in by_name] if name in by_name else []
        return 0 if not deps else 1 + max(depth(d, seen + (name,)) for d in deps)

    for s in skills:
        try:
            d = depth(s.name, ())
        except ValueError as cycle:
            _err(out, "CT004", "catalog", f"dependency cycle: {cycle}")
            continue
        if d > max_depth:
            _err(out, "CT004", "catalog", f"{s.name} has dependency depth {d}; limit {max_depth}")
        for dep in s.uses:
            if dep in by_name and s.owner == platform and by_name[dep].owner not in ("", platform):
                _err(out, "CT004", "catalog", f"platform skill {s.name} depends on team skill {dep}")
    return out


def lint_workspace_instructions(path: Path, std: Standard) -> list[Finding]:
    out: list[Finding] = []
    where = path.as_posix()
    if not path.is_file():
        _err(out, "WI001", where, "workspace instructions file is missing")
        return out
    text = path.read_text(encoding="utf-8")
    hard = std.limit("workspace_instructions_max_chars")
    if len(text) > hard:
        _err(out, "WI001", where, f"{len(text)} characters; Databricks ignores everything past {hard}")
    tokens = estimate_tokens(text)
    if tokens > std.limit("workspace_instructions_max_tokens"):
        _err(out, "WI002", where, f"about {tokens} tokens; budget {std.limit('workspace_instructions_max_tokens')} (paid on every response)")
    for label, pattern in std.forbidden("context"):
        match = pattern.search(text)
        if match:
            _err(out, "WI003", where, f"contains {label}: '{match.group(0)}'")
    if "<!-- EXAMPLE" in text:
        _warn(out, "WI004", where, "still the framework's example: evals refuse to run and build refuses to deploy "
              "until it holds your workspace's real instructions (or nothing) and the marker is removed")
    return out


def lint_agents_md(path: Path, std: Standard) -> list[Finding]:
    out: list[Finding] = []
    where = path.as_posix()
    text = path.read_text(encoding="utf-8")
    n_lines = text.count("\n") + 1
    if n_lines > std.limit("agents_md_max_lines"):
        _err(out, "AG001", where, f"{n_lines} lines; limit {std.limit('agents_md_max_lines')}. Move task detail into skills")
    for label, pattern in std.forbidden("context"):
        match = pattern.search(text)
        if match:
            _err(out, "AG002", where, f"contains {label}: '{match.group(0)}'")
    return out


def lint_journeys(root, skills: list[Skill]) -> list[Finding]:
    """evals/journeys.json: unique ids, a prompt, at least two known, non-deprecated skills."""
    import json

    out: list[Finding] = []
    path = root / "evals" / "journeys.json"
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _err(out, "JR001", "evals/journeys.json", f"not valid JSON: {exc}")
        return out
    status = {s.name: s.status for s in skills}
    uses = {s.name: s.uses for s in skills}
    seen: set[str] = set()
    for i, j in enumerate(data.get("journeys", []) or []):
        where = f"evals/journeys.json[{j.get('id', i)}]"
        jid = str(j.get("id", ""))
        if not jid or jid in seen:
            _err(out, "JR001", where, "every journey needs a unique id")
        seen.add(jid)
        if not str(j.get("prompt", "")).strip():
            _err(out, "JR001", where, "prompt is missing")
        names = [str(n) for n in (j.get("skills") or [])]
        if len(names) < 2:
            _err(out, "JR001", where, "a journey lists at least two skills, the first one being where it starts")
        for name in names:
            if name not in status:
                _err(out, "JR001", where, f"unknown skill '{name}'")
            elif status[name] == "deprecated":
                _err(out, "JR001", where, f"skill '{name}' is deprecated")
        for key in ("must_include", "must_not_include"):
            for pattern in j.get(key) or []:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    _err(out, "JR001", where, f"bad regex in {key}: {exc}")
        if not (j.get("must_include") or j.get("assertions")):
            _warn(out, "JR001", where, "no must_include or assertions: the journey can only fail on routing")
        # Genie Code reaches a later skill only if an earlier one names it (listed in `uses`).
        if names and names[0] in status:
            reach, todo = set(), [names[0]]
            while todo:
                cur = todo.pop()
                if cur in reach or cur not in uses:
                    continue
                reach.add(cur)
                todo += uses[cur]
            for name in names[1:]:
                if name in status and name not in reach:
                    _warn(out, "JR002", where, f"'{name}' is not reachable from '{names[0]}' through `uses`: Genie Code "
                          "would have to pick it on its own. Name it at the step that needs it, or drop it from the journey")
    return out
