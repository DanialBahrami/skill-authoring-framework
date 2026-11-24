# Analyze: where to find what goes in the inventory

## Contents

- How to work this step
- Signals in the code
- Signals in the docs
- Signals in the history
- Task checklist
- Vocabulary checklist
- Who the tasks are for
- When the inventory is done

## How to work this step

Read for the inventory, not for completeness. Spread the signals below over a few read-only passes (or subagents, if the agent has them), write findings to `inventory.md` as you go, and stop when every table is filled for the folders in scope. Every row cites a source: a repo path, a doc page, or `note:` with who said it.

Read code before docs. Where they disagree, record both in `conflicts.md`; the code is the current state, but people decide which side is right.

## Signals in the code

| Look at | Gives you | Goes to inventory table |
| --- | --- | --- |
| Shared libraries, helper modules, `%run` targets, imported utility notebooks | The helpers people are meant to call, with signatures and what they guarantee (deduplication, audit columns, tagging) | Shared helpers and templates |
| Setup notebooks, scaffolds, cookiecutters, `assets/` or `templates/` folders | The starting point for a repeated task, and its required parameters | Tasks; Shared helpers and templates |
| Bundle files (`databricks.yml`, `resources/`), job and pipeline definitions | Environments, how values are injected (variables, widgets), schedules, compute choices | Config, metadata and environments |
| Config files, settings objects, widget definitions | How catalogs, schemas, paths and secrets are derived per environment; the values skills must never hardcode | Config, metadata and environments |
| Enums, constants, validation code, `CHECK` constraints, `assert`s | Allowed values and the combinations the code rejects | Vocabulary |
| Columns or tags the code adds automatically (audit timestamps, source file, run id, delete flag, `pii` tags) | Technical columns users must not redefine | Vocabulary |
| Tests, especially end-to-end ones, and example notebooks | Real, working sequences of a task; real examples to copy instead of inventing | Tasks (sub-steps) |
| CI pipelines, pre-commit hooks, linters, PR templates | Checks every change must pass; branch and release process | Guardrails and process |
| `CODEOWNERS`, folder names, team READMEs | Which team owns which folder | Folders and owners |
| Error messages, `raise` statements, retry and recovery code | Common failures and their fixes; worth a Gotcha when the fix is not obvious | Guardrails and process |
| Code that drops, truncates, overwrites, deletes checkpoints or reloads fully | Destructive operations that need a consent step | Guardrails and process |

## Signals in the docs

| Look at | Gives you |
| --- | --- |
| Onboarding guides, "how we do X" pages, runbooks | Tasks and their steps as the team describes them; compare with the code |
| Architecture and layer pages | Vocabulary (layers, zones, environments), contract rules |
| Decision records, standards pages | Rules with their reasons; the reason becomes the one line of reasoning in a skill |
| Troubleshooting pages, incident write-ups, FAQ | Gotchas and failure fixes |
| Pages that describe something the code no longer does | A docs-vs-code conflict, not a fact |

Skip meeting notes, history of decisions and anything that restates public Databricks documentation.

## Signals in the history

Tasks people repeat show up as repeated changes. When the repo history is available:

- `git log --since=6.months --name-only -- <folders>`: which kinds of files change together and how often (a new notebook plus a job entry plus a test is one task).
- PR titles and descriptions: the words people use for the task; reuse them in skill descriptions.
- Review comments that repeat ("use the merge template", "add the audit columns"): conventions the agent should follow, and good eval assertions.

## Task checklist

A checklist, not a quota: keep only tasks people in scope actually repeat, and name them in the team's words.

- Bring in a new source (file, database, API, stream)
- Create or change a table, view or model in a layer
- Add or change a column or schema; backfill or reprocess data
- Add a data quality check
- Schedule, change or rerun a job or pipeline
- Promote a change between environments; prepare a release or PR
- Diagnose a failed run or a slow job
- Grant access; tag or mask sensitive data; handle a deletion request
- Train, register, promote or monitor a model
- Build or publish a dashboard, report or app
- Decommission a table, job or source

A task becomes a skill only after Classify and Map. Many short tasks turn out to be one convention for `AGENTS.md`.

## Vocabulary checklist

For each vocabulary the code has, record term, allowed values, default and the consequence of a wrong value. These are what an agent guesses wrong.

- Layers or zones and what each one owns
- Load types (full, incremental, append, change data capture) and what each requires (a key, an ordering column)
- Delete handling (hard, soft, delete flag) and history tracking (SCD type 1 or 2)
- Schema evolution modes
- Technical columns and tags added automatically
- Data quality severities (warn, drop, fail) and where results go
- Environments, how they are selected, and the promotion order
- Naming conventions for catalogs, schemas, tables, jobs, models and skills' own prefixes
- Compute and schedule options the team allows
- Which changes are breaking and need a full reload or a migration

## Who the tasks are for

Separate tasks of the people who work in the repo (build a table, fix a job) from tasks of whoever maintains the shared tooling itself (release the helper library, change the CI pipeline). Generate skills for the first group by default; the second group gets skills only when the user asks, owned by the tooling's maintainers.

## When the inventory is done

- Every task in scope has its sub-steps, who does it, and whether people ask for each sub-step on its own.
- Every helper a task uses has its signature.
- Every vocabulary a task touches has values, default and consequence.
- Every destructive operation is listed as a guardrail.
- Every row has a source.
