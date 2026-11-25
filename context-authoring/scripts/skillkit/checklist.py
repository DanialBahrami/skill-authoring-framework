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
    traj = case.get("trajectory") if isinstance(case.get("trajectory"), dict) else {}
    if traj.get("order"):
        items.append("Did these in this order: " + " → ".join(f"`{p}`" for p in traj["order"]))
    items += [f"Did not: {a}" for a in traj.get("avoid", []) or []]
    return items


READ_FILES = "- [ ] Read repo files to answer? no / yes: ____ (if yes, did the skill or the repo do the work?)"


def checklist_markdown(skills: list[Skill], prompts_per_skill: int = 2, journeys: list[dict] | None = None) -> str:
    lines = [
        "# Genie Code check",
        "",
        "For each skill: install the draft as a personal skill in "
        "`/Workspace/Users/<you>/.assistant/skills/<skill>/` (copy the folder without `skill.yaml` and `evals/`), "
        "start a new Agent-mode thread, open a file in the folder the task belongs to, paste each prompt, "
        "and tick what you see. 'Matches' and 'Does not match' are regular expressions. Judge the trajectory "
        "from what Genie Code actually read and ran in the thread, not only from its final answer.",
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
            lines += [READ_FILES, ""]
        if triggers:
            lines += ["**No file open**: if this task can start outside the repo (SQL editor, a new notebook), ask "
                      f"**{triggers[0]['id']}** once more with no repo file open. `AGENTS.md` does not load then, so the "
                      "skill must carry what it needs.", "",
                      "- [ ] Same result without a repo file open, or the task never starts outside the repo", ""]
        lines += ["Result: [ ] passes  [ ] needs work: ____________________", ""]
    if journeys:
        lines += ["## Journeys", "",
                  "Tasks that span several skills. This is the only check of whether Genie Code loads a skill named "
                  "in another skill's steps: the simulated evals load them all up front.", ""]
        for j in journeys:
            lines += [f"**{j['id']}**", "", "```text", j["prompt"], "```", ""]
            lines += [f"- [ ] Used `{name}`" + (" first" if k == 0 else "") for k, name in enumerate(j["skills"])]
            lines += [f"- [ ] {item}" for item in _look_for(j)]
            lines += [READ_FILES, "- [ ] Result: passes / needs work: ____", ""]
    return "\n".join(lines)
