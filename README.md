# Skill authoring framework

**`context-authoring`** is a meta-skill: a skill that builds skills. Add the folder to any agent that supports [Agent Skills](https://agentskills.io/specification) (it was built for Databricks Genie Code, which the default settings target). Ask it to create the skill family for a repo, and it reads the code and docs, identifies the tasks people repeat, writes one self-contained skill per task with eval cases, checks that each skill actually helps, and hands you one report to review.

It adapts [framework-skill-authoring](https://github.com/grusin-db/framework-skill-authoring) to repos that people work in every day, that several teams share, and that change constantly.

**Golden rule.** Write for a consumer that does not read the source: everything a task needs is inside its skill. Every line is also **sourced** (a file, a page or a person), **placed once** in the cheapest layer that works, and **proven** by an eval to change the answer.

**Contents**

1. [Why](#1-why)
2. [Install](#2-install)
3. [Run it](#3-run-it)
4. [Review](#4-review)
5. [What you get](#5-what-you-get)
6. [The next run](#6-the-next-run)
7. [Settings](#7-settings)
8. [Adopting it across teams](#8-adopting-it-across-teams)
9. [How it differs from framework-skill-authoring](#9-how-it-differs-from-framework-skill-authoring)
10. [Running it at scale](#10-running-it-at-scale)
11. [Repository layout](#11-repository-layout)
12. [Standards it follows](#12-standards-it-follows)

---

## 1. Why

A coding agent working in your repo does not know what your team knows. Ask it to create a Silver table and it either writes a hand-made `MERGE`, or it reads notebook after notebook to work out the convention, spending tokens on every request and still guessing. A skill replaces that digging with the few lines that matter:

```
2. Merge with `merge_table_silver(df, target, keys=[business_key])`: it deduplicates on the key and
   adds `_loaded_at`; do not write a MERGE by hand.
3. Tag every PII column with `pii`; untagged PII columns are not masked downstream.
```

The meta-skill is the **author**: it has the repo, the docs and the history. The **consumer**, the agent that uses the skills later, should do each task from its skill alone, without reading the source. Finding the tasks people repeat, capturing what each one needs, keeping it out of the places it doesn't belong, and proving it helps is what the meta-skill does. [docs/how-it-works.md](docs/how-it-works.md) has the diagrams and explains every file.

| Step | What happens |
| --- | --- |
| **Start** | Creates a run folder and lists the skills, decisions and backlog that earlier runs left |
| **Analyze** | Lists what it read and how closely, then the tasks people repeat ("onboard a source table", not "PySpark"), the helpers, vocabularies and facts the agent would need, each with its source and the layer it belongs in: a skill, `AGENTS.md`, the always-on instructions, a catalog comment, or nowhere |
| **Identify the skills** | Settles each disagreement between teams, or between docs and code, from evidence, or leaves it open when it breaks a shared rule; decides which tasks need a skill: tasks people ask for on their own, that the agent gets wrong or reads the code for, with knowledge specific to your organisation |
| **Write** | One self-contained skill per task, with a description that makes the agent pick it at the right time, and eval cases; proposals for `AGENTS.md`, the always-on instructions and catalog comments |
| **Check** | Lint, a name check against the code, and evals with and without each skill. Skills that don't help are deleted. Everything lands in `report.md` |

## 2. Install

Copy the [`context-authoring/`](context-authoring/) folder to wherever your agent loads skills from. For Databricks Genie Code:

- `/Workspace/Users/<you>/.assistant/skills/context-authoring/` to try it yourself, or
- `/Workspace/.assistant/skills/context-authoring/` for everyone in the workspace.

For Claude Code, Codex, Copilot or Cursor, use that agent's skills folder, and set `workspace.consumer` and the paths in `standard.yaml` (section 7). The checks are Python scripts inside the folder that the agent runs with its code tool; they need `pyyaml`, and `databricks-sdk` for evals (both preinstalled on Databricks compute). On a laptop or in CI, `pip install .` gives the same commands as `skillkit`.

## 3. Run it

Start small: one team and one or two production folders. Ask the agent:

```text
Use the context-authoring skill.
Source repo: <path>. Folders: <folders>. Team: <team>, skill prefix: <prefix>.
Docs: <Confluence pages, a Markdown folder, or exported pages>.
```

It runs every step without stopping and writes to `workspace.output_folder` from the settings (on Databricks, `/Workspace/Users/<you>/genie-skills/`) unless you add "Output folder: <path>" (a Git folder if changes should go through pull requests). If the thread gets long, start a new one with "Continue the context-authoring run in `<run folder>`": the run folder holds everything.

## 4. Review

Open `report.md` in the run folder. Its first section says what to look at:

1. **Decisions it applied** (in `decisions.md`): reply in one line, "accept all except 3; 3 is Align to B", or edit the rows. A later run applies changes to the skills they affect.
2. **Open conflicts**: differences that break a shared rule, or have no evidence either way. Nothing that depends on them was written.
3. **Facts**: spot-check two or three helper names in `inventory.md` against the code.
4. **Proposals** in `proposals.md`, for the owners of `AGENTS.md`, the always-on instructions and the tables.
5. **The real agent**: copy one or two skills into your personal skills folder and paste the prompts from the report's checklist into a new session. If the agent reads repo files to finish a task, that skill is missing something.

Then copy approved skills to the workspace skills folder, or open a pull request if the output folder is a Git folder; `report.md` is the pull request description.

Prefer to check the facts before any skill is written? Set `review: before-write` (section 7).

## 5. What you get

```
<output folder>/
├── skills/<prefix>-<verb>-<object>/    the product: what the agent uses
│   ├── SKILL.md                        steps, a check per step, recovery, gotchas
│   ├── references/  assets/            detail opened on demand; templates
│   ├── skill.yaml                      owner, status, sources, the skills it uses (not deployed)
│   └── evals/evals.json                eval cases (not deployed)
├── evals/journeys.json                 eval cases for tasks that chain skills
└── authoring/runs/<date>-<scope>/      the run: inventory.md, decisions.md, proposals.md, report.md
```

The meta-skill never writes to the source repo, the installed skills, the always-on instructions or the data catalog: `AGENTS.md` lines, instruction changes and table comments are proposals that their owners apply. A study found that generated context files slightly lowered agent success and raised cost, while short human-written ones helped.

The checks it runs, and why they are scripts:

| Check | Why a script |
| --- | --- |
| Lint: format, size, sections, naming, links, forbidden values (catalog names, hosts, emails), skills that send the agent back to the code, skill dependencies, assets | Mechanical rules an agent misses when checking by eye |
| Names: every helper, file and table a skill mentions, looked up in the source repo | Invented names are the most common failure |
| Evals: each case with and without the skill, on a model from a different family, plus journeys; optionally SQL planned with `EXPLAIN` on a development warehouse | An agent grading its own skills is biased, and not every agent has sub-agents to grade independently |
| Skill map and agent checklist | Generated from the files, so they match what was written; the checklist is the check with the real agent that evals can't do |

Without Python, the meta-skill checks each skill by hand against the review checklist in the standard and says in the report that no evals ran.

## 6. The next run

| Situation | Ask |
| --- | --- |
| More folders, another team, or items from the backlog | The same prompt as section 3, with the new scope |
| A skill went stale (code or a doc changed) or gave a wrong answer | "Use context-authoring for `<skill>`. Trigger: `<commit range, doc page, or the wrong answer and its prompt>`." |
| You changed a decision, or edited skills or eval cases yourself | "Run the context-authoring check for `<run folder>`." |

Each run starts from what exists: current skills, reviewed decisions (not asked again), and the last backlog. For each task it finds, it adds a skill, adds a variant to the skill that covers the task when another team does it differently, or changes nothing. It updates an existing skill only when an eval case fails with it today; more facts are not a reason, because every line costs tokens and can conflict. Changes to another team's skills are proposed to that team. Eval results are cached, so only changed cases run again.

## 7. Settings

Nothing is required. The defaults live in [`context-authoring/assets/defaults/standard.yaml`](context-authoring/assets/defaults/standard.yaml). To change something, put a `standard.yaml` in the output folder with just the keys you change; it is merged over the defaults (a list replaces the default list, so copy the default entries you want to keep).

```yaml
prefixes: {dp: data-platform, fc: forecasting}   # teams and their skill prefixes
review: end                                       # or before-write: stop after identifying the skills, for a review
workspace:                                        # the platform; the defaults are for Databricks Genie Code
  consumer: Claude Code in a developer checkout   # the agent under test, as evals describe it
  output_folder: ~/agent-skills
  personal_skills_path: ~/.claude/skills
eval:
  model_endpoint: databricks-claude-sonnet-4-5
  judge_endpoint: databricks-gpt-oss-120b         # a different model family from the one under test
  runs: 3
  execution:                                      # optional: plan generated SQL with EXPLAIN
    warehouse_id: <development warehouse>
    variables: {catalog: mycatalog_dev}
catalog:
  installed_skills: ignore                        # use: also compare with skills already in the workspace
```

The full skill standard (layers, budgets, format, writing rules, review checklist, lint rules, glossary) is [context-authoring/references/standard.md](context-authoring/references/standard.md).

## 8. Adopting it across teams

Any team, the platform team included, can run the meta-skill for its own folders. Every skill meets the same bar: the standard (lint), real names (name check), proven value (evals with and without the skill), no duplicates (one skill per task, team variants inside it, overlap warnings), and nothing unnecessary (shared rules go to `AGENTS.md`; a skill with no effect is deleted).

The duplicate check only sees skills the run can see, so teams share one skill family:

- **One shared output folder**, for example a Git folder or a context repo (section 10), passed as "Output folder: <path>".
- **A prefix per team** in that folder's `standard.yaml`, so every skill has an owner and conflicts with platform conventions go to the platform team.
- **`catalog.installed_skills: use`** once the workspace has skills from elsewhere, so runs also compare with what is installed.

## 9. How it differs from framework-skill-authoring

[framework-skill-authoring](https://github.com/grusin-db/framework-skill-authoring) is an excellent method for packaged libraries, and this meta-skill keeps its core idea: the author has the source, the consumer works from the skills alone. Here the repo is one that several teams share and that changes constantly, so conflicts, ownership, evidence and freshness matter too.

| | framework-skill-authoring | context-authoring |
| --- | --- | --- |
| Consumer | Has only the installed package, so it cannot read the source | Works in the repo, but should not need to read it: every read costs tokens and guesses at conventions |
| Output | A router skill, one skill per capability area, an always-loaded "read the router first" instruction | One skill per task; `AGENTS.md`, instructions and table comments for the rest |
| Conflicts | Recorded in the skills | Decided from evidence and reviewed by people; contract breaks left open |
| Teams | One owner | Shared conventions, team variants inside a skill, a prefix per team |
| Validation | Checklists and source-blind sub-agents | Lint, name check, evals with and without each skill on a separate model, optional execution gate, a check with the real agent |
| After generation | Regenerate by hand | Per-skill sources, evidence-based updates, freshness checks |
| **Kept from it** | | The author/consumer framing and self-contained skills, signals with what to record, vocabularies as term, values, default, consequence and what goes together, values from config, consent at the risky step, degrees of freedom, defaults with an escape hatch, a leakage scan (forbidden patterns), symptom-to-fix tables, a real-agent check, journeys as a regression suite |
| **Left out on purpose** | | The router and its forced "read first" instruction, capability areas as the skill list, the 15-section anatomy and decision trees, "Before you start" and related-skills sections, "capture aggressively", and the ban on organisation names |

## 10. Running it at scale

Not needed to create skills. When teams rely on their skills and want changes reviewed, deployed and kept current, [`ops/`](ops/) adds a context repo (the output folder in Git, with owners per prefix), pipelines for GitHub Actions or Azure DevOps (PR evals, deploy with checksums, weekly maintenance, a freshness comment on source-repo PRs), and `skillkit-ops` for build, deploy and freshness. [ops/operating.md](ops/operating.md) describes the setup.

## 11. Repository layout

```
context-authoring/              the meta-skill: copy this folder
├── SKILL.md                    five steps
├── references/                 analyze, standard, evals, update
├── assets/templates/           run files, skill template, journeys, AGENTS.md templates
├── assets/defaults/            standard.yaml and decoys used when you supply none
└── scripts/skillkit/           init, check, and the single checks
docs/how-it-works.md            diagrams and every file explained
ops/                            optional: context repo, pipelines, deploy, freshness
tests/                          unit tests and a dry run of the installed skill
```

## 12. Standards it follows

| Source | Applied to |
| --- | --- |
| [Agent Skills specification](https://agentskills.io/specification) and [evaluation guide](https://agentskills.io/skill-creation/evaluating-skills) | Skill format, progressive disclosure, `evals/` layout, with/without-skill evals, trigger-rate testing |
| [AGENTS.md](https://agents.md/) | Repo and team-folder conventions |
| [Databricks Genie Code skills](https://docs.databricks.com/aws/en/genie-code/skills) and [instructions](https://docs.databricks.com/aws/en/genie-code/instructions) | Skill and instruction locations, one task per skill |
| [Anthropic: skills for enterprise](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/enterprise) | Review, separation of duties, coexistence testing, lifecycle |
| [Evaluating AGENTS.md (ETH Zurich)](https://arxiv.org/html/2602.11988v1) | Human-written, minimal, evaluated `AGENTS.md` |
| [framework-skill-authoring](https://github.com/grusin-db/framework-skill-authoring) | Analysis method, vocabularies, validation ideas |
