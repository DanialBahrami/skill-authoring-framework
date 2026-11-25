# Analyze: what to read, what to record, where it goes

## Contents

- How to work
- Coverage first
- Signals in the code
- Signals in the docs and the history
- What the consumer needs in the skill
- Where each fact goes (layers)
- Shared material
- Checklists: tasks and vocabularies
- Done when

## How to work

You fill `inventory.md` in the run folder. Read for the inventory, not for completeness: spread the signals below over a few read-only passes (or subagents, if you have them), write rows as you go, and stop when every table is filled for the folders in scope. Every row cites a source.

Read code before docs. Where they disagree, record both sides in `decisions.md`: the code is the current state, the evidence decides which side is right.

Separate the tasks of people who work in the repo (build a table, fix a job) from the tasks of whoever maintains the shared tooling (release the helper library, change CI). Write skills for the first group; the second only when the user asks, owned by the tooling's maintainers.

## Coverage first

In a large repo you will not read everything; make that visible.

1. List the folders in scope with their file counts (`find <folder> -type f | wc -l`).
2. Give each a kind: **production** (referenced from bundles, jobs or CI), **shared library** (helpers and templates others call), **team-owned** (a team's production folder), **tooling** (CI, deploy scripts, bundle files), **ad hoc** (exploratory scripts, one-offs no job references), **archive** (`old`, `backup`, `deprecated`, untouched for long), **generated** (build output, exports).
3. Read in this order: shared libraries and templates, production, tooling, a sample of team-owned folders. Take conventions and examples only from these. Ad hoc code shows what people struggle with (gotchas), not how it should be done. List archive and generated folders only.
4. Do not open hundreds of similar files: search (`grep -rl`, `grep -c`) for counts and patterns, and record the command as the source.
5. Record how closely you read each folder. A folder read by names only, or skipped, produces no skill in this run; its tasks go to the backlog.

## Signals in the code

Each signal ends with what to record.

**Shared libraries and helpers** (`%run` targets, imported utility modules, a `common/` or `lib/` folder). The helpers people are meant to call and what they guarantee (deduplication, audit columns, tagging).
Record: name, signature, what it guarantees, source, in *Helpers and templates*.

**Setup notebooks, scaffolds, `templates/` folders.** The starting point of a repeated task and its required parameters.
Record: the template with its template decision (copy into assets, build an asset, none), and the task it starts, in *Tasks* and *Helpers and templates*.

**Bundle files, job and pipeline definitions** (`databricks.yml`, `resources/`). Environments, how values are injected (variables, widgets), schedules, compute.
Record: how each environment value is derived, in *Facts* (kind: config). Note every environment-specific name pattern (catalogs, storage accounts, hosts) for the forbidden patterns in `proposals.md`.

**Enums, constants, validation code, `CHECK` constraints, `assert`s.** Allowed values and the combinations the code rejects.
Record: term, values, default, consequence, what goes with what, in *Vocabularies*.

**Columns and tags the code adds automatically** (audit timestamps, source file, run id, delete flag, `pii`). Technical columns users must not redefine.
Record: the full set, in *Vocabularies*.

**Tests (end-to-end first) and example notebooks.** Real, working sequences of a task; examples to copy instead of inventing.
Record: the task's sub-steps in order, in *Tasks*.

**CI pipelines, pre-commit hooks, PR templates.** Checks every change must pass; branch and release process.
Record: in *Facts* (kind: guardrail).

**`CODEOWNERS`, folder names, team READMEs.** Who owns which folder.
Record: the Owner column in *Coverage*.

**Error messages, `raise`, retry and recovery code.** Common failures and their fixes.
Record: in *Facts* (kind: gotcha); they become a skill's `## Recovery` rows.

**Code that drops, truncates, overwrites, deletes checkpoints or reloads fully.** Destructive operations.
Record: in *Facts* (kind: guardrail); each becomes a consent step in a skill.

## Signals in the docs and the history

| Look at | Gives you |
| --- | --- |
| Onboarding guides, "how we do X" pages, runbooks | Tasks and steps as the team describes them; compare with the code |
| Architecture and layer pages | Vocabulary (layers, zones, environments), contract rules |
| Decision records, standards pages | Rules with their reasons; the reason becomes the one line of reasoning in a skill |
| Troubleshooting pages, incident write-ups, FAQ | Gotchas and `## Recovery` rows |
| Pages that describe what the code no longer does | A docs-against-code conflict, not a fact |
| `git log --since=6.months --name-only -- <folders>` | Files that change together: one repeated task (a notebook, a job entry and a test) |
| PR titles and descriptions | The words people use for a task; reuse them in descriptions |
| Repeated review comments ("use the merge template") | Conventions, and good eval assertions |

Record every page you read in *Docs read*, with its id and version, so the next run sees whether it changed. Skip meeting notes, decision history and anything that restates public documentation.

## What the consumer needs in the skill

The consumer works from the skill alone; it does not read the code. For every task, record what it would otherwise have to dig out of the source:

| Knowledge | Example | In the skill |
| --- | --- | --- |
| The helper to use and its signature | `merge_table_silver(df, target, keys)`, and why not `merge_silver` | The signature and the reason, written in: the most invented thing |
| A complete working example | The calls a Silver notebook makes, from a test or production code | Copied in full, environment values as variables |
| A template people copy | The Silver setup notebook | Copied into `assets/`, the original listed in `sources` so the freshness check flags changes |
| Where files go | Folder per source system, file naming | A short tree in the step that writes them |
| A vocabulary and its consequences | Load types, what each requires, what breaks | Term, values, default, consequence, what goes with what |
| The order of steps; where to stop and ask | Validate before deploy; ask before a full reload | Steps with a check and a guard |
| A choice made across many files or by people | "14 of 16 notebooks do X"; a conflict's outcome | The rule and its reason |
| Live state | Today's columns, tables, failed runs | The query that fetches it, never the result |

Mine examples from tests and production code; never invent one. A large catalog (every column of every table, every config key) is not copied whole: the skill gives the values the task chooses between, and the query or script that lists the rest.

## Where each fact goes (layers)

Ask in order; the first yes decides the Layer column.

| # | Question | Layer |
| --- | --- | --- |
| 1 | Is it in public documentation, or a skill the agent already has? | `drop` |
| 2 | Is it a fact about one table, column or model (meaning, grain, source, PII)? | `catalog-comment` |
| 3 | Must it hold in every response of the agent, even with no repo file open? | `instructions` |
| 4 | Is it a convention or vocabulary that any task in one repo or folder needs? | `agents-md:<path>` |
| 5 | Is it a sequence of steps for a task people repeat, with organisation-specific choices? | `skill:<name>` |
| 6 | Is it deterministic work (a lookup, a check, a generated snippet)? | `script:<skill>` |
| 7 | None of the above | `drop`, or ask the user |

- `AGENTS.md` loads only when a file in that folder is open. A task that starts outside the repo (the SQL editor, a new notebook) carries the vocabulary it needs inside the skill.
- Always-on instructions cost tokens on every response: only rules that must hold across repos, or where a wrong answer is harmful.
- A long table a skill needs only sometimes goes in that skill's `references/`.

## Shared material

Anything that appears in two or more tasks: a sub-step, a rule, a vocabulary. The first yes wins:

1. A rule, convention or vocabulary: `AGENTS.md` (or the always-on instructions if it must hold outside the repo).
2. A task people also ask for on its own: its own skill, which other skills name at the step that needs it.
3. Otherwise: inline in each skill that needs it. A few repeated lines cost less than a skill that must always load alongside.

No skill exists only to be reused.

## Checklists: tasks and vocabularies

A checklist, not a quota. Keep only what people in scope really do.

Tasks: explore a source before building on it · bring in a new source · create or change a table, view or model in a layer · add or change a column; backfill · add a data quality check · schedule, change or rerun a job · promote between environments; prepare a release or PR · diagnose a failed or slow run · monitor pipelines, quality or cost · grant access; tag or mask sensitive data; handle a deletion request · train, register, promote or monitor a model · build or publish a dashboard or app · decommission a table, job or source.

Vocabularies: layers or zones · load types (full, incremental, append, CDC) and what each requires · delete handling and history tracking (SCD 1 or 2) · schema evolution modes · technical columns and tags · data quality severities and where results go · environments and promotion order · naming conventions (catalogs, schemas, tables, jobs, models) · allowed compute and schedules · which changes are breaking and need a reload.

Tasks that chain (onboard a source, change its schema, prepare the PR) become journeys: note them for the eval cases.

## Done when

- Every folder in scope is in *Coverage* with how closely it was read.
- Every task has its sub-steps and which of them people ask for on their own.
- Every helper a task uses has its signature; every vocabulary has values, default, consequence and what goes with what.
- Every destructive operation is a guardrail fact.
- Every row has a source and a layer.
