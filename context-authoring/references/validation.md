# Validation

Three checks, in order: the output follows the contract, every name in it is real, and the skill changes the agent's answers for the better. Then a short check in Genie Code itself.

## Contents

- 1. Contract
- 2. Names against the code
- 3. Evals
- 4. Check in Genie Code
- Symptoms and fixes
- Done when

## 1. Contract

With the scripts (see SKILL.md, "Limits and tooling"): `lint` (no names, so the catalog, journey and dependency checks run too) and fix every error. SK026 warns about a step that runs something without a `Check:` line, and SK027 about a skill whose trigger cases have no trajectory; fix both unless the reason is clear. SK023 warns about assertions a model cannot satisfy without running anything ("names the latest release branch", "lists the existing tables"); rewrite them to expect the query or the step. Warnings marked SK020 (scripts, network calls, external URLs) go to the human reviewer.

Without it, check by hand and write the result in `summary.md`:

- [ ] Folder name equals `name`, which is `<prefix>-<verb>-<object>` with the team's registered prefix.
- [ ] Description is third person, 80–1,024 characters, contains `Use when`, and names the neighbour it is not for when they share vocabulary.
- [ ] Body is under 500 lines, has `## Steps`, `## Verify` and `## Recovery` in that order, and no sections outside the allowed list.
- [ ] Every step that runs something has a `Check:` line; every `## Recovery` row has a real fix (not "try again").
- [ ] Every link points to a file in the skill folder; reference files do not link further.
- [ ] Every skill named in the body is in `uses`, exists, and is not deprecated; no skill uses itself through others; platform skills do not use team skills.
- [ ] No catalog names, hosts, emails, IDs, tokens, dates or version notes (search for the organisation's own names too).
- [ ] `skill.yaml` has owner, status `draft`, `last_reviewed`, and at least one source; every variant has an owner.
- [ ] `evals/evals.json` has at least two trigger cases and one near miss, and at least one trigger case has a `trajectory`.
- [ ] Every decision from the inventory's vocabulary that the task touches (load type, delete handling, data quality severity, breaking or not before anything destructive) appears in the skill as a step with its default and the condition for the alternative.
- [ ] Every skill that uses others has a journey in `evals/journeys.json`, and every skill in a journey is reachable from its first skill through `uses` (JR002).
- [ ] `context/workspace-instructions.md` holds the workspace's real instructions, not the framework example: evals inject it into every answer.
- [ ] All new descriptions together fit the catalog budget alongside the existing ones.

## 2. Names against the code

For every helper, template, table, column, widget, parameter and command in the generated files, find it in the source repo (or the doc it came from). Fix or remove anything that is not there. This catches most invented content, and evals do not: a confident wrong name can still pass a rubric.

`check-names <names> --repo <source repo checkout>` looks up every inline code span in the skill and its references, as a file or folder name and in file contents, and lists what it cannot find. Placeholders (`<table>`, `YYYY.MM.DD`) and commands with arguments are skipped. Treat the list as questions, not errors: a value the user types or a workspace group legitimately appears in no file; pass those with `--ignore` so the list stays short.

## 3. Evals

`eval <names> --runs 3` runs each case with and without the skill and reports a verdict per skill. Each answer gets the workspace instructions Genie Code would load: the live `/Workspace/.assistant_workspace_instructions.md`, or the output folder's `context/workspace-instructions.md` when it is a context repo. Routing always uses every skill in the output folder that is not deprecated, drafts included, so a near miss can go to a sibling skill that is not being evaluated; add `--installed <folder>` to include skills already installed in the workspace (when `catalog.installed_skills: use`).

| Verdict | Meaning | Action |
| --- | --- | --- |
| ADDS VALUE | Cases pass more often with the skill | Keep |
| NO EFFECT | The model answers as well without it | Delete the skill, or move its one useful rule to the `AGENTS.md` candidates |
| FAILING | Cases fail even with the skill | Fix the skill, or the case if the case was wrong |
| INCONCLUSIVE | Answers were cut off at the token limit | Set `eval: max_tokens` in the skill's `skill.yaml` and run again |

**Execution gate.** Rubrics and regexes see whether code looks right, not whether it runs. Add `--execute` with a development SQL warehouse (`--warehouse-id <id>`), or run it from a notebook to use the active Spark session, and `--sql-var catalog=<dev catalog>` for the variables the skills use. The gate plans every query and DML statement in an answer with `EXPLAIN`, runs `DESCRIBE TABLE` on every fully qualified table in the development catalog (`MERGE` and `ALTER` targets too), compiles Python blocks and parses YAML blocks. An invented table or column, or a syntax error, fails the case even when the rubric passed. Only `EXPLAIN` and `DESCRIBE TABLE` are sent, and both read metadata, never rows. Tables the answer creates are skipped; for a source that is not onboarded yet, list its tables as regexes in the case's `exec_new_tables`. Use an identity that can only read the development catalog.

**Journeys.** `evals/journeys.json` holds tasks that span several skills. `eval` runs the journeys that involve the skills under evaluation: routing must pick the first skill, and the answer, with all the journey's skills loaded, must pass its checks. This shows whether the skills hand over (names, tables and parameters line up). It cannot show whether Genie Code loads a skill named in another skill's steps; the journeys in the Genie Code check do.

Before fixing a failing case, check that it is achievable: the eval model cannot run anything, so a case that expects real results (actual table lists, today's branch name) fails for every skill. Rewrite it to expect what the agent would do.

Also read the routing result: a trigger case that does not select the skill, or a near miss that does, means the description needs work. Stop after three rounds and report what still fails.

Without `skillkit`, say in the summary that no evals ran and do step 4 for every skill.

## 4. Check in Genie Code

Evals call a model through a serving endpoint; they are not Genie Code itself. Before a skill becomes `active`:

`genie-checklist <names> --out <run folder>/genie-check.md` writes the prompts to paste and what to look for in each answer, taken from the eval cases.

1. Install the draft as a personal skill (`/Workspace/Users/<you>/.assistant/skills/<name>/`).
2. In a new Agent-mode thread, open a file in the folder the task belongs to and give two of the skill's trigger prompts, worded as a user would.
3. Check: the skill was used; the answer uses the real helpers and conventions; nothing was hardcoded; risky steps asked for consent; skills named in its steps were followed; the trajectory items hold for what Genie Code actually read and ran.
4. Note whether Genie Code read repo files to answer. Reading code is allowed, but if it read the files the skill distils, the skill may not be doing the work.
5. If the task can start outside the repo (SQL editor, a new notebook), ask one prompt with no repo file open: `AGENTS.md` does not load then.
6. Give each journey's prompt and check that every skill in it was used.

Record the result in `summary.md`. A skill that uses other skills always gets this check, because whether Genie Code loads a skill named in another skill's steps is not documented.

## Symptoms and fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Agent invents a helper, field or value | It was not inlined | Inline the signature or vocabulary (term, values, default, consequence) |
| Execution gate: column or table not found | The skill names a column or table that is not in the development catalog, or the model invented one | Check the skill's names with `check-names` and against the table; inline the real column list where the task needs it |
| Answers use catalog or table names that exist nowhere in your code | The evals injected example workspace instructions, or an example `AGENTS.md` | Replace `context/workspace-instructions.md` with the real one; check the case's `agents` paths |
| Journey fails but each skill passes alone | The skills do not hand over: different names for the same table or parameter | Use the same names in both skills; state in the using skill what it passes |
| Skill not used for a prompt it should handle | Description lacks the words people type | Rewrite the description with the prompt's words; add the prompt as a trigger case |
| Skill used for the wrong task | Two descriptions overlap | Sharpen both; add a near-miss case naming the right skill |
| Agent hardcodes a catalog or path | The step did not say where the value comes from | Name the bundle variable or widget in the step |
| Agent does something destructive without asking | No guard at that step | Add the consent step where the risk occurs, with the non-destructive option first |
| Agent reads the repo or a wiki page to find a convention | The skill points instead of distilling | Copy the convention into the skill or `AGENTS.md`, and add the detour to a case's `trajectory.avoid` |
| Trajectory order fails, answer is right | The skill's steps are not in the order the agent should act, or a step is missing | Reorder the steps; put read-only checks before writes |
| Agent improvises after an error (retries, works around it, writes elsewhere) | No `Check:` on the step, or no `## Recovery` row for that failure | Add the check and the row, with a stop where improvising would do harm |
| Two teams' ways mixed in one answer | Variant condition unclear | State the condition in step 1 and keep each way in its own reference file |
| NO EFFECT on every case | The model already knows this | Delete the skill |

## Done when

- Lint is clean (or the manual checklist passes).
- Every name in the output exists in the sources.
- Every skill is ADDS VALUE, or the summary says why evals could not run.
- Every skill passed the Genie Code check, or the summary lists it as not yet checked.
