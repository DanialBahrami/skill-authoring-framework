# Skill authoring framework for Databricks Genie Code

**`context-authoring`** is a meta-skill: one folder you add to Genie Code (or any agent that supports [Agent Skills](https://agentskills.io/specification)). Ask it to create the skill family for a repo and it reads the code and docs, asks people where sources disagree, writes task-shaped skills with eval cases, and checks that each skill actually helps.

It adapts [framework-skill-authoring](https://github.com/grusin-db/framework-skill-authoring) to repos that people work in every day, that several teams share, and that change constantly. It works with any repo and any docs, however a team works.

**Contents**

1. [How it works](#1-how-it-works)
2. [Install](#2-install)
3. [First run](#3-first-run)
4. [Second run](#4-second-run)
5. [What you get](#5-what-you-get)
6. [The checks](#6-the-checks)
7. [Settings](#7-settings)
8. [How it differs from framework-skill-authoring](#8-how-it-differs-from-framework-skill-authoring)
9. [Running it at scale](#9-running-it-at-scale)
10. [Repository layout](#10-repository-layout)
11. [Standards it follows](#11-standards-it-follows)

---

## 1. How it works

The meta-skill works in four stages. [docs/how-it-works.md](docs/how-it-works.md) has the diagrams and explains every file it writes.

| Stage | Steps | What happens |
| --- | --- | --- |
| **Understand** | 1–3 | Lists the folders and how closely each was read, then finds the tasks people repeat ("onboard a source table", not "PySpark"), the helpers they use and the values that matter. Every fact cites the file or page it came from. |
| **Decide** | 4–5 | Puts each fact in one place: a skill, `AGENTS.md`, the workspace instructions, a table comment, or nowhere. Lists where teams, or docs and code, disagree, suggests a decision, and **stops** for people to review and decide. |
| **Write** | 6–7 | One skill per task, following writing rules: real names copied from the code, the default first, a guard at the risky step, a reason where the agent would otherwise go wrong. Each skill gets eval cases; tasks that chain skills get journeys. |
| **Check** | 8–9 | Lint, a name check against the repo, and evals with and without each skill. Skills that don't help are deleted. Writes a checklist for a real Genie Code chat and a summary for review. |

Quality comes from the steps, not the tooling: skills shaped by real tasks, facts copied from code with sources, people settling disagreements, and every skill proving it helps.

## 2. Install

Copy the [`context-authoring/`](context-authoring/) folder to:

- `/Workspace/Users/<you>/.assistant/skills/context-authoring/` to try it yourself, or
- `/Workspace/.assistant/skills/context-authoring/` for everyone in the workspace.

That's all. The checks are Python scripts inside the folder. Genie Code runs them with its code tool, and `databricks-sdk` and `pyyaml` are preinstalled on Databricks compute. In other agents (Claude Code, Codex, Copilot), put the folder wherever that agent loads skills from.

## 3. First run

Start small: one team and one or two production folders. Run the stages in separate chat threads, because long threads degrade the output. The meta-skill writes everything to the run folder, so each thread picks up where the last one stopped.

**Thread 1: understand and decide.**

```text
Use the context-authoring skill in create mode.
Source repo: <path>. Folders: <folders>. Team: <team>, skill prefix: <prefix>.
Docs: <Confluence pages, Markdown folder, or exported pages>.
Do steps 1 to 5 and stop.
```

Output goes to `/Workspace/Users/<you>/genie-skills/` unless you add "Output folder: <path>" (a Git folder if changes should go through pull requests). Later runs reuse that folder, so they start from what earlier runs left.

**You: review.** Go through `coverage.md`, `inventory.md` and `conflicts.md` with the [review checkpoint](context-authoring/references/review-checkpoint.md). Fix wrong facts and decide the conflicts; "accept all suggestions except 3 and 7" is enough. This is the most important human step: every skill is built from these three files.

**Thread 2: write and check.**

```text
Continue the context-authoring run in <run folder> from step 6.
Conflicts are decided in conflicts.md. Generate the skills, then validate:
lint, check-names against <repo path>, and eval --runs 3.
```

Before writing any skill, Genie shows the planned family in `skill-map.md`: a table and a diagram of which tasks become skills and which skill uses which. Reply "go", or say what to merge, split or drop; it's the cheapest moment to change the family's shape. After the evals, the map is regenerated from the skills actually written, with their verdicts.

**You: try and hand over.**

1. Copy one or two draft skills into your personal skills folder.
2. Paste the prompts from `genie-check.md` into a new Agent-mode chat and tick what you see.
3. Read `summary.md`.
4. Copy approved skills to the workspace skills folder, or open a pull request if the output folder is a Git folder.

## 4. Second run

| Situation | Mode | Ask |
| --- | --- | --- |
| A skill went stale: code or a doc changed, or someone got a wrong answer | Update mode, one skill | "Use context-authoring in update mode for `<skill>`. Trigger: `<commit range, doc page, or the wrong answer and its prompt>`." |
| More folders, another team, or items from `backlog.md` | Create mode, new scope | Same as thread 1, with the new scope |
| You edited skills or eval cases yourself | Just the checks | "Run eval for `<skills>` with --runs 3." |

The second run is cheaper than the first:

- **Update mode** reads only what changed and edits the fewest lines that make the skill true again, so human fixes elsewhere survive. A wrong answer is first added as a failing eval case, then fixed. The journeys that include the skill are checked too.
- **A new create run** starts from what exists: current skills, the last run's backlog, and conflict decisions already made, which it doesn't ask about again. If another team does a task differently, its way becomes a variant inside the existing skill, not a second skill.
- **Evals** cache their results, so only cases whose skill or question changed run again.

## 5. What you get

```
<output folder>/
├── skills/<prefix>-<verb>-<object>/     the product: what Genie Code uses
│   ├── SKILL.md                         steps, a default per decision, gotchas
│   ├── references/  assets/             detail opened on demand; templates per the assets rule
│   ├── skill.yaml                       owner, status, sources, the skills it uses (not deployed)
│   └── evals/evals.json                 eval cases (not deployed)
├── evals/journeys.json                  eval cases for tasks that chain skills
└── authoring/runs/<date>-<scope>/       working papers: review, resume, next run
    ├── coverage.md  inventory.md  classification.md  conflicts.md  skill-map.md
    ├── agents-md-candidates.md  workspace-instructions.diff.md  uc-comments.sql   proposals for their owners
    ├── genie-check.md  summary.md  backlog.md
```

The meta-skill never writes to the source repo, the workspace skills folder, the workspace instructions or Unity Catalog. `AGENTS.md` lines, instruction changes and table comments are proposals that their owners apply. A study found that generated context files slightly lowered agent success and raised cost, while short human-written ones helped.

## 6. The checks

The scripts in `context-authoring/scripts/` do what an agent can't do reliably on its own work:

| Check | What it does | Why it's a script |
| --- | --- | --- |
| `lint` | Format, size, naming, links, forbidden values (catalog names, hosts, emails), skill dependencies, asset syntax | Mechanical rules an agent misses when checking by eye |
| `check-names` | Looks up every helper, file and table a skill mentions in the source repo | Invented names are the most common failure |
| `eval` | Asks a different model each eval case with and without the skill, injecting the live workspace instructions; also runs journeys. Verdicts: ADDS VALUE, NO EFFECT, FAILING, INCONCLUSIVE | An agent grading its own skills is biased, and Genie Code has no sub-agents to grade independently |
| `eval --execute` | Plans the SQL in each answer with `EXPLAIN` and describes the tables on a development warehouse or Spark session; checks Python and YAML syntax | Catches invented tables and columns that look right in text |
| `genie-checklist` | Prompts to paste into a real Genie Code chat and what to look for | Evals are a simulation; this is the real check |
| `catalog` | Skill descriptions and the token budget they use | Every description is paid in every session |
| `catalog --map` | The skill map: every skill, what it uses and is used by, journeys and verdicts, as a table and a diagram | Generated from the files, so it always matches the skills actually written |

Genie runs them like this (the meta-skill's `SKILL.md` has the snippet):

```python
import sys; sys.path.insert(0, "/Workspace/Users/<you>/.assistant/skills/context-authoring/scripts")
from skillkit.cli import main
main(["--root", "/Workspace/Users/<you>/genie-skills", "eval", "dp-create-silver-table", "--runs", "3"])
```

Without them, the meta-skill still works: it follows a manual checklist and says in the summary that no evals ran. On a laptop or in CI, `pip install .` gives the same commands as `skillkit`.

## 7. Settings

Nothing is required. The defaults live in [`context-authoring/assets/defaults/standard.yaml`](context-authoring/assets/defaults/standard.yaml). To change something, put a `standard.yaml` in the output folder with just the keys you change; it's merged over the defaults.

```yaml
prefixes: {dp: data-platform, fc: forecasting}   # register teams and skill prefixes
forbidden_patterns:                               # your environment names, so skills never hardcode them
  - {name: environment catalog, regex: '\bmycatalog_(dev|stg|prd)\b'}
eval:
  model_endpoint: databricks-claude-sonnet-4-5
  judge_endpoint: databricks-gpt-oss-120b         # a different model family from the one under test
  execution:
    variables: {catalog: mycatalog_dev}           # fills ${catalog} in generated SQL for the execution gate
catalog:
  installed_skills: ignore                        # see below
```

**Skills already installed in the workspace.** By default (`ignore`), a run only considers skills in its output folder. Switch to `use` once you want new runs to check what's already installed: the catalog budget and the evals then count those skills, and the meta-skill must extend an existing skill (or plan its retirement with `supersedes`) instead of creating a duplicate.

## 8. How it differs from framework-skill-authoring

[framework-skill-authoring](https://github.com/grusin-db/framework-skill-authoring) is an excellent method for packaged libraries. This meta-skill keeps its analysis and validation ideas and changes what doesn't fit a shared repo.

| | framework-skill-authoring | context-authoring |
| --- | --- | --- |
| Consumer | Has only the installed package | Works inside the repo |
| Output | Router skill, one skill per capability area, "read the router first" instruction | One skill per task; `AGENTS.md`, instructions and table comments for the rest; no router |
| Conflicts | Recorded in the skills | Decided by people before any skill is written |
| Teams | One owner, one prefix | Shared conventions, team variants inside a skill, per-team prefixes |
| Size | Up to about 500 lines per skill | Up to 500 lines and 5,000 tokens per skill (the specification's limit); a catalog budget |
| Validation | Checklists and a source-blind simulation with sub-agents | Lint, name check, evals with and without each skill on a separate model, optional execution gate |
| After generation | Regenerate by hand | Per-skill sources and update mode |
| **Kept from it** | | Signal-by-signal analysis, inventory with sources, vocabularies as term/values/default/consequence, values from config not literals, consent at the risky step, degrees of freedom, leakage scan, symptom-to-fix table, a real-agent check, journeys as a regression suite |
| **Left out on purpose** | | Capability areas as a skill list (kept as a task checklist), the router and decision trees (a decision is a step with its condition), "Before you start", troubleshooting catalogues and related-skills sections (a skill keeps only a short `## Recovery` table for the failures its own steps can hit) |

## 9. Running it at scale

Not needed to create skills. When a team relies on its skills and wants changes reviewed, deployed and kept current, [`ops/`](ops/) adds the next layer:

- **a context repo:** the output folder in Git, with its own `standard.yaml`, owners per prefix and a reviewed copy of the workspace instructions;
- **pipelines** for GitHub Actions or Azure DevOps: PR validation with evals, deploy with checksums, weekly maintenance, and a freshness comment on source-repo PRs that touch a skill's sources;
- **`skillkit-ops`:** `build`, `deploy`, `freshness`, `changed`, `stale`, `reviewed`, `confluence-check`, `reviewers`.

[ops/operating.md](ops/operating.md) describes the setup.

## 10. Repository layout

```
context-authoring/              the meta-skill: copy this folder
├── SKILL.md                    the steps
├── references/                 analyze, classify, conflicts, review checkpoint, output contract, writing, validation, update mode
├── assets/templates/           run files, skill template, journeys, AGENTS.md templates
├── assets/defaults/            standard.yaml and decoys used when you supply none
└── scripts/skillkit/           the checks
docs/
├── how-it-works.md             diagrams and every file explained
└── STANDARD.md                 the skill standard in full
ops/                            optional: context repo, pipelines, deploy, freshness
tests/                          unit tests and a dry run of the installed skill
```

## 11. Standards it follows

| Source | Applied to |
| --- | --- |
| [Agent Skills specification](https://agentskills.io/specification) and [evaluation guide](https://agentskills.io/skill-creation/evaluating-skills) | Skill format, progressive disclosure, `evals/` layout, with/without-skill evals, trigger-rate testing |
| [AGENTS.md](https://agents.md/) | Repo and team-folder conventions |
| [Databricks Genie Code skills](https://docs.databricks.com/aws/en/genie-code/skills) and [instructions](https://docs.databricks.com/aws/en/genie-code/instructions) | Skill and instruction locations, one task per skill |
| [Anthropic: skills for enterprise](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/enterprise) | Review, separation of duties, coexistence testing, lifecycle |
| [Evaluating AGENTS.md (ETH Zurich)](https://arxiv.org/html/2602.11988v1) | Human-written, minimal, evaluated `AGENTS.md` |
| [framework-skill-authoring](https://github.com/grusin-db/framework-skill-authoring) | Analysis method, vocabularies, validation ideas |
