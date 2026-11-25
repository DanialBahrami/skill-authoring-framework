# Skill map: <scope> (planned)

Written at step 6, before any skill is written, so the reviewer sees the planned family: which tasks become skills, which skill uses which, which team gets a variant, and which existing skills this run changes. List every skill in the output folder, not only this run's. At step 8, `catalog --map --out <run folder>/skill-map.md` replaces this file with the map generated from the skills actually written, with eval verdicts; it keeps the "This run" column.

This run: **new** (a task without a skill), **updated** (this scope adds facts to an existing skill), **variant added** (another team's way, inside the existing skill), **unchanged**.

| Skill | Task (from inventory.md) | Owner | Uses | Used by | Team variants | This run |
| --- | --- | --- | --- | --- | --- | --- |
| `<prefix>-<verb>-<object>` | <task> | <team> | `<skill>` | `<skill>` | <team> | new / updated: <what changed> / variant added: <team> / unchanged |

```mermaid
graph LR
  s1["<prefix>-<verb>-<object>"]
  s2["<skill it uses>"]
  s1 --> s2
```

Why each skill exists (a task people ask for on its own), and what was not made a skill (moved to `AGENTS.md` candidates, kept inline, or left in `backlog.md`):

- <skill>: <one line>
