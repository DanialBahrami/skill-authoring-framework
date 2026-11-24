---
name: context-authoring
description: >-
  Generates and updates Genie Code context for a your organisation repo from its code and Confluence
  pages: workspace skills, AGENTS.md files, workspace-instruction proposals and Unity Catalog
  comment proposals, all in the genie-context standard. Use when asked to create skills for a
  repo, team or domain, to onboard a team to Genie Code, to regenerate or update a skill after
  its sources changed, or to turn documentation into Genie Code skills.
---

# Context authoring

Runs in the `genie-context` repo. Claude Code picks this skill up from `.claude/skills/`. In Genie Code: copy this folder to `/Workspace/Users/<you>/.assistant/skills/context-authoring/`, clone `genie-context` and the source repos as Git folders side by side under `/Workspace/Users/<you>/`, and run every `skillkit` command below through the notebook `genie-context/notebooks/run_skillkit.py` (set the widgets, run all; read its output). Confluence pages come from the Atlassian connector if one is enabled, otherwise from exported pages in a workspace folder the user names. Two modes:

- **create**: a team or domain gets its context for the first time.
- **update**: one skill's sources changed. Follow [references/update-mode.md](references/update-mode.md) instead of the steps below.

Read `docs/STANDARD.md` and `standard.yaml` before starting; they define the output. Write everything for a run under `authoring/runs/<YYYY-MM-DD>-<scope>/` plus the skill folders under `skills/`. Never write to the source repo, the workspace or Unity Catalog: AGENTS.md files, instruction changes and comments are proposals the owners apply.

## Steps

1. **Scope.** Get from the user: the source repo checkout path, the folders in scope, the owning team and its prefix (must be in `standard.yaml`), and the Confluence pages (Atlassian connector, or exported pages in a folder). If the prefix is not registered, stop; the platform team registers it first.
2. **Load what exists.** Run `skillkit catalog`. Read the existing skills' descriptions, `context/workspace-instructions.md`, and every `AGENTS.md` in the source repo. New output must not repeat or contradict them silently.
3. **Analyze.** Inventory the scope into `inventory.md`: user journeys (tasks people repeat: "onboard a source table", not "PySpark"), shared helpers and their signatures, config and metadata, CI/CD, vocabularies, guardrails, ownership. Cite every fact with a repo path or a Confluence page id. Read code before docs; where they disagree, the code is the current state.
4. **Classify.** Put each inventory item in exactly one layer, using [references/layer-classification.md](references/layer-classification.md). Write `classification.md`: item, layer, reason. Public Databricks knowledge is dropped, not classified.
5. **Find conflicts.** Compare per folder (teams), docs against code, and new content against existing instructions and skills. Write `conflicts.md` with [references/conflict-report.md](references/conflict-report.md). Present the conflicts to the user and wait for decisions on each one before generating content that depends on it. A difference that breaks the platform contract is reported, never encoded.
6. **Map journeys to skills.** One skill per task, named `<prefix>-<verb>-<object>`. If a skill for the task already exists (any team), add this team's way as a variant reference in that skill instead of a new skill. Check the catalog budget: if the new descriptions do not fit, merge tasks or ask which to drop.
7. **Generate.** Write each skill to `skills/<name>/` per [references/output-contract.md](references/output-contract.md), status `draft`. Write the proposals to the run folder: `agents-md-candidates.md`, `workspace-instructions.diff.md`, `uc-comments.sql`. For `AGENTS.md`, do not write the file: list candidate lines, each with its evidence and why the agent cannot infer it from the code. Research found generated context files lower success and raise cost by over 20%; people write the file from the candidates.
8. **Validate.** Run `skillkit lint` and fix every error. Ask: "verify everything you built against the code; no invented helper, table, column or parameter names" and fix what you find. Run `skillkit eval <names> --runs 3 --repos-root <folder with the source repo>`. For each skill: FAILING means fix the content or the eval case; NO EFFECT means the model already does this, so delete the skill or merge its one useful rule into `AGENTS.md`. Repeat at most three rounds, then report what still fails.
9. **Hand over.** Write `summary.md` for the pull request: skills created (with eval verdicts), proposals for other owners, open conflicts. Tell the user which files go to which owner.

## Verify

- `skillkit lint` reports 0 errors and every generated skill has eval verdict ADDS VALUE.
- Every fact in every generated file traces to a source in `skill.yaml` or the run's `inventory.md`.
- `conflicts.md` has a decision for every item the skills depend on.

## Rules

- Distil, do not point. Skills must not tell the agent to browse the repo or wiki for conventions; copy the needed convention in. Runtime lookups are for live state only. Each runtime read costs tokens on every use.
- Inline helper signatures and copy-paste templates into `assets/`; do not tell the agent to read the helper first.
- Never write environment values (catalog names, hosts, IDs, emails) into skills; name the bundle variable or widget instead. The linter rejects them.
- One default per decision. An alternative appears only with the condition that selects it.
- Keep human edits. In a repo that already has skills, regenerate only what the user asked for.
- Reuse before writing. A step another skill already covers becomes a reference to that skill by name, listed in `uses`. Create a building block only if people also ask for that task on its own; otherwise keep the steps in the workflow, because many narrow skills loaded for one task add overhead and conflicting instructions.
- Work in phases and write each result to a file before moving on. A later session resumes from the run folder, not from chat history.
