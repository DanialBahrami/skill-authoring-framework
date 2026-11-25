# Review checkpoint (after step 5)

For the person reviewing the run before any skill is written. Fifteen minutes here saves rewriting skills later: every skill is built from these three files.

## coverage.md

- [ ] The folders that matter for this team are there, marked production, shared library, team-owned or tooling, and read at least "sampled".
- [ ] Nothing was taken from ad hoc, archive or generated folders.
- [ ] Folders read only by name are listed in `backlog.md`, not silently dropped.

## inventory.md

- [ ] The tasks are ones people really repeat, named the way the team names them. Missing an important one? Add it with its source.
- [ ] Sub-steps are in the order people do them; "asked for on its own" is right (that decides what becomes a separate skill).
- [ ] Helper names and signatures match the code (open two or three sources and check).
- [ ] Every vocabulary has its default and what goes wrong with the wrong value.
- [ ] Every destructive operation (drop, overwrite, full reload, deleting checkpoints) is listed as a guardrail.
- [ ] The template decision per template makes sense: the repo's own templates are named, not copied, unless the task starts outside the repo.
- [ ] No environment values (catalog names, hosts, ids) are presented as conventions.

## conflicts.md

- [ ] Each suggested decision has a reason you agree with. Accept in one reply ("accept all except 3 and 7"), or decide by number.
- [ ] Rows that break a shared convention are decided by number, with the platform team.
- [ ] Docs-versus-code rows say which side is right; the page owner gets the other side as "Docs to fix".

Then tell the meta-skill to continue from step 6.

## skill-map.md (after step 6, before any skill is written)

The meta-skill shows the planned family before generating. This is the cheapest moment to change its shape.

- [ ] Every skill is a task people ask for on its own; nothing exists only to be reused by other skills.
- [ ] No two skills cover the same task; another team's way is a variant inside the skill, not a second skill.
- [ ] Nothing marked "new" duplicates an existing skill.
- [ ] Every "updated" skill names the eval case that fails with it today; an update without one is just more facts, so drop it.
- [ ] Changes to another team's skills are marked "proposed", and that team has been asked.
- [ ] Arrows go from a workflow to the skills it names at a step, at most two levels deep; platform skills never use team skills.
- [ ] Shared rules went to the `AGENTS.md` candidates, not into a skill of their own.
- [ ] With `catalog.installed_skills: use`: no planned skill duplicates an installed one.

Reply "go", or say what to merge, split or drop.
