---
name: context-authoring
description: >-
  Generates and updates Databricks Genie Code context for a repo from its code and
  documentation: task-shaped workspace skills with evals, AGENTS.md candidate lines,
  workspace-instruction proposals and Unity Catalog comment proposals. Use when asked to
  create skills for a repo, team or domain, to onboard a team to Genie Code, to update a
  skill after its sources changed, or to turn documentation into Genie Code skills.
---

# Context authoring

Turns a repo that people work in (data engineering, ML, analytics or apps on Databricks) and its documentation (wiki pages, Markdown, exported pages) into the context Genie Code needs, each piece in the cheapest place: workspace instructions, `AGENTS.md`, skills, Unity Catalog comments. Two modes:

- **create**: a repo, team or domain gets its context for the first time, or an existing skill family is extended to new folders, teams or docs. Follow the steps below; they build on what the output folder already holds.
- **update**: one skill's sources changed or it gave a wrong answer. Follow [references/update-mode.md](references/update-mode.md) instead.

**Where output goes.** Write to the folder the user named, otherwise `/Workspace/Users/<current user>/genie-skills/` (`SELECT current_user()`); reuse it if it already has skills or runs, and say where in your first reply. The layout inside it is in [references/output-contract.md](references/output-contract.md). Never write to the source repo, the workspace skills folder, the workspace instructions or Unity Catalog.

**Limits and tooling.** The defaults are in `assets/defaults/standard.yaml`; a `standard.yaml` in the output folder overrides any of them (limits, team prefixes, forbidden patterns, eval endpoints). The checks are scripts in this skill's `scripts/` folder. Run them with your code tool, nothing to install:

```python
import sys; sys.path.insert(0, "<this skill's folder>/scripts")
from skillkit.cli import main
main(["--root", "<output folder>", "lint"])   # also: catalog, check-names, eval, genie-checklist
```

If you cannot run code, check every rule in [references/output-contract.md](references/output-contract.md) by hand and say in the summary that no evals ran.

## Steps

1. **Scope.** Get from the user: the source repo path, the folders in scope, the owning team and its skill prefix, and the docs (a connector such as Confluence, Markdown in the repo, or exported pages in a folder). If you cannot open the docs, stop and tell the user; continue from code alone only if they agree. Create the run folder.
2. **Load what exists.** List the skills already in the output folder (`catalog`), the workspace instructions, and every `AGENTS.md` in the source repo. Skills installed in the workspace outside the output folder are out of scope by default (`catalog.installed_skills: ignore`): do not load, compare or count them. With `use`, include them (`catalog --installed <workspace skills folder>`) and never create a skill that duplicates one: extend it, or plan its retirement with `supersedes`. Search the docs and connected repos for earlier skill work: skill families, instruction files, authoring runs. Read earlier runs in `authoring/runs/`: their `backlog.md` is where this run can start, and their decisions in `conflicts.md` stand unless the sources they were based on changed. New output must not repeat or silently contradict any of it.
3. **Analyze.** First fill [assets/templates/run/coverage.md](assets/templates/run/coverage.md): every folder in scope with its file count, its kind (production, team-owned, ad hoc, archive) and how closely you read it, so a partial run shows as partial. Read production and team-owned folders first and take conventions only from them. Then fill [assets/templates/run/inventory.md](assets/templates/run/inventory.md): tasks people repeat ("onboard a source table", not "PySpark") with their sub-steps and whether people ask for each on its own, shared helpers with their signatures, config and metadata, vocabularies (term, values, default, consequence), guardrails, folders and owners. [references/analyze.md](references/analyze.md) lists where to find each in code, docs and history. Cite a source for every fact. Read code before docs; where they disagree, the code is the current state.
4. **Classify.** Put each item in exactly one layer with [references/layer-classification.md](references/layer-classification.md), in [assets/templates/run/classification.md](assets/templates/run/classification.md). Public Databricks knowledge is dropped.
5. **Find conflicts, then stop.** Compare team folders with each other, docs with code, and new content with existing context, in [assets/templates/run/conflicts.md](assets/templates/run/conflicts.md); suggest a decision with its reason for each, but decide nothing yourself ([references/conflict-report.md](references/conflict-report.md) explains the decisions and who makes them). Show the list to the user; they can accept your suggestions in one reply. Ask them to review `coverage.md`, `inventory.md` and `conflicts.md` with [references/review-checkpoint.md](references/review-checkpoint.md) first: a wrong fact there ends up in every skill built from it. Skills that depend on no open row can be generated meanwhile; the rest wait for a decision.
6. **Map tasks to skills.** One skill per task, named `<prefix>-<verb>-<object>`. For each task decide: a **new** skill; a **variant** in the skill that already covers it, when another team does the task differently; or leave that skill **unchanged**. More facts are no reason to change a skill: **update** it only when you can write an eval case that fails with it today, then fix it per [references/update-mode.md](references/update-mode.md) (smallest edit, earlier edits kept); facts without a failing case stay in the inventory and backlog. A change to a skill another team owns, variants included, is **proposed** for that owner to approve. Never a second skill for a task that has one, whichever team owns it. Decide everything in the inventory's "Shared material" table in this order: a rule, convention or vocabulary goes to the `AGENTS.md` candidates; a task people also ask for on its own becomes (or already is) a skill that others name at the step that needs it, listed in `uses`; anything else stays inside each skill that needs it. For each template a task needs, decide between naming the repo's template, copying it into `assets/`, building an asset, or none, per "Assets" in [references/writing-skills.md](references/writing-skills.md). Check the catalog budget; if the new descriptions do not fit, merge tasks or ask which to drop. Write the planned family to [skill-map.md](assets/templates/run/skill-map.md) and show it to the user before generating.
7. **Generate.** Write each skill per [references/output-contract.md](references/output-contract.md) and [references/writing-skills.md](references/writing-skills.md), starting from [assets/templates/skill/](assets/templates/skill/SKILL.md), status `draft`. Write skills that others use first, then the skills that use them. For every skill that uses others, add a journey to `<output>/evals/journeys.json` ([template](assets/templates/journeys.json)): a prompt that needs the whole chain, with checks that only pass if the skills hand over. Write the proposals to the run folder: [agents-md-candidates.md](assets/templates/run/agents-md-candidates.md), [workspace-instructions.diff.md](assets/templates/run/workspace-instructions.diff.md), [uc-comments.sql](assets/templates/run/uc-comments.sql), and in `summary.md` the environment-specific names you found (catalogs, storage accounts, hosts) as forbidden patterns for `standard.yaml`. Do not write `AGENTS.md` into the source repo: people write it from the candidates, because unreviewed generated context files measurably lower agent success and raise cost. If the user asks for drafts, also write them to `<run folder>/agents-md/<repo>/<folder>/AGENTS.md` from [AGENTS.repo.md](assets/templates/AGENTS.repo.md) and [AGENTS.team.md](assets/templates/AGENTS.team.md), each marked as a draft; a person edits them, and `eval-context --agents-drafts <run folder>/agents-md` must show ADDS VALUE before they are merged.
8. **Validate** per [references/validation.md](references/validation.md): lint (or its manual checklist) and fix every error; check every helper, table, column and parameter name in the output against the code (`check-names --repo <source repo>`) and fix anything invented; run the evals (`eval <names> --runs 3 --json <run folder>/eval.json`, which also runs the journeys; add `--execute` when a development warehouse is available, so SQL in the answers is planned with `EXPLAIN`). INCONCLUSIVE: answers were cut off; raise `eval: max_tokens` in the skill's `skill.yaml` and run again. FAILING: fix the skill or the case. NO EFFECT: delete the skill, or move its one useful rule into the `AGENTS.md` candidates. At most three rounds, then report what still fails. Then regenerate the map from the written skills (`catalog --map --eval-json <run folder>/eval.json --out <run folder>/skill-map.md`) and generate the Genie Code check (`genie-checklist --out <run folder>/genie-check.md`).
9. **Hand over.** Fill [assets/templates/run/summary.md](assets/templates/run/summary.md) for the pull request and [assets/templates/run/backlog.md](assets/templates/run/backlog.md) with the tasks found but not generated, and tell the user which file goes to which owner. Repo owners write `AGENTS.md` from the candidates with [AGENTS.repo.md](assets/templates/AGENTS.repo.md) (repo root) and [AGENTS.team.md](assets/templates/AGENTS.team.md) (team folder).

## Verify

- Lint reports no errors, and every generated skill has the eval verdict ADDS VALUE (or the summary says why evals could not run).
- Every skill was checked in Genie Code, or the summary lists it as not yet checked.
- Every fact in every generated file traces to a source in its `skill.yaml` or in `inventory.md`.
- Every conflict the skills depend on has a decision in `conflicts.md`.

## Recovery

| Symptom | Cause | Fix |
| --- | --- | --- |
| `skillkit` does not import or install | No Python environment with the package | Use the manual checklist in references/validation.md and say in `summary.md` that lint and evals did not run |
| Evals fail with an endpoint or permission error | The model or judge endpoint in `standard.yaml` is missing or not granted | Stop the eval step and tell the user which endpoint failed; do not switch endpoints on your own, since verdicts are only comparable on the same models |
| Evals refuse to run: example workspace instructions | `context/workspace-instructions.md` still holds the framework example | Ask the user for the real instructions (or confirm there are none) before running evals |
| The docs connector is not available | Confluence or another source cannot be reached | Continue from code only, mark the docs as not read in `coverage.md`, and list the pages to read next time in `backlog.md` |
| A case still fails after three rounds | The skill, the case or the model is the problem | Stop and report the case, its notes and the answer (`--inspect`); never loosen a case only to make it pass |

## Rules

- Distil, do not point. A skill never tells the agent to browse the repo or a wiki for conventions; copy the convention in. Runtime lookups are for live state only, because every read costs tokens on every use.
- Inline helper signatures. Name the repo's own templates by path; put a template in `assets/` only when the assets rule says so.
- Never write environment values (catalog names, hosts, IDs, emails) into skills; name the bundle variable or widget instead.
- One default per decision. An alternative appears only with the condition that selects it.
- Never create a skill only so others can reuse it. A skill exists because people ask for its task; shared rules go to `AGENTS.md`, and short shared steps stay inline. Many narrow skills loaded for one task add overhead and conflicting instructions.
- Keep human edits. Where skills already exist, change only what the user asked for.
- Write each phase's result to a file before moving on; a later session resumes from the run folder, not from chat history.
