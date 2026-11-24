# Writing skills that work

The output contract says what a skill must contain. This file is about writing it so the agent follows it.

## Contents

- Description
- Steps
- Decisions
- How exact to be
- Risky steps
- Gotchas
- Examples and templates
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

From a fictional repo. Before (generic, points elsewhere, no reasons):

```
## Steps
1. Read the Silver README to understand the conventions.
2. Create the table following best practices.
3. Make sure PII is handled correctly.
```

After (distilled, with the default, the reason and the guard):

```
## Steps
1. Copy `assets/silver_notebook.py` next to the Bronze notebook and set the widgets `source_table` and `business_key`.
2. Merge with `merge_table_silver(df, target, keys=[business_key])`: it deduplicates on the key and adds `_loaded_at` and `_source_file`; do not write a MERGE by hand.
3. Tag every PII column with `pii` and the PII type as value (`email`, `phone`); untagged PII columns are not masked downstream.
4. Run the notebook in development only; production changes go through the release pipeline.
```
