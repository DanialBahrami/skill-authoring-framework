# Writing skills that work

The output contract says what a skill must contain. This file is about writing it so the agent follows it.

## Contents

- Description
- Steps
- Checks and recovery
- Decisions
- How exact to be
- Risky steps
- Gotchas
- Examples and templates
- Assets
- Scripts
- Words
- What to leave out
- Before and after

## Description

It decides whether the skill loads; nothing else in the skill matters if it does not.

- First what the task produces, then `Use when` with the situations and the words people type: table and helper names, layer names, "add a column", the phrasing from PR titles.
- Name the neighbouring skill it is not for when they share vocabulary.
- Test it against the catalog: if two descriptions could both match a prompt, sharpen both.

## Steps

- One action per step, in the order the agent does it, imperative.
- Add one line of reasoning only where the step differs from what the agent would do by default. "Use `merge_table_silver`: it adds the audit columns and deduplicates on the business key" lets the agent handle cases the skill did not foresee; a bare "use `merge_table_silver`" does not.
- Inline what the step needs (helper signature, parameter names, the convention), copied from the source. Never send the agent to read a file or page for it.
- Name another skill at the step that needs it, with what to pass, and list it in `uses`.

## Checks and recovery

Generated skills tend to describe only the happy path. When a step fails, the agent improvises: it retries, wastes turns, or "fixes" the problem in a way nobody would accept, such as creating the table in a schema where it does have rights.

- A step that runs something (a command, SQL, a deploy, a script) ends with `Check:` and the observable result that means it worked: an exit code, a `DESCRIBE TABLE` with the expected columns, the job in `databricks bundle summary`. The agent checks before the next step, so a failure is caught where it happens, not three steps later.
- `## Verify` is still the end-to-end check before reporting back; `Check:` lines are per step.
- `## Recovery` is a table of the failures the steps can realistically hit, with cause and fix. Take the rows from error handling in the code, troubleshooting pages, incident write-ups and repeated review comments; never invent failures to fill the table.
- A fix says what to change, or when to stop and what to tell the user. "Try again" is not a fix. Where improvising would do harm (permissions, an existing table, production), the fix is to stop and ask.
- Keep it to the steps' own failures, usually three to six rows. A long troubleshooting guide is a reference file linked from the row that needs it.

```
## Recovery

| Symptom | Cause | Fix |
| --- | --- | --- |
| `PERMISSION_DENIED` on CREATE TABLE | The principal lacks a grant on the schema | Stop and tell the user which grant is missing; never create the table in another schema |
| `variable catalog is not defined` | No bundle target given | Rerun with `-t dev` |
| The table exists with a different schema | An earlier onboarding failed half-way | Stop and report the difference; do not drop the table |
```

## Decisions

A decision is a step with its condition, default first:

```
3. Choose the load type: `incremental` with the source's business key. If the source sends a full extract every day and has no key, use `full` instead.
```

Not a tree, not a menu of equal options. If a decision has more than two outcomes that people really use, put the options with their consequences in a table under `## Rules` or a reference file, and keep the default in the step.

## How exact to be

Match the wording to how fragile the step is.

| The step | Write |
| --- | --- |
| Has many valid ways and depends on context (naming a new column) | The rule and its reason |
| Has a preferred pattern with some variation (a notebook layout) | A template in `assets/` and what may change in it |
| Breaks when done slightly differently (a deploy command, a merge call) | The exact command or call, to copy as is |

## Risky steps

Put the guard in the step where the risk occurs, not in a separate section the agent may not connect to it:

```
5. If the schema change is breaking (rename, type change, new key), stop: offer a new column or a new table first, and run a full reload only after the user explicitly agrees.
```

Read-only steps (inspect, profile, list runs) come before anything that writes.

## Gotchas

Facts that defy a reasonable assumption are often the most valuable lines in a skill: "the `pii` tag is set on the column, not the table", "`full` loads cannot represent deletes". Collect them from error messages, troubleshooting pages and repeated review comments. Leave out anything the agent would get right anyway.

## Examples and templates

- Copy examples from working code or tests; never invent one. An invented helper or parameter is the most common failure the validation step finds.
- An example is complete: the agent can paste it and fill the marked values.
- Environment values in examples are bundle variables or widgets, never literals.

## Assets

Decide per template, at Map, and record the decision in the inventory's "Shared helpers and templates" table:

| Situation | Do | Why |
| --- | --- | --- |
| The repo already has a template people copy (a setup notebook, a deployment script template) | Name it by path at the step that uses it, and list it in the skill's `sources` | A copy in `assets/` would drift from the original; the source entry makes the freshness check notice when it changes |
| The same, but the task can start outside the repo (SQL editor, a new notebook, no repo file open) | Copy it into `assets/`, with the repo file in `sources` | Without an open repo file the agent may not find the original |
| No template exists, but people produce the same shape again and again: notebook skeleton, job or bundle YAML, deployment script, PR description | Build an asset from two or three real examples, with the parts to fill marked `<like_this>` | The agent copies a known-good shape instead of inventing one |
| A small step the agent gets wrong by reasoning (deriving a path from widgets, listing a job's last runs) | A script in `scripts/` (next section) | Rare; most skills need none |
| Anything else | No asset | |

Every asset is linked from the step that uses it, with what may change in it. Keep an asset only if the evals show it helps; lint compiles Python assets and parses YAML and JSON assets.

## Scripts

Add a script to `scripts/` only for deterministic work the agent would otherwise get wrong or spend many tokens on (deriving a path from widgets, listing a job's last runs). Say in the step whether the agent runs it or reads it, what it needs installed, and what its output means. Most skills need none.

## Words

- One term per concept, the same one the code and `AGENTS.md` use. If the team uses internal jargon, use it and define it once, or use the standard term.
- Forward slashes in paths.
- No dates, versions or history ("since the migration in March"): they go stale and the lint rejects them.

## What to leave out

- Anything in public Databricks documentation or a built-in skill.
- Background the agent already knows ("Delta Lake is an open table format...").
- Conventions every task in the repo needs: they belong in `AGENTS.md`, once.
- Live state (current tables, today's failures): give the query instead.

## Before and after

From a fictional repo. Before (generic, points elsewhere, no reasons, no checks):

```
## Steps
1. Read the Silver README to understand the conventions.
2. Create the table following best practices.
3. Make sure PII is handled correctly.
```

After (distilled, with the default, the reason, the guard and the checks):

```
## Steps
1. Copy `assets/silver_notebook.py` next to the Bronze notebook and set the widgets `source_table` and `business_key`.
2. Merge with `merge_table_silver(df, target, keys=[business_key])`: it deduplicates on the key and adds `_loaded_at` and `_source_file`; do not write a MERGE by hand.
3. Tag every PII column with `pii` and the PII type as value (`email`, `phone`); untagged PII columns are not masked downstream.
4. Run the notebook in development only; production changes go through the release pipeline.
   Check: `DESCRIBE TABLE` on the target lists `_loaded_at` and `_source_file`, and the PII columns carry the `pii` tag.
```
