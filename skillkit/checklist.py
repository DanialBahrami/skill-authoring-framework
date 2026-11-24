"""Generate the Genie Code check: prompts to paste and what to look for, per skill.

Evals call a model through a serving endpoint, not Genie Code itself. This checklist makes
the manual check in a real Agent-mode thread quick enough that it gets done.
"""

from __future__ import annotations

from .model import Skill


def _look_for(case: dict) -> list[str]:
    items = [f"Matches `{p}`" for p in case.get("must_include", []) or []]
    items += [f"Does not match `{p}`" for p in case.get("must_not_include", []) or []]
    items += list(case.get("rubric", []) or [])
    return items


def checklist_markdown(skills: list[Skill], prompts_per_skill: int = 2) -> str:
    lines = [
        "# Genie Code check",
        "",
        "For each skill: install the draft as a personal skill in "
        "`/Workspace/Users/<you>/.assistant/skills/<skill>/` (copy the folder without `skill.yaml` and `evals/`), "
        "start a new Agent-mode thread, open a file in the folder the task belongs to, paste each prompt, "
        "and tick what you see. 'Matches' and 'Does not match' are regular expressions.",
        "",
        "Every answer: [ ] the skill was used  [ ] real helpers and conventions, nothing invented  "
        "[ ] no hardcoded catalog, host or path  [ ] asked before anything destructive",
        "",
    ]
    for skill in skills:
        triggers = [c for c in skill.cases if c.get("type", "trigger") == "trigger"][:prompts_per_skill]
        lines += [f"## {skill.name}", ""]
        if skill.uses:
            lines += [f"Uses {', '.join(f'`{u}`' for u in skill.uses)}: check that Genie Code also follows "
                      "those skills at the step that names them.", ""]
        if not triggers:
            lines += ["No trigger cases in `evals/evals.json`; add two before checking.", ""]
        for case in triggers:
            agents = case.get("agents") or []
            lines += [f"**{case['id']}**" + (f" (open a file under `{agents[0].rsplit('/', 1)[0]}/`)" if agents else ""),
                      "", "```text", case["prompt"], "```", ""]
            lines += [f"- [ ] {item}" for item in _look_for(case)] or ["- [ ] The answer does the task as the skill describes"]
            lines.append("")
        lines += ["Result: [ ] passes  [ ] needs work: ____________________", ""]
    return "\n".join(lines)
