# Output contract for generated skills

These are the defaults (`assets/defaults/standard.yaml`). A `standard.yaml` in the output folder overrides the limits, prefixes and sections. The `lint` script enforces most of this; the rest is checked in review, or by hand when the scripts cannot run.

## Output folder

```
<output folder>/                       the user's choice, or /Workspace/Users/<current user>/genie-skills/
├── skills/<name>/                     one folder per skill (below)
├── evals/journeys.json                tasks that chain skills
├── standard.yaml                      optional overrides of assets/defaults/standard.yaml
└── authoring/runs/<YYYY-MM-DD>-<scope>/   the run's working files, proposals and summary
```

Drafts stay here until a person reviews them: copying an approved skill into the workspace skills folder, applying `AGENTS.md` lines, instruction changes and table comments are left to their owners. A Git folder works too, when changes should go through pull requests.

## Skill folder

```
skills/<prefix>-<verb>-<object>/
├── SKILL.md        frontmatter (name, description; optional license, compatibility, metadata) + body
├── references/     optional, detail opened on demand; each file linked from SKILL.md
├── assets/         optional, templates the agent copies, per the assets rule in writing-skills.md
├── scripts/        optional, code the agent runs
├── skill.yaml      owner, status: draft, last_reviewed: today, sources, uses, requires, supersedes, variants
└── evals/
    └── evals.json  Agent Skills eval layout; at least 2 trigger cases, 1 near_miss
```

## Description (decides triggering)

- Third person, 80-1,024 characters; aim for a few hundred, since every description is paid in every session. First what the skill does, then `Use when` and the situations and words people type (table names, helper names, "add a column", "silver notebook").
- End with what it is not for when a neighbouring skill shares vocabulary ("Not for changing an existing table").

## Body (at most 500 lines, about 5,000 tokens; shorter is usually better)

- One or two lines saying what the task produces.
- `## Steps`: numbered, imperative, one objective each. One line of reasoning on each step that differs from default Databricks practice. A step that runs something ends with a `Check:` line (see "Checks and recovery" in writing-skills.md).
- `## Verify`: the checks the agent runs on the end result before reporting back, as queries or commands.
- `## Recovery`: a symptom | cause | fix table of the failures the steps can hit, from the sources. A fix says what to change or when to stop and ask; "try again" is not a fix.
- Optional `## Gotchas` (facts that defy reasonable assumptions; often the highest-value content), `## Rules`, `## Examples`, `## References`. No other sections: no "Before you start", decision trees, troubleshooting catalogues or related-skill lists. A decision is a step with its condition. Troubleshooting beyond the steps' own failures is a reference file.
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
   "assertions": ["observable result"],
   "trajectory": {"order": ["regex of an earlier step", "regex of a later step"], "avoid": ["a wrong path"]}},
  {"id": "...", "type": "near_miss", "prompt": "...", "expect_skill": "<other skill or null>"}
]}
```

- Trigger prompts as a developer would type them, in different words from the description, with real context (table names, paths). Include at least one that needs the skill without naming its domain.
- `must_include` for names that must appear (helpers, templates, conventions); `must_not_include` for hardcoded environment values and the wrong approach (for example a hand-written MERGE where a template exists).
- `assertions` for observable behaviour (asks for consent, verifies uniqueness, does not read PII rows). Drop assertions that pass with and without the skill; they show nothing.
- `trajectory` on at least one trigger case, to check the path to the answer: `order` lists regexes that must appear in that order (validate before deploy, a read-only check before a write); `avoid` lists actions the judge must not find in the plan ("reads repository files to look up the naming convention", "creates the table in another schema"). Use `avoid` for the token-costly or risky detours this task invites, not for generic bad behaviour.
- Every expected behaviour must be achievable without running anything: the eval model cannot run code, query data or know today's date. Expect what it would do ("gives the query that lists the downstream tables", "names the branch `Development-Release-<date>`"), never results ("lists the downstream tables", "uses the actual branch name").
- When good answers span several files and get cut off, set `eval: max_tokens` in `skill.yaml` instead of shortening the case.
- At least one near miss that shares vocabulary but belongs to another skill or to none; set `expect_skill` when the right skill is known.
- `agents:` lists the `AGENTS.md` files Genie Code would have loaded for that prompt.
- `exec_new_tables:` / `exec_new_columns:` (optional) regexes of tables, and names of columns, the task creates and that do not exist yet, so the execution gate does not count them as invented. Columns added with `ALTER TABLE ... ADD COLUMN(S)` in the answer are recognised without listing them.
- `must_not_include` for environment values (catalog names, storage accounts, hosts) targets the place where the value does harm, not every mention: a literal catalog as the target of DDL or DML, or a literal value in bundle YAML, fails; a widget default or a development-only check the repo itself uses does not. Try a new pattern against a few lines of real repo code before adding it, or it fails good answers.

## evals/journeys.json (output folder)

A skill that uses other skills gets a journey: `id`, `prompt` (a task that needs the chain), `skills` (where it starts first, then the skills it hands over to), and the same `agents`, `must_include`, `must_not_include`, `assertions`, `trajectory`, `exec_new_tables` and `exec_new_columns` as a case. Every skill after the first must be reachable from it through `uses`, because that is the only way Genie Code gets there. Check what only passes when the hand-over worked: a name from a later skill, the table one step creates being the one the next step uses.
