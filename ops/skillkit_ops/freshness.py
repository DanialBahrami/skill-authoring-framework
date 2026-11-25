"""Find skills affected by source changes, overdue reviews, and changed Confluence pages."""

from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
from pathlib import Path

from skillkit.model import Skill


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**` matches across folders, `*` and `?` within one. A pattern without wildcards
    matches the path itself and everything below it."""
    pattern = pattern.strip().lstrip("/")
    if not any(ch in pattern for ch in "*?["):
        return re.compile(re.escape(pattern.rstrip("/")) + r"(/.*)?$")
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append(r"(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(r".*")
            i += 2
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + "$")


def affected_skills(skills: list[Skill], repo: str, changed: list[str]) -> dict[str, list[str]]:
    """Map skill name -> changed paths that match one of its sources in `repo`."""
    hits: dict[str, list[str]] = {}
    changed = [c.strip().lstrip("/") for c in changed if c.strip()]
    for skill in skills:
        if skill.status == "deprecated":
            continue
        for src in skill.sources:
            if not isinstance(src, dict) or src.get("repo", "").lower() != repo.lower():
                continue
            patterns = [glob_to_regex(p) for p in src.get("paths", [])]
            for path in changed:
                if any(p.match(path) for p in patterns):
                    hits.setdefault(skill.name, [])
                    if path not in hits[skill.name]:
                        hits[skill.name].append(path)
    return hits


def stale_skills(skills: list[Skill], period_days: int, today: dt.date | None = None) -> list[tuple[str, str]]:
    today = today or dt.date.today()
    out = []
    for skill in skills:
        if skill.status != "active":
            continue
        reviewed = skill.last_reviewed
        if reviewed is None:
            out.append((skill.name, "no last_reviewed date"))
        elif (today - reviewed).days > period_days:
            out.append((skill.name, f"last reviewed {reviewed.isoformat()}, {(today - reviewed).days} days ago"))
    return out


def mark_reviewed(skill: Skill, today: dt.date | None = None) -> None:
    """Set last_reviewed in skill.yaml without rewriting the rest (keeps comments)."""
    path = skill.path / "skill.yaml"
    text = path.read_text(encoding="utf-8")
    stamp = (today or dt.date.today()).isoformat()
    new, n = re.subn(r"(?m)^last_reviewed:.*$", f"last_reviewed: {stamp}", text)
    if n == 0:
        new = text.rstrip("\n") + f"\nlast_reviewed: {stamp}\n"
    path.write_text(new, encoding="utf-8")


def dependents(names: set[str], uses: dict[str, list[str]]) -> set[str]:
    """Skills that use any of `names`, directly or through another skill."""
    found: set[str] = set()
    frontier = set(names)
    while frontier:
        nxt = {skill for skill, deps in uses.items() if frontier & set(deps)} - found - names
        found |= nxt
        frontier = nxt
    return found


def changed_skills(root: Path, base: str, all_names: list[str],
                   uses: dict[str, list[str]] | None = None) -> list[str]:
    """Skill names touched between `base` and HEAD, plus every skill that uses one of them
    (a changed building block can break the workflows that reference it). A change to shared
    context (workspace instructions, standard.yaml) affects every skill."""
    result = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=root,
                            capture_output=True, text=True, check=True)
    paths = [p for p in result.stdout.splitlines() if p]
    if any(p.startswith("context/") or p == "standard.yaml" for p in paths):
        return sorted(all_names)
    names = {p.split("/")[1] for p in paths if p.startswith("skills/") and p.count("/") >= 2}
    names = {n for n in names if n in all_names}
    if uses:
        names |= {d for d in dependents(names, uses) if d in all_names}
    return sorted(names)


# --- Confluence -----------------------------------------------------------------

def _confluence_session():
    import requests

    base = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
    if not base:
        raise SystemExit("set CONFLUENCE_BASE_URL (Cloud: https://<site>.atlassian.net/wiki, Data Center: https://<host>)")
    session = requests.Session()
    token = os.environ.get("CONFLUENCE_TOKEN", "")
    email = os.environ.get("CONFLUENCE_EMAIL")
    if email:      # Confluence Cloud: email + API token
        session.auth = (email, token)
    elif token:    # Data Center: personal access token
        session.headers["Authorization"] = f"Bearer {token}"
    return base, session


def confluence_changes(skills: list[Skill]) -> list[dict]:
    """Compare the recorded version of each Confluence source with the live page."""
    pages = []
    for skill in skills:
        if skill.status == "deprecated":
            continue
        for src in skill.sources:
            page = src.get("confluence") if isinstance(src, dict) else None
            if page and page.get("page_id"):
                pages.append((skill, page))
    if not pages:
        return []
    base, session = _confluence_session()
    changes = []
    for skill, page in pages:
        resp = session.get(f"{base}/rest/api/content/{page['page_id']}", params={"expand": "version"}, timeout=30)
        if resp.status_code == 404:
            changes.append({"skill": skill.name, "page_id": page["page_id"], "title": page.get("title", ""),
                            "recorded": page.get("version"), "current": None, "note": "page not found"})
            continue
        resp.raise_for_status()
        current = resp.json()["version"]["number"]
        if page.get("version") != current:
            changes.append({"skill": skill.name, "page_id": page["page_id"], "title": page.get("title", ""),
                            "recorded": page.get("version"), "current": current, "note": ""})
    return changes


def write_confluence_versions(skill: Skill, versions: dict[str, int]) -> None:
    """After a review, record the page versions the skill now matches."""
    path = skill.path / "skill.yaml"
    lines = path.read_text(encoding="utf-8").splitlines()
    current_page = None
    for i, line in enumerate(lines):
        m = re.search(r"page_id:\s*['\"]?(\w+)['\"]?", line)
        if m:
            current_page = m.group(1)
        m = re.match(r"^(\s*)version:\s*\S*\s*$", line)
        if m and current_page in versions:
            lines[i] = f"{m.group(1)}version: {versions[current_page]}"
            current_page = None
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
