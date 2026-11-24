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

- **create**: a repo, team or domain gets its context for the first time. Follow the steps below.
- **update**: one skill's sources changed or it gave a wrong answer. Follow [references/update-mode.md](references/update-mode.md) instead.

**Where output goes.** Work inside the context repo (called `genie-context` here) when one exists: skills go to `skills/<name>/`, the run's working files to `authoring/runs/<YYYY-MM-DD>-<scope>/`. Without one, ask the user for an output folder and use the same layout there. Never write to the source repo, a workspace or Unity Catalog: `AGENTS.md`, instruction changes and comments are proposals that their owners apply.

**Limits and tooling.** If the context repo has a `standard.yaml`, its limits, team prefixes and allowed sections override the defaults in [references/output-contract.md](references/output-contract.md). If `skillkit` is installed (or the context repo has `notebooks/run_skillkit.py` for Genie Code), use it for `catalog`, `lint` and `eval`; otherwise check every rule in the output contract by hand and say in the summary that no evals ran.

## Steps

1. **Scope.** Get from the user: the source repo path, the folders in scope, the owning team and its skill prefix, and the docs (a connector such as Confluence, Markdown in the repo, or exported pages in a folder). Create the run folder.
2. **Load what exists.** List the existing skills and their descriptions (`skillkit catalog`), the workspace instructions, and every `AGENTS.md` in the source repo. New output must not repeat or silently contradict them.
3. **Analyze.** Fill [assets/templates/run/inventory.md](assets/templates/run/inventory.md): tasks people repeat ("onboard a source table", not "PySpark") with their sub-steps and whether people ask for each on its own, shared helpers with their signatures, config and metadata, vocabularies (term, values, default, consequence), guardrails, folders and owners. [references/analyze.md](references/analyze.md) lists where to find each in code, docs and history. Cite a source for every fact. Read code before docs; where they disagree, the code is the current state.
4. **Classify.** Put each item in exactly one layer with [references/layer-classification.md](references/layer-classification.md), in [assets/templates/run/classification.md](assets/templates/run/classification.md). Public Databricks knowledge is dropped.
5. **Find conflicts, then stop.** Compare team folders with each other, docs with code, and new content with existing context, in [assets/templates/run/conflicts.md](assets/templates/run/conflicts.md); decide nothing yourself ([references/conflict-report.md](references/conflict-report.md) explains the decisions and who makes them). Show the list to the user and wait until every item the skills depend on has a decision.
6. **Map tasks to skills.** One skill per task, named `<prefix>-<verb>-<object>`. When a skill for the task exists (any team), add this team's way as a variant in it instead of a new skill. Decide everything in the inventory's "Shared material" table in this order: a rule, convention or vocabulary goes to the `AGENTS.md` candidates; a task people also ask for on its own becomes (or already is) a skill that others name at the step that needs it, listed in `uses`; anything else stays inside each skill that needs it. Check the catalog budget; if the new descriptions do not fit, merge tasks or ask which to drop.
7. **Generate.** Write each skill per [references/output-contract.md](references/output-contract.md) and [references/writing-skills.md](references/writing-skills.md), starting from [assets/templates/skill/](assets/templates/skill/SKILL.md), status `draft`. Write skills that others use first, then the skills that use them. Write the proposals to the run folder: [agents-md-candidates.md](assets/templates/run/agents-md-candidates.md), [workspace-instructions.diff.md](assets/templates/run/workspace-instructions.diff.md), [uc-comments.sql](assets/templates/run/uc-comments.sql). Do not write `AGENTS.md` itself: people write it from the candidates, because generated context files measurably lower agent success and raise cost.
8. **Validate** per [references/validation.md](references/validation.md): lint (or its manual checklist) and fix every error; check every helper, table, column and parameter name in the output against the code and fix anything invented; run the evals (`skillkit eval <names> --runs 3`). FAILING: fix the skill or the case. NO EFFECT: delete the skill, or move its one useful rule into the `AGENTS.md` candidates. At most three rounds, then report what still fails. Then check each skill with two prompts in Genie Code.
9. **Hand over.** Fill [assets/templates/run/summary.md](assets/templates/run/summary.md) for the pull request and tell the user which file goes to which owner. Repo owners write `AGENTS.md` from the candidates with [AGENTS.repo.md](assets/templates/AGENTS.repo.md) (repo root) and [AGENTS.team.md](assets/templates/AGENTS.team.md) (team folder).

## Verify

- Lint reports no errors, and every generated skill has the eval verdict ADDS VALUE (or the summary says why evals could not run).
- Every skill was checked in Genie Code, or the summary lists it as not yet checked.
- Every fact in every generated file traces to a source in its `skill.yaml` or in `inventory.md`.
- Every conflict the skills depend on has a decision in `conflicts.md`.

## Rules

- Distil, do not point. A skill never tells the agent to browse the repo or a wiki for conventions; copy the convention in. Runtime lookups are for live state only, because every read costs tokens on every use.
- Inline helper signatures; put copy-paste templates in the skill's `assets/`.
- Never write environment values (catalog names, hosts, IDs, emails) into skills; name the bundle variable or widget instead.
- One default per decision. An alternative appears only with the condition that selects it.
- Never create a skill only so others can reuse it. A skill exists because people ask for its task; shared rules go to `AGENTS.md`, and short shared steps stay inline. Many narrow skills loaded for one task add overhead and conflicting instructions.
- Keep human edits. Where skills already exist, change only what the user asked for.
- Write each phase's result to a file before moving on; a later session resumes from the run folder, not from chat history.
