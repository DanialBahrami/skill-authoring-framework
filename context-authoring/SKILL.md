---
name: context-authoring
description: >-
  Analyzes a code repository and its documentation and builds the Agent Skills family it
  needs, so a coding agent can do the team's recurring tasks without reading the source:
  it identifies the tasks people repeat, writes one self-contained skill per task with eval
  cases that prove it helps, and proposes AGENTS.md lines, always-on instructions and data
  catalog comments. Use when the user wants skills, a skill pack or agent context for a
  repo, team or domain, wants documentation or a codebase turned into skills, or wants
  existing skills extended or updated after code changes or a wrong answer, even if they
  only ask to make the agent understand the repo.
---

# Context authoring

You are the **author agent**. You have the repo: its code, docs and history, and people you can ask. The **consumer agent** that uses your skills later must not need any of that. Each time it reads the code to find a convention, it spends tokens and guesses from whatever files it happened to open. Your job is to find the tasks people repeat, capture what the consumer needs for each one, and bake it into skills, so it does the task from the skill alone.

**Golden rule.** Write for a consumer that does not read the source. Everything a task needs is inside its skill: real signatures, complete examples, vocabularies with their consequences, the order of steps, the guards. If the consumer has to open the code to finish the task, the skill has failed. Every line is also **sourced** (a file, a page or a person), **placed once** in the cheapest layer that works, and **proven** by an eval to change the answer.

**Inputs.** The source repo and the folders in scope, the owning team and its skill prefix, the docs (a connector, Markdown in the repo, or exported pages), and the output folder: the one the user names, otherwise `workspace.output_folder` from the settings. Say in your first reply where output goes. Ask only for what you cannot find.

**Boundaries.** Never write to the source repo, the installed skills, the always-on instructions or the data catalog: you propose, their owners apply. Do not stop between steps for review; people review the finished run in `report.md`. Only when the settings say `review: before-write`, stop after step 3 and ask for a review of `inventory.md` and `decisions.md`.

**Tooling.** The checks are scripts in this skill's `scripts/` folder; nothing to install. Settings (limits, team prefixes, platform paths, eval models) come from `assets/defaults/standard.yaml`, overridden by a `standard.yaml` in the output folder.

```python
import sys; sys.path.insert(0, "<this skill's folder>/scripts")
from skillkit.cli import main
main(["--root", "<output folder>", "init", "--scope", "<scope>"])   # also: new, check, eval, lint
```

## Steps

1. **Start.** Run `init --scope <scope>`. It creates the run folder `authoring/runs/<date>-<scope>/` with the run files and lists the skills that exist, the decisions that stand and the last backlog; this run builds on them. Also read the always-on instructions, every `AGENTS.md` in the repo, and earlier skill work in the docs; new output must not repeat or contradict any of it. When the run is about one skill (its sources changed, it gave a wrong answer, a decision it depends on changed), follow [references/update.md](references/update.md) instead of steps 2–4. When someone only edited skills or eval cases, go straight to step 5.
   Check: the run folder holds `inventory.md`, `decisions.md`, `proposals.md` and `report.md`.
2. **Analyze.** Fill `inventory.md`: what you read and how closely, the tasks people repeat with their steps, and every helper, vocabulary and fact the consumer would need for them, each with its source and its layer. Read code before docs, take conventions only from production code, and take examples from tests and working code. Where to look: [references/analyze.md](references/analyze.md).
3. **Identify the skills.** In `decisions.md`, settle each conflict (team against team, docs against code, new against existing context) with the decision the evidence supports, or leave it open when it breaks the contract or has no evidence; nothing that depends on an open conflict is written. Then turn the tasks into the skill family. A task gets a skill when people ask for it on its own, the consumer would get it wrong or read the code to get it right without one, and the knowledge is specific to this organisation. Scope each skill to one coherent task, so one request loads one skill. For each, decide: **new**, a **variant** in the skill that covers it, an **update** (only with an eval case that fails today), or **unchanged**. Never a second skill for a task that already has one, installed skills included when `catalog.installed_skills` is `use`; a change to another team's skill is proposed to its owner.
4. **Write.** Scaffold each skill with `new <name>` and write it to [references/standard.md](references/standard.md): a description that says what the skill does and when to use it, in the words people type, then steps with everything they need written in. Skills that others use go first. Then do a self-containment pass on each: no step sends the consumer to the code, a README or a wiki; every example is complete; every template it copies is in `assets/`. Give each skill eval cases, and each skill that uses others a journey, per [references/evals.md](references/evals.md). Fill `proposals.md` for the other owners.
5. **Check.** Run `check <run folder> --repo <source repo>`: lint, names against the code, evals with and without each skill, the skill map and the agent checklist, written into `report.md`. Fix what it lists, at most three rounds. Delete a skill with NO EFFECT, or move its one useful rule to the `AGENTS.md` candidates. Then fill the top of `report.md`: what was made, what is open, the backlog.
   Check: `check` exits 0, or `report.md` says what still fails and why.

## Verify

- Lint reports no errors, and every new or changed skill is ADDS VALUE, or `report.md` says why not.
- No skill points the consumer at the source (lint SK028), and every fact in a skill traces to a source in its `skill.yaml` or in `inventory.md`.
- No skill depends on a conflict that is open in `decisions.md`.

## Recovery

| Symptom | Cause | Fix |
| --- | --- | --- |
| `skillkit` does not import | No Python with `pyyaml` | Check each skill by hand with the review checklist in [references/standard.md](references/standard.md); say in `report.md` that no evals ran |
| Evals fail with an endpoint or permission error | The model or judge endpoint in the settings is missing or not granted | Run `check --no-eval` and tell the user which endpoint failed; do not switch endpoints yourself, verdicts compare only on the same models |
| The docs cannot be opened | No connector or no access | Ask the user once whether to continue from code only; if so, mark the docs as not read in `inventory.md` and put them in the backlog |
| A case still fails after three rounds | The skill, the case or the model | Report the case and its answer (`eval <name> --inspect <case-id>`) in `report.md`; never loosen a case only to make it pass |
| The thread gets long or is cut off | The context is full | Start a new thread: "Continue the context-authoring run in `<run folder>`". There, skip `init` and resume at the first step whose run file is not filled |

## Rules

- Bake it in, never point: no "see the file", "read the README", "look at the other notebooks". A repo path appears only as where to write a file or what to call or import. Live state (today's tables, failed runs) gets a query.
- Never write environment values (catalog names, hosts, IDs, emails) into skills; name the variable or widget the value comes from.
- One default per decision; an alternative only with the condition that selects it.
- One task per skill, and no skill only to be reused: shared rules go to `AGENTS.md`, short shared steps stay inline.
- Keep human edits: change only what this run decided to change.
- Write each step's result to its run file before the next step: a new thread resumes from the files, not from the chat.

## References

| File | Read it when |
| --- | --- |
| [references/analyze.md](references/analyze.md) | Step 2: where to find tasks and facts, what the consumer needs, which layer each fact goes to |
| [references/standard.md](references/standard.md) | Steps 3–4: what makes a skill, its description, how to write it; the review checklist |
| [references/evals.md](references/evals.md) | Steps 4–5: writing eval cases and journeys; reading verdicts |
| [references/update.md](references/update.md) | A run about one skill and one trigger |
