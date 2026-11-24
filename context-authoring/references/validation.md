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

With `skillkit`: `skillkit lint <names>` and fix every error. Warnings marked SK020 (scripts, network calls, external URLs) go to the human reviewer.

Without it, check by hand and write the result in `summary.md`:

- [ ] Folder name equals `name`, which is `<prefix>-<verb>-<object>` with the team's registered prefix.
- [ ] Description is third person, 80–600 characters, contains `Use when`, and names the neighbour it is not for when they share vocabulary.
- [ ] Body is under 200 lines, has `## Steps` and `## Verify`, and no sections outside the allowed list.
- [ ] Every link points to a file in the skill folder; reference files do not link further.
- [ ] Every skill named in the body is in `uses`, exists, and is not deprecated; no skill uses itself through others; platform skills do not use team skills.
- [ ] No catalog names, hosts, emails, IDs, tokens, dates or version notes (search for the organisation's own names too).
- [ ] `skill.yaml` has owner, status `draft`, `last_reviewed`, and at least one source; every variant has an owner.
- [ ] `evals/evals.json` has at least two trigger cases and one near miss.
- [ ] All new descriptions together fit the catalog budget alongside the existing ones.

## 2. Names against the code

For every helper, template, table, column, widget, parameter and command in the generated files, find it in the source repo (or the doc it came from). Fix or remove anything that is not there. This catches most invented content, and evals do not: a confident wrong name can still pass a rubric.

## 3. Evals

`skillkit eval <names> --runs 3` runs each case with and without the skill and reports a verdict per skill:

| Verdict | Meaning | Action |
| --- | --- | --- |
| ADDS VALUE | Cases pass more often with the skill | Keep |
| NO EFFECT | The model answers as well without it | Delete the skill, or move its one useful rule to the `AGENTS.md` candidates |
| FAILING | Cases fail even with the skill | Fix the skill, or the case if the case was wrong |

Also read the routing result: a trigger case that does not select the skill, or a near miss that does, means the description needs work. Stop after three rounds and report what still fails.

Without `skillkit`, say in the summary that no evals ran and do step 4 for every skill.

## 4. Check in Genie Code

Evals call a model through a serving endpoint; they are not Genie Code itself. Before a skill becomes `active`:

1. Install the draft as a personal skill (`/Workspace/Users/<you>/.assistant/skills/<name>/`).
2. In a new Agent-mode thread, open a file in the folder the task belongs to and give two of the skill's trigger prompts, worded as a user would.
3. Check: the skill was used; the answer uses the real helpers and conventions; nothing was hardcoded; risky steps asked for consent; skills named in its steps were followed.

Record the result in `summary.md`. A skill that uses other skills always gets this check, because whether Genie Code loads a skill named in another skill's steps is not documented.

## Symptoms and fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Agent invents a helper, field or value | It was not inlined | Inline the signature or vocabulary (term, values, default, consequence) |
| Skill not used for a prompt it should handle | Description lacks the words people type | Rewrite the description with the prompt's words; add the prompt as a trigger case |
| Skill used for the wrong task | Two descriptions overlap | Sharpen both; add a near-miss case naming the right skill |
| Agent hardcodes a catalog or path | The step did not say where the value comes from | Name the bundle variable or widget in the step |
| Agent does something destructive without asking | No guard at that step | Add the consent step where the risk occurs, with the non-destructive option first |
| Agent reads the repo or a wiki page to find a convention | The skill points instead of distilling | Copy the convention into the skill or `AGENTS.md` |
| Two teams' ways mixed in one answer | Variant condition unclear | State the condition in step 1 and keep each way in its own reference file |
| NO EFFECT on every case | The model already knows this | Delete the skill |

## Done when

- Lint is clean (or the manual checklist passes).
- Every name in the output exists in the sources.
- Every skill is ADDS VALUE, or the summary says why evals could not run.
- Every skill passed the Genie Code check, or the summary lists it as not yet checked.
