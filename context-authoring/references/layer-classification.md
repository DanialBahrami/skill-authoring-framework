# Layer classification

Ask the questions in order; the first yes decides.

| # | Question | Layer | Example |
| --- | --- | --- | --- |
| 1 | Is it in public Databricks documentation or a built-in Databricks skill? | Drop it | MERGE semantics, CLI flags, MLflow APIs, Auto Loader options |
| 2 | Is it a fact about one table, column or model (meaning, grain, source system, PII)? | Unity Catalog comment or tag (`uc-comments.sql`) | "One row per customer per day"; "Champion model for churn" |
| 3 | Must it hold in every Genie Code response for every user in the workspace, even with no repo file open? | Workspace instructions (`workspace-instructions.diff.md`) | Environment table, never read PII rows, never write to production by hand |
| 4 | Is it a convention or vocabulary that any task in one repo or folder needs? | `AGENTS.md` of that repo or folder | Naming rules, technical columns, folder layout, release branches, model naming |
| 5 | Is it a sequence of steps for a task people repeat, with organisation-specific choices? | Skill | Onboard a source table, register and promote a model, publish a dashboard, prepare a PR |
| 6 | Is it deterministic work (a lookup, a check, a generated snippet)? | `scripts/` inside the skill that needs it | Derive a storage path from widgets; list a job's last runs |
| 7 | None of the above | Drop it, or ask the user | History of a decision, meeting notes |

Notes:

- `AGENTS.md` holds only what the agent cannot infer from the code and docs it can already read: vocabulary, conventions, contract rules, non-obvious commands. No overviews, no restating the README. A study of context files found generated ones slightly reduced success and raised cost by over 20%, while short human-written ones helped; so you propose candidate lines and people write the file.
- Workspace instructions cost tokens on every response. Propose a line there only if a wrong answer would be harmful or the rule applies across repos.
- `AGENTS.md` loads only when a file in that folder is open. Tasks that start outside the repo (monitoring questions, data lookups asked in the SQL editor) must carry the vocabulary they need inside the skill.
- A long table of values that a skill needs only sometimes goes in that skill's `references/`.
- Live state (current table list, today's failed jobs) is never copied; the skill gives the query.
