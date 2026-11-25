"""The skill map: every skill in the output folder, how they use each other, which chains are
tested as journeys, and the eval verdicts. Generated from the actual files, so it always matches
what was written; the meta-skill writes a planned version at Map and this replaces it at Check.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .model import Skill


def load_verdicts(path: Path | None) -> dict[str, str]:
    """Verdict per skill from an `eval --json` results file."""
    if not path or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {v["skill"]: v["verdict"] for v in data.get("verdicts", []) if "skill" in v}


def planned_changes(path: Path | None) -> dict[str, str]:
    """The "This run" column of a planned family table (decisions.md: new / updated / variant added / unchanged),
    so the generated map keeps what the run decided."""
    if not path or not path.is_file():
        return {}
    header: list[str] | None = None
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if "this run" not in header or set("".join(cells)) <= set("-: "):
            continue
        name = cells[0].strip("`")
        if name and not name.startswith("<"):
            out[name] = cells[header.index("this run")]
    return out


def map_markdown(skills: list[Skill], journeys: list[dict] | None = None, verdicts: dict[str, str] | None = None,
                 scope: str = "", this_run: dict[str, str] | None = None) -> str:
    skills = [s for s in skills if s.status != "deprecated"]
    journeys = journeys or []
    verdicts = verdicts or {}
    names = {s.name for s in skills}
    used_by: dict[str, list[str]] = {s.name: [] for s in skills}
    for s in skills:
        for dep in s.uses:
            used_by.setdefault(dep, []).append(s.name)

    def variants(s: Skill) -> str:
        return ", ".join(str(v.get("owner", "?")) for v in (s.meta.get("variants") or [])) or "-"

    def cell(items: list[str]) -> str:
        return ", ".join(f"`{i}`" for i in items) or "-"

    lines = [f"# Skill map{': ' + scope if scope else ''}", "",
             f"Generated from the skills in the output folder on {dt.date.today().isoformat()} "
             "(`catalog --map`). Arrows: a skill names the other at the step that needs it (`uses`); "
             "dashed arrows: a journey tests that chain end to end.", "",
             "| Skill | Status | Owner | Uses | Used by | Team variants | Verdict |" + (" This run |" if this_run else ""),
             "| --- | --- | --- | --- | --- | --- | --- |" + (" --- |" if this_run else "")]
    for s in sorted(skills, key=lambda k: k.name):
        lines.append(f"| `{s.name}` | {s.status} | {s.owner or '-'} | {cell(s.uses)} | "
                     f"{cell(sorted(used_by.get(s.name, [])))} | {variants(s)} | {verdicts.get(s.name, 'not evaluated')} |"
                     + (f" {this_run.get(s.name, 'unchanged')} |" if this_run else ""))

    ids = {name: f"s{i}" for i, name in enumerate(sorted(names), 1)}
    lines += ["", "```mermaid", "graph LR"]
    for s in sorted(skills, key=lambda k: k.name):
        label = s.name + (f"<br/>+ {variants(s)}" if variants(s) != "-" else "")
        shape = f'{ids[s.name]}(["{label}"])' if s.status == "draft" else f'{ids[s.name]}["{label}"]'
        lines.append(f"  {shape}")
    for s in sorted(skills, key=lambda k: k.name):
        for dep in s.uses:
            if dep in ids:
                lines.append(f"  {ids[s.name]} --> {ids[dep]}")
    tested = set()
    for j in journeys:
        chain = [n for n in j.get("skills", []) if n in ids]
        for a, b in zip(chain, chain[1:]):
            if (a, b) not in tested:
                tested.add((a, b))
                lines.append(f"  {ids[a]} -.->|{j.get('id', 'journey')}| {ids[b]}")
    lines += ["```", "",
              "Rounded boxes are drafts. A skill that nothing uses and that uses nothing stands on its own; "
              "check that it is a task people ask for, not a fragment."]
    loose = [s.name for s in skills if not s.uses and not used_by.get(s.name)]
    if journeys:
        in_journeys = {n for j in journeys for n in j.get("skills", [])}
        untested = [s.name for s in skills if s.uses and s.name not in in_journeys]
        if untested:
            lines += ["", "Skills that use others but appear in no journey: " + cell(sorted(untested)) + "."]
    if loose and len(skills) > 1:
        lines += ["", "Standalone skills: " + cell(sorted(loose)) + "."]
    return "\n".join(lines) + "\n"
