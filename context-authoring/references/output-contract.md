# Output contract for generated skills

These are the defaults. A `standard.yaml` in the context repo overrides the limits, prefixes and sections. `skillkit lint` enforces most of this; the rest is checked in review, or by hand when `skillkit` is not available.

## Folder

```
skills/<prefix>-<verb>-<object>/
├── SKILL.md        frontmatter (name, description; optional license, compatibility, metadata) + body
├── references/     optional, detail opened on demand; each file linked from SKILL.md
├── assets/         optional, templates the agent copies (notebook skeletons, YAML)
├── scripts/        optional, code the agent runs
├── skill.yaml      owner, status: draft, last_reviewed: today, sources, uses, requires, variants
└── evals/
    └── evals.json  Agent Skills eval layout; at least 2 trigger cases, 1 near_miss
```

## Description (decides triggering)

- Third person, 80-600 characters. First what the skill does, then `Use when` and the situations and words people type (table names, helper names, "add a column", "silver notebook").
- End with what it is not for when a neighbouring skill shares vocabulary ("Not for changing an existing table").

## Body (200 lines, about 2,500 tokens)

- One or two lines saying what the task produces.
- `## Steps`: numbered, imperative. One line of reasoning on each step that differs from default Databricks practice.
- `## Verify`: the checks the agent runs before reporting back, as queries or commands.
- Optional `## Gotchas` (facts that defy reasonable assumptions; often the highest-value content), `## Rules`, `## Examples`, `## References`. No other sections: no "Before you start", decision trees, troubleshooting catalogues or related-skill lists. A decision is a step with its condition. Troubleshooting worth keeping is a reference file.
- Frontmatter may also use the specification's optional fields (`license`, `compatibility`, `metadata`); owner and source commit are stamped into `metadata` at build time.
- Using another skill: name it at the step ("Ingest to Bronze: follow the `dp-configure-autoloader` skill with ...") and list it in `uses`. Never copy its steps. Only name skills that are tasks people also ask for on their own; a shared rule belongs in `AGENTS.md`, a short shared step stays inline.
- Variants: when another team does the task differently, step 1 states the condition and links `references/<team>.md`; declare it in `skill.yaml` under `variants`.
- No dates, version notes or history.

## skill.yaml sources

- Repo sources: the repo name and the narrowest globs that cover what the skill was distilled from. These drive the freshness hook; too broad and every PR flags the skill, too narrow and changes go unnoticed.
- Confluence sources: `page_id`, `title`, `version` (in that order); a weekly check compares the version with the live page.
- Other docs (any wiki or website): `doc:` with `url` and `title`; reviewed by age. Docs kept in a Git repo are repo sources, so their changes are detected like code.
- Knowledge with no written source: `note:` with who agreed it.

## evals/evals.json

```json
{"skill_name": "<name>", "evals": [
  {"id": "...", "type": "trigger", "prompt": "...", "expected_output": "...",
   "agents": ["data-platform/AGENTS.md"], "must_include": ["regex"], "must_not_include": ["regex"],
   "assertions": ["observable result"]},
  {"id": "...", "type": "near_miss", "prompt": "...", "expect_skill": "<other skill or null>"}
]}
```

- Trigger prompts as a developer would type them, in different words from the description, with real context (table names, paths). Include at least one that needs the skill without naming its domain.
- `must_include` for names that must appear (helpers, templates, conventions); `must_not_include` for hardcoded environment values and the wrong approach (for example a hand-written MERGE where a template exists).
- `assertions` for observable behaviour (asks for consent, verifies uniqueness, does not read PII rows). Drop assertions that pass with and without the skill; they show nothing.
- At least one near miss that shares vocabulary but belongs to another skill or to none; set `expect_skill` when the right skill is known.
- `agents:` lists the `AGENTS.md` files Genie Code would have loaded for that prompt.
