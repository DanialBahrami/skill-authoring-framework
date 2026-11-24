# Coverage: <scope>

Filled before the inventory, updated as you read. It shows what this run is based on, so a partial run is visibly partial and the next run knows where to continue.

Kind: **production** (deployed code), **shared library** (helpers and templates others call), **team-owned** (a team's production folder with its own conventions), **tooling** (CI, deployment scripts, bundle files), **ad hoc** (personal or exploratory scripts, one-off fixes, proofs of concept), **archive** (old, unused, superseded, backups), **generated** (build output, exports). Conventions and examples come only from production, shared-library, team-owned and tooling folders; ad hoc folders may still show gotchas.

Read: **all** (every file), **sampled** (which files and why, in Notes), **searched** (counts and patterns with grep; the command in Notes), **names only** (file and folder names), **skipped**.

| Folder | Files | Kind | Owner | Read | Verdict | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| <path>/ | <n> | production / shared library / team-owned / tooling / ad hoc / archive / generated | <team> | all / sampled / searched / names only / skipped | in scope / backlog / out of scope | <which files, why, or the grep command> |

A folder read only by names, or skipped, cannot produce a skill in this run: its tasks go to `backlog.md`. Never copy a pattern from an ad hoc, archive or generated folder into a skill.

## Docs read

| Page or file | Id and version | Useful? | Contradicts the code? | Note for the page owner |
| --- | --- | --- | --- | --- |
| <title or path> | <page id, version> | yes / thin (links or headings only) / no | no / yes: <where> | <what to fix> |

## Not covered

<Folders or docs in scope that were not read closely enough to generate from. Each one goes to backlog.md.>
