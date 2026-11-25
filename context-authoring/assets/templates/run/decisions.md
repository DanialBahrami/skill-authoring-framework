# Decisions: {{scope}}

Filled by the meta-skill, which carries on without waiting; people review this file through `report.md`. A decision stands for later runs once it has a name under "Reviewed by". To change one, edit its row: the next run updates the skills it lists (`references/update.md`).

## Conflicts

Team against team, docs against code, new content against existing context. Decide from evidence: what the code does more often, what the contract or the docs require, which side is newer.

- **Variant**: both are legitimate; the skill gives the platform way and links `references/<team>.md` for the other.
- **Align to A / Align to B**: one way wins; the other side gets a backlog item to migrate.
- **Fix code / Fix docs**: the skill follows the decision; the fix goes to that owner.
- **Open**: the difference breaks the contract, or there is no evidence either way. Nothing that depends on it is written. A contract break is never a Variant.

| # | Topic | Approach A (source) | Approach B (source) | Breaks the contract? | Decision | Why | Skills affected | Reviewed by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Skill family

Every skill in the output folder, not only this run's. This run: **new** · **updated: <eval case that fails today>** · **variant added: <team>** · **unchanged**. Add **proposed to <owner>** when the skill belongs to another team.

| Skill | Task | Owner | Uses | This run | Why it is a skill |
| --- | --- | --- | --- | --- | --- |

## Not a skill

Tasks and shared material that went elsewhere: an `AGENTS.md` candidate, inline in the skills that need it, or the backlog.

| Task or material | Went to | Why |
| --- | --- | --- |
