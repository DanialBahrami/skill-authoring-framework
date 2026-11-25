# The context standard

The one definition of good agent context: skills, `AGENTS.md`, always-on instructions and catalog comments. The meta-skill writes to it, `skillkit lint` enforces the checkable parts, reviewers check the rest. It builds on the [Agent Skills specification](https://agentskills.io/specification) and [AGENTS.md](https://agents.md/), and is stricter where a shared workspace needs it. Limits live in `assets/defaults/standard.yaml`; a `standard.yaml` in the output folder overrides them.

## Contents

- 1. What goes where
- 2. Token budget
- 3. Skill folder and skill.yaml
- 4. SKILL.md: name, description and sections
- 5. Writing skills that work
- 6. Teams, variants and skills that use skills
- 7. Ownership and freshness
- 8. Review checklist
- 9. Lint rules
- 10. Glossary

## 1. What goes where

Put each piece of knowledge in the cheapest layer that works. Names differ by agent: always-on instructions are, for example, Databricks workspace instructions, `CLAUDE.md` or `.github/copilot-instructions.md`; catalog comments are, for example, Unity Catalog comments and tags.

| Layer | Loaded | Use for | Owner |
| --- | --- | --- | --- |
| Always-on instructions | Every response | Short rules that are always true: environments, hard constraints, PII guardrails | Platform team |
| `AGENTS.md` | When a file under its folder is open; nested files stack | Conventions and vocabulary of a repo or team folder | Repo or folder owner |
| Skill | Name and description always; body when triggered | A repeated task with organisation-specific steps | Team registered for the prefix |
| Catalog comments and tags | When the agent inspects a table | Facts about data: meaning, grain, source, PII | Data owner |

A skill is justified only when all three hold:

1. It describes a **task** someone repeats and asks for on its own ("onboard a source table"), not a topic ("PySpark patterns").
2. Without it, the agent gets the task wrong or inconsistent, or has to read the code to get it right; the baseline eval shows which.
3. The content is specific to your organisation; public documentation and skills the agent already has are known to it.

Scope each skill to one coherent task. Too narrow, and one request needs several skills loaded together; too broad, and the description cannot say precisely when to use it.

`AGENTS.md` holds only what the agent cannot infer from the code and docs: vocabulary, conventions, contract rules, non-obvious commands. People write it; the meta-skill proposes lines with evidence. Generated context files measurably lowered agent success and raised cost by over 20%, while short human-written ones helped ([ETH Zurich](https://arxiv.org/html/2602.11988v1)).

## 2. Token budget

| Level | When it costs | Budget |
| --- | --- | --- |
| Always-on instructions | Every response, every user | About 4,000 tokens (Databricks workspace instructions ignore text past 20,000 characters) |
| Skill name and description | Every session, for every installed skill | 80–1,024 characters each; about 10,000 tokens for the whole catalog |
| `SKILL.md` body | Each time the skill triggers | 500 lines and about 5,000 tokens |
| `AGENTS.md` | When a file in its folder is open | 500 lines |
| `references/`, `scripts/`, `assets/` | Only when opened or run | No limit; files over 100 lines start with a `## Contents` list |

Tokens are estimated as characters / 4. The limits are ceilings, not targets: less text often works better.

- **No runtime reads of static knowledge.** A skill never sends the agent to the code, a repo, a wiki or an MCP server for a convention: bake it in at authoring time and record the source in `skill.yaml`. Reading the source on every use is the cost a skill exists to remove. Runtime lookups are for live state only.
- **Detail goes down a level.** Long tables, templates and edge cases go in `references/` or `assets/`, linked from the step that needs them.
- **The catalog budget caps the number of skills.** When it is full, merge or retire a skill before adding one.

## 3. Skill folder and skill.yaml

```
skills/<prefix>-<verb>-<object>/
├── SKILL.md        runtime: frontmatter + body
├── references/     runtime, optional: detail opened on demand, each file linked from SKILL.md
├── assets/         runtime, optional: templates the agent copies
├── scripts/        runtime, optional: code the agent runs
├── skill.yaml      repo only: the registry record
└── evals/
    └── evals.json  repo only: eval cases (references/evals.md)
```

`skill.yaml` and `evals/` are never deployed. The build stamps `owner` and `source-commit` into the deployed `SKILL.md` `metadata`.

`skill.yaml` fields:

- `owner`: the team registered for the prefix. `status`: `draft` (linted, not deployed), `active` (deployed) or `deprecated` (not deployed, kept until removed). `last_reviewed`: a date.
- `sources`: where the knowledge came from; drives the freshness checks. Repo sources give the repo name and the narrowest globs that cover what the skill was distilled from (too broad and every PR flags the skill, too narrow and changes go unnoticed). Confluence sources give `page_id`, `title`, `version`, in that order. Other docs give `doc:` with `url` and `title`. Knowledge with no written source gives `note:` with who agreed it.
- `uses`: skills it names in its steps. `requires`: MCP servers, packages or services. `supersedes`: repo or installed skills it replaces once active.
- Optional: `eval: max_tokens` for answers that span several files; `variants` (section 6).

## 4. SKILL.md: name, description and sections

**Frontmatter.** `name` and `description` are required; the specification's optional fields (`license`, `compatibility`, `metadata`) are allowed; nothing else.

- `name`: `<team-prefix>-<verb>-<object>`, lowercase with single hyphens, equal to the folder name, at most 64 characters. Example: `dp-onboard-source-table`. Never vague (`helper`, `utils`, `data`).
- `description`: the agent sees only names and descriptions when it picks a skill, so this field alone decides whether the skill loads. 80–1,024 characters; a few sentences is usually right, since every description is paid in every session.
  - Third person. First what the skill does, then `Use when` and the situations, in terms of what the user wants, not how the skill works.
  - Use the words people type: the task in the team's words, table, helper and layer names, phrasing from PR titles. Include the cases where the user does not name the domain ("…even if they only ask to add a column").
  - Agents consult skills for tasks that need knowledge they do not have, so say what organisation-specific knowledge the skill carries ("our merge helper", "the release branch rule").
  - When a neighbouring skill shares vocabulary, end with what this one is not for ("Not for changing an existing table").
  - Good: "Creates a Silver table and its notebook from a Bronze source with the team's merge helper, audit columns and PII tags. Use when the user asks to build, add or onboard a silver table, or to move a bronze table to silver. Not for changing an existing silver table."
  - Bad: "Helps with Silver tables." (no trigger terms) or "This skill uses `merge_table_silver` to…" (implementation, not intent).
  - Tune it with trigger cases (references/evals.md): when it fails to load, broaden it with the situation, not with the exact words of the failed prompt.

**Body.** One or two lines saying what the task produces, then these sections in this order:

- `## Steps` (required): numbered, imperative, one objective each.
- `## Verify` (required): how the agent confirms the whole result before reporting back, as queries or commands.
- `## Recovery` (required): a symptom | cause | fix table.
- Optional: `## Gotchas`, `## Rules`, `## Examples`, `## References`. No other sections: no "Before you start", decision trees, troubleshooting catalogues or related-skill lists.

No dates or version notes (history lives in Git), no `TODO` in an active skill, one term per concept, forward slashes in paths. Reference files are linked from `SKILL.md` and do not link further.

## 5. Writing skills that work

**Write for a consumer that does not read the source.** The agent should finish the task from the skill alone: each time it opens the code to find a convention it spends tokens and guesses from what it opened. Write in what the task needs:

- the helper to call and its signature, with the reason to use it;
- a complete example, copied from tests or production code, with environment values as variables;
- the templates it copies, in `assets/`;
- where files go, as a short tree in the step that writes them;
- the vocabularies the task touches (term, values, default, consequence, what goes with what);
- live state as the query that fetches it.

Never "see the file", "read the README" or "look at the other notebooks" (lint warns with SK028). A repo path appears only as where to write a file or what to call or import. Assume the agent is capable: leave out what it gets right without being told, and test each line with "would the agent get this wrong without it?"

**Steps.** One action per step, in the order the agent acts. Add one line of reasoning only where the step differs from default practice: "Use `merge_table_silver`: it adds the audit columns and deduplicates on the business key" lets the agent handle cases the skill did not foresee. Write in what the step needs (signature, parameter names, the convention), copied from the source. Read-only steps come before anything that writes.

**Checks and recovery.** Without them the agent improvises after an error: it retries, wastes turns, or "fixes" the problem in a way nobody accepts, such as creating the table in a schema where it does have rights.

- A step that runs something (a command, SQL, a deploy) ends with `Check:` and the observable result that means it worked: an exit code, a `DESCRIBE TABLE` with the expected columns.
- `## Recovery` lists the failures the steps can realistically hit, usually three to six, taken from error handling in the code, troubleshooting pages and review comments; never invented. A fix says what to change, or when to stop and what to tell the user. "Try again" is not a fix. Where improvising would do harm (permissions, an existing table, production), the fix is to stop and ask.

```
| Symptom | Cause | Fix |
| --- | --- | --- |
| `PERMISSION_DENIED` on CREATE TABLE | The principal lacks a grant on the schema | Stop and say which grant is missing; never create the table in another schema |
| The table exists with a different schema | An earlier onboarding failed half-way | Stop and report the difference; do not drop the table |
```

**Decisions.** A decision is a step with its condition, default first: "Choose the load type: `incremental` with the source's business key. If the source sends a full extract every day and has no key, use `full` instead." Not a tree, not a menu of equal options. More than two outcomes people really use: a table under `## Rules` or in a reference file, the default in the step.

**How exact to be.** Match the wording to how fragile the step is.

| The step | Write |
| --- | --- |
| Has many valid ways and depends on context | The rule and its reason |
| Has a preferred pattern with some variation | A template and what may change in it |
| Breaks when done slightly differently (a deploy command, a merge call) | The exact command or call, to copy as is |

**Risky steps.** Put the guard in the step where the risk occurs: "If the schema change is breaking (rename, type change, new key), stop: offer a new column or table first, and run a full reload only after the user explicitly agrees."

**Gotchas.** Facts that defy a reasonable assumption are often the most valuable lines: "the `pii` tag is set on the column, not the table". Leave out anything the agent gets right anyway.

**Examples and assets.** Copy examples from working code or tests; never invent one. An example is complete, with environment values as variables or widgets. Per template:

| Situation | Do |
| --- | --- |
| The repo has a template people copy | Copy it into `assets/` and list the original in `sources`, so the freshness check flags it when the original changes |
| No template, but people produce the same shape again and again | Build an asset from two or three real examples, parts to fill marked `<like_this>` |
| A small step the agent gets wrong by reasoning | A script in `scripts/`; say whether the agent runs or reads it and what its output means |

**Leave out** anything in public documentation or a skill the agent already has, background the agent knows, conventions every task needs (they go to `AGENTS.md`, once), and live state (give the query).

**Before and after** (fictional):

```
## Steps
1. Read the Silver README and look at the other Silver notebooks to understand the conventions.
2. Create the table following best practices.
```

```
## Steps
1. Copy `assets/silver_notebook.py` next to the Bronze notebook and set the widgets `source_table` and `business_key`.
2. Merge with `merge_table_silver(df, target, keys=[business_key])`: it deduplicates on the key and adds `_loaded_at`; do not write a MERGE by hand.
3. Tag every PII column with `pii`; untagged PII columns are not masked downstream.
   Check: `DESCRIBE TABLE` on the target lists `_loaded_at`, and the PII columns carry the `pii` tag.
```

## 6. Teams, variants and skills that use skills

- The platform team keeps a short **contract** in the repo's root `AGENTS.md`: the few rules every team follows. A team's `AGENTS.md` in its folder states each override of the root file explicitly, because agents differ in which file wins.
- **One skill per task across teams.** When a team does a shared task differently, step 1 states the condition and links `references/<team>.md`; `skill.yaml` declares it under `variants` with its owner and `applies_when`. A task only one team does gets that team's prefix. A difference that breaks the contract is fixed, never a variant.
- **Using another skill.** Name it at the step that needs it, with what to pass ("Ingest to Bronze: follow the `dp-configure-autoloader` skill with …"), list it in `uses`, never copy its steps. Only skills that are tasks people also ask for on their own. Depth at most two, no cycles, platform skills never use team skills. A skill that uses others gets a journey (references/evals.md); when a skill changes, every skill that uses it is re-evaluated.

## 7. Ownership and freshness

`skill.yaml` is the registry record. Authors cannot approve their own changes. The linter warns on scripts, network calls, external URLs and paths outside the skill; a reviewer checks each against the skill's purpose.

A skill changes only when something shows it fails or is about to:

| Trigger | Evidence | Change |
| --- | --- | --- |
| A wrong answer, or a failing eval | The prompt | Add it as an eval case that fails today, fix the skill, see it pass |
| A source changed (helper renamed, page rewritten) | The diff, or the freshness check | Update the facts that changed, nothing else |
| Another team does the task differently | A decision "Variant" | Add the variant |
| The review date passed | Age | The owner re-checks; often nothing changes |

Finding more facts is not a trigger. Freshness is detected by a source-repo PR hook (changed paths match `sources`), a weekly comparison of Confluence page versions, and the review period; see `ops/operating.md` in the framework repo.

## 8. Review checklist

For the reviewer, and for checking by hand when the scripts cannot run.

- [ ] It is one task people ask for, and the eval verdict is ADDS VALUE.
- [ ] Nothing restates public documentation or a skill the agent already has; nothing belongs in the always-on instructions, `AGENTS.md` or the catalog instead.
- [ ] The description says what the skill does and when to use it, in the words people type, and does not overlap another skill; the near miss is a real near miss.
- [ ] The agent can do the task from the skill alone: no step sends it to the code, a README or a wiki; examples are complete; templates are in `assets/`.
- [ ] Folder name equals `name`; body under 500 lines with `## Steps`, `## Verify`, `## Recovery` in order.
- [ ] Rules carry their reasons; one default per decision; a guard at each risky step.
- [ ] Every step that runs something has a `Check:`; every Recovery fix is real, with a stop where improvising would harm.
- [ ] Every name in it exists in the code (`check-names`); no catalog names, hosts, emails, IDs, tokens, dates.
- [ ] Every skill named in the body is in `uses`; every skill that uses others has a journey.
- [ ] `skill.yaml` has owner, status, `last_reviewed` and narrow `sources`; variants are team differences, not contract breaks.
- [ ] `evals.json` has two trigger cases and a near miss, and a trajectory whose `avoid` items name wrong paths that matter for this task.
- [ ] Every security warning is explained; the reviewer is not the author.

## 9. Lint rules

| Code | Checks |
| --- | --- |
| SK001–SK006 | `SKILL.md` exists; frontmatter fields; name pattern, folder match, registered prefix; description length and "Use when" |
| SK007–SK009 | Body size; required and allowed sections |
| SK010–SK012 | Links resolve; reference files don't link further; long references start with `## Contents` |
| SK013 | No catalog names, hosts, emails, GUIDs, tokens or dated notes in deployed files |
| SK014–SK016 | `skill.yaml` fields; `evals.json` minimums and trajectory shape; variants |
| SK017–SK019 | No `TODO` in active skills; no stray files; deprecated notice |
| SK020 | Security review warnings: scripts, network calls, external URLs, paths outside the skill |
| SK021 | `uses` matches the skills named in the body; dependencies exist and are active |
| SK022 | `supersedes`: not itself; a superseded repo skill is deprecated once this one is active |
| SK023 | An assertion needs facts the model cannot know without running anything (warning) |
| SK024 | Assets: Python compiles, YAML and JSON parse |
| SK025 | `## Recovery` is a symptom/cause/fix table; no fix that only says to try again |
| SK026 | A step that runs something has a `Check:` line (warning) |
| SK027 | At least one trigger case has a trajectory (warning) |
| SK028 | A step or reference sends the agent to the code, the repo, a README or a wiki (warning) |
| CT001–CT004 | Catalog budget; duplicate names; description overlap; dependency cycles, depth and direction |
| JR001–JR002 | `journeys.json`: ids, prompt, known skills; every skill reachable from the first through `uses` (warning) |
| WI001–WI004 | Always-on instructions: size, token budget, no emails or tokens, not the framework's example |
| AG001–AG002 | `AGENTS.md`: size, no emails or tokens |

## 10. Glossary

- **Author / consumer**: the agent running this meta-skill, which has the repo, docs and history / the agent using the skills later, which should do each task from the skill alone, without reading the source.
- **Output folder**: where skills, `evals/journeys.json` and runs are written. **Run folder**: `authoring/runs/<date>-<scope>/`, one per run. **Context repo**: an output folder kept in Git, with CI and deployment (`ops/`).
- **Skill family**: all skills in the output folder. **Layer**: where a fact goes (section 1). **Contract**: the rules every team follows, in the root `AGENTS.md`.
- **Platform team**: owns the contract and the always-on instructions. **Owning team**: the team registered for a skill's prefix.
- **Variant**: another team's way of a shared task, inside the same skill. **Uses**: a skill named at a step of another.
- **Eval case**: a prompt with checks. **Trigger / near miss**: a prompt that should / should not load the skill. **Trajectory**: checks on the path to the answer (order, avoid). **Journey**: an eval case for a task that chains skills.
- **Baseline**: the same eval without the skill. **Verdict**: ADDS VALUE, NO EFFECT, FAILING or INCONCLUSIVE. **Decoys**: stand-ins for skills the agent already has, in the routing test. **Execution gate**: planning the SQL of eval answers with `EXPLAIN` on a development warehouse.
- **Catalog budget**: the tokens all descriptions together may use. **Installed skills**: skills already installed from outside the output folder. **Supersedes**: skills a skill replaces once active.
