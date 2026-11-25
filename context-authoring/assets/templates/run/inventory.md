# Inventory: {{scope}}

Run: {{run}} · Source repo: <name> · Folders: <paths> · Team: <team> (<prefix>) · Docs: <where>

What this run is based on. Every row has a source: a repo path, a doc page id, a search command, or `note:` with who said it. Read code before docs; where they disagree, the code is the current state and the difference goes to `decisions.md`. How to fill each table: `references/analyze.md`.

## Coverage

Kind: production · shared library · team-owned · tooling · ad hoc · archive · generated.
Read: all · sampled (which files) · searched (the command) · names only · skipped.
Take conventions and examples only from production, shared library, team-owned and tooling folders. A folder read by names only, or skipped, produces no skill in this run: its tasks go to the backlog in `report.md`.

| Folder | Files | Kind | Owner | Read | Notes |
| --- | --- | --- | --- | --- | --- |

### Docs read

| Page or file | Id and version | Useful? | Contradicts the code? |
| --- | --- | --- | --- |

## Tasks people repeat

Named in the team's words ("onboard a source table", not "PySpark"). "On its own" decides what becomes a separate skill: a sub-step people also ask for by itself.

| Task (verb + object) | Who does it | Sub-steps, in order | Sub-steps asked for on their own | Sources |
| --- | --- | --- | --- | --- |

## Helpers and templates

The consumer will not read these files: the skill carries the signature, and every template the task copies goes into the skill's `assets/`. Template: **copy to assets** (the original goes in `sources`) · **build an asset** (no template exists, people repeat the same shape) · **none**.

| Name | Signature or usage | What it guarantees | Template | Source |
| --- | --- | --- | --- | --- |

## Vocabularies

What an agent guesses wrong. "Goes with" lists values that require, or exclude, each other.

| Term | Values | Default | Consequence of a wrong value | Goes with | Source |
| --- | --- | --- | --- | --- | --- |

## Facts

Conventions, config, guardrails, gotchas: what the consumer would otherwise dig out of the code. "Needed by" lists the tasks that need it; a fact two or more tasks need is shared material (`references/analyze.md`). Layer: `skill:<name>` · `agents-md:<path>` · `instructions` · `catalog-comment` · `script:<skill>` · `drop`.

| Fact | Kind | Needed by | Layer | Source |
| --- | --- | --- | --- | --- |
