# Genie Code context standard

Every piece of Genie Code context in your organisation follows this standard. It builds on the open Agent Skills specification and the AGENTS.md format, and is stricter where a shared workspace needs it. `skillkit lint` enforces the checkable parts; reviewers enforce the rest. Limits live in `standard.yaml` so they can be tuned without editing this file. The README describes the meta-skill that drafts this context; `docs/operating.md` describes running it at scale.

## 1. What goes where

Context reaches Genie Code through four layers. Put each piece of knowledge in the cheapest layer that works.

| Layer | Loaded | Use for | Owner |
|---|---|---|---|
| Workspace instructions | Every response | Short rules that are always true: environments, hard constraints, PII and GDPR guardrails | Platform team |
| `AGENTS.md` | When a file under that folder is open; Genie Code walks up the tree, so nested files stack | Conventions and vocabulary of a repo or a team folder | Repo or folder owner |
| Workspace skill | Name and description always; body only when triggered | A repeatable task that needs organisation-specific steps | Team registered for the prefix, reviewed by platform |
| Unity Catalog comments and tags | When the agent inspects a table | Facts about data: meaning, grain, source system, PII | Data owner |

`AGENTS.md` holds only what the agent cannot infer from the code and docs: vocabulary, conventions, contract rules, non-obvious commands. People write it; the generator proposes candidate lines with evidence. (Measured: generated context files slightly lowered success and raised cost by over 20%; short human-written ones helped.) It gets its own with/without eval (`skillkit eval-context`).

A skill is justified only when all three hold:

1. It describes a **task** someone does repeatedly ("onboard a source table"), not a topic ("PySpark patterns").
2. Genie Code gets it wrong or inconsistent **without** the skill, shown by the baseline eval (section 5).
3. The content is specific to us. Public Databricks documentation and built-in skills are already known to the agent.

`AGENTS.md` loads only inside the repo. Tasks that usually start outside it (monitoring questions, data-source questions in the SQL editor) carry the vocabulary they need inside the skill.

## 2. Token budget

| Level | When it costs | Budget |
|---|---|---|
| Workspace instructions | Every response, every user | About 1,500 tokens; Databricks ignores text past 20,000 characters |
| Skill name and description | Every Agent-mode session, for every installed skill | 80–600 characters each; about 2,500 tokens for the whole catalog |
| `SKILL.md` body | Each time the skill triggers | 200 lines and about 2,500 tokens |
| `AGENTS.md` | When a file in its folder is open | 300 lines |
| `references/`, `scripts/`, `assets/` | Only when opened or run | No limit; files over 100 lines start with a `## Contents` list |

Token counts are estimated as characters / 4.

- **No runtime reads of static knowledge.** A skill must not tell the agent to browse a repository, wiki or MCP server for conventions. Distil the convention at authoring time and record the source in `skill.yaml`. Runtime lookups are for live state only.
- **Detail goes down a level.** Long tables, templates and edge cases go in `references/` or `assets/`, linked from the body with a note on when to open them.
- **Deterministic work goes in `scripts/`.** A script costs only its output.
- **The catalog budget caps the number of skills.** When it is full, merge or retire a skill before adding one.

## 3. Folder layout

```
skills/<name>/
├── SKILL.md        runtime: instructions
├── references/     runtime, optional: detail loaded on demand
├── assets/         runtime, optional: templates the agent copies
├── scripts/        runtime, optional: code the agent runs
├── skill.yaml      repo only: owner, status, review date, sources, uses, requires, variants
└── evals/
    └── evals.json  repo only: test cases (Agent Skills layout)
```

`skill.yaml` and `evals/` are stripped at build time and never reach the workspace. The build stamps `owner` and `source-commit` into the deployed `SKILL.md` `metadata`, and records a SHA-256 checksum per file in a manifest deployed next to the skills.

## 4. SKILL.md

### Frontmatter

`name` and `description` are required. The specification's optional fields (`license`, `compatibility`, `metadata`) are allowed; nothing else.

- `name`: `<team-prefix>-<verb>-<object>`, lowercase with single hyphens, equal to the folder name, at most 64 characters. Prefixes are registered in `standard.yaml`. Example: `dp-onboard-source-table`.
- `description`: 80–600 characters (the specification allows 1,024; every description is paid in every session), third person, says what the skill does and then when to use it. It contains "Use when" followed by the situations and the terms people actually type. When a neighbouring skill shares vocabulary, end with what this one is not for. This field alone decides whether the skill triggers.

### Body

Required sections, in this order: `## Steps` (numbered, imperative) and `## Verify` (how the agent confirms the result before reporting back). Optional: `## Gotchas` (facts that defy reasonable assumptions), `## Rules`, `## Examples`, `## References`. No other sections.

- State only what differs from default Databricks practice, with one line of reasoning per rule.
- One default per decision. An alternative appears only with the condition that selects it.
- Never hardcode environment-specific values (catalogs, workspace URLs, IDs, emails, secrets). Refer to bundle variables, widgets or the environment table in the workspace instructions.
- No dates or version notes. History lives in Git.
- Link reference files from `SKILL.md`. Reference files do not link to further files.
- One term per concept throughout.
- No `TODO` markers in an active skill.
- Using another skill: name it at the step that needs it and list it in `uses`; never copy its steps. A building block exists only if people also ask for that task on its own. Depth at most two (workflow, block, block), no cycles, and platform skills never use team skills.

## 5. Evals

Each skill carries `evals/evals.json` with at least two `trigger` cases and one `near_miss` case; more are expected for active skills (the Agent Skills guide suggests about 20 trigger queries, half near misses). Trigger cases state observable results with `must_include`, `must_not_include` and `assertions`; cases list the `AGENTS.md` files Genie Code would have loaded.

`skillkit eval` runs, for every case and `--runs` times: a routing test (the model sees the whole catalog plus decoys for built-in skills and picks a skill; passes on a trigger rate of 0.5), and for trigger cases an answer test with the skill and without it (passes on a majority of runs). Skills in `uses` are available in both arms, so a workflow is measured against its building blocks. The report shows the extra tokens per answer the skill costs. The verdict per skill:

- **ADDS VALUE**: every case passes, and at least one passes only with the skill. Required to merge.
- **NO EFFECT**: the model already gets it right. Do not merge; move any single useful rule to `AGENTS.md`.
- **FAILING**: a routing or answer case fails.

The PR pipeline runs this for changed skills (3 runs) and, for coexistence, the routing test for every active skill, and posts the report on the PR. During the pilot the eval gate is advisory; it becomes blocking once the suite is stable. Before activating a new skill, the author also runs two cases in a real Genie Code Agent-mode chat and notes the outcome in the PR.

## 6. Ownership and freshness

`skill.yaml` is the registry record. It holds `owner` (the team registered for the prefix), `status` (`draft`: linted, not deployed; `active`: deployed; `deprecated`: not deployed, kept until removed), `last_reviewed`, `sources` (repo globs, Confluence page id + version, or a note), `uses` (skills it names), `requires` (MCP servers, packages, services) and optional `variants`.

Security: the linter warns on scripts, network calls, external URLs and paths outside the skill; any such warning needs a reviewer to check it against the stated purpose. Authors cannot approve their own changes (branch policy).

Freshness is checked in three ways:

- **Source change.** A source repo's PR build runs `skillkit freshness` and comments on the PR with the affected skills and owners.
- **Confluence change.** The weekly pipeline compares recorded page versions with the live pages.
- **Age.** The weekly pipeline fails for active skills not reviewed within the period in `standard.yaml`.

## 7. Multi-team repositories

- The platform team defines a short **contract** in the repo's root `AGENTS.md` that applies in every folder. Inside it, teams choose how they work.
- A team's conventions go in an `AGENTS.md` in its folder. It states each override of the root file explicitly: the AGENTS.md convention is that the nearest file wins, but Genie Code does not document its precedence, and conflicting instructions make agents behave unpredictably.
- One skill per task across teams. When a team does a shared task differently, step 1 of the skill states the condition and links `references/<team>.md`; `skill.yaml` declares it under `variants` with the owning team. Tasks only one team does get that team's prefix.
- A difference that breaks the contract is fixed, not documented as a variant.

## 8. Authoring

Skills are drafted by the `context-authoring` generator from code and Confluence, then maintained by hand in pull requests. The generator is rerun in update mode for one skill when its sources change; its output is reviewed as a diff. Hand-written skills follow the same lint, eval and review.

## 9. Review checklist

The platform reviewer checks what the linter cannot:

- [ ] It is a task, and the eval verdict is ADDS VALUE.
- [ ] Nothing restates public Databricks documentation or a built-in skill.
- [ ] The content does not belong in workspace instructions, `AGENTS.md` or Unity Catalog instead.
- [ ] The description does not overlap an existing skill; the near-miss case is a real near miss.
- [ ] Rules carry their reasons; there is one default per decision.
- [ ] Variants are legitimate team differences, not contract breaks.
- [ ] `sources` lists where the knowledge came from, with narrow globs.
- [ ] Every security warning (scripts, network calls, URLs) is explained by the skill's purpose.
- [ ] No overlap warning left unexplained; the coexistence routing run shows no regression.
- [ ] Reviewer is not the author.
