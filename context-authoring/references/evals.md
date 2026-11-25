# Evals: proving a skill helps

## Contents

- What an eval does
- Writing eval cases
- Journeys
- Verdicts
- Execution gate
- The real agent check
- Symptoms and fixes

## What an eval does

Build the cases before or with the skill, not after: first see where the agent fails without a skill, then write only what makes those cases pass. `check` (or `eval <names>`) runs every case against a model serving endpoint that stands in for the consumer agent (`workspace.consumer` in the settings), judged by a model from a different family:

- **Routing**, every case: the model sees the catalog (every skill in the output folder that is not deprecated, drafts included; installed skills when `catalog.installed_skills: use`; decoys for skills the agent already has) and picks a skill. A trigger case passes when it picks this skill in at least half the runs; a near miss passes when it does not.
- **Answer with the skill**, trigger cases: the model gets the always-on instructions, the `AGENTS.md` files the case lists, the skills in `uses`, and this skill. It passes when every `must_include` matches, no `must_not_include` matches, the trajectory holds and the judge passes every assertion, in a majority of runs.
- **Answer without the skill**: the same minus this skill. This is the baseline.

The model cannot run anything: it describes what it would do, in order, including what it would read first. It sees no source code in either arm, on purpose: the with-skill arm is the consumer doing the task from the skill alone, so a skill that points at a file instead of saying what is in it fails. ADDS VALUE means the skill supplies what the agent would otherwise guess or have to read. Results are cached per case and re-run only when the case, the skill or the context changes.

## Writing eval cases

`evals/evals.json`, the Agent Skills layout with a few additions:

```json
{"skill_name": "<name>", "evals": [
  {"id": "silver-01", "type": "trigger",
   "prompt": "Create the silver table and notebook for nordics_bronze.crm_contract_account",
   "agents": ["data-platform/AGENTS.md"],
   "must_include": ["merge_table_silver"],
   "must_not_include": ["(?m)^\\s*MERGE\\s+INTO"],
   "assertions": ["Asks before running a full reload"],
   "trajectory": {"order": ["bundle validate", "bundle deploy"],
                  "avoid": ["Reads repository files to look up the naming convention"]}},
  {"id": "silver-nm-01", "type": "near_miss", "prompt": "Add a column to an existing silver table",
   "expect_skill": "dp-add-silver-column"}
]}
```

- At least two trigger cases and one near miss to start. Before a skill is `active`, grow it towards about 20 routing prompts: 8–10 that should load the skill, varied in wording, detail and explicitness (the most useful are the ones where the connection is not obvious), and 8–10 near misses that share its words but need something else. Weak negatives ("what is the weather") test nothing.
- **Prompts** as a developer would type them, in other words than the description, with real context (table names, paths). At least one needs the skill without naming its domain.
- **`must_include`** (regexes): names that must appear (helpers, templates, conventions). **`must_not_include`**: hardcoded environment values and the wrong approach (a hand-written MERGE where a template exists). Target the place where a value does harm (a literal catalog as the target of DDL), not every mention; try a new pattern against a few lines of real repo code first.
- **`assertions`**: observable behaviour the judge checks ("asks for consent", "verifies uniqueness"). Drop assertions that pass with and without the skill.
- **`trajectory`** on at least one trigger case: `order` lists regexes that must appear in this order (validate before deploy, a read-only check before a write); `avoid` lists actions the judge must not find in the plan. Use `avoid` for the costly or risky detours this task invites, starting with reading the source the skill should have replaced ("Reads repository files to look up the naming convention").
- **Achievable without running anything**: expect what the agent would do ("gives the query that lists the downstream tables"), never results ("lists the downstream tables").
- **`agents`**: the `AGENTS.md` files the agent would have loaded for the prompt.
- **`expect_skill`** on a near miss when the right skill is known.
- **`exec_new_tables` / `exec_new_columns`** (optional): tables and columns the task creates, so the execution gate does not count them as invented.
- Answers cut off at the limit: set `eval: max_tokens` in `skill.yaml`, never shorten the case.

## Journeys

A skill that uses other skills gets a journey in `<output folder>/evals/journeys.json` (template: `assets/templates/journeys.json`): `id`, `prompt` (a task that needs the chain), `skills` (where it starts, then the skills it hands over to), and the same checks as a case. Every skill after the first must be reachable from it through `uses`. Check what only passes when the hand-over worked: a name from a later skill, the table one step creates being the one the next uses. Each journey also runs without any skill; one that passes then too does not test the skills.

## Verdicts

| Verdict | Meaning | Action |
| --- | --- | --- |
| ADDS VALUE | Every case passes, and at least one passes only with the skill | Keep |
| NO EFFECT | The model gets it right without the skill | Delete the skill, or move its one useful rule to the `AGENTS.md` candidates |
| FAILING | A routing or answer case fails | Read the answer (`eval <name> --inspect <case-id>`); fix the skill, its description, or the case if the case was wrong |
| INCONCLUSIVE | Answers were cut off at the token limit | Raise `eval: max_tokens` in `skill.yaml` and run again |

Before fixing a failing case, check that it is achievable: a case that expects real results fails for every skill. Never loosen a case only to make it pass. Stop after three rounds and report what still fails.

## Execution gate

Rubrics see whether code looks right, not whether it runs. When `eval.execution.warehouse_id` is set in `standard.yaml` (or `eval --execute` in a notebook), the SQL in each answer is planned with `EXPLAIN`, fully qualified tables in the development catalog get `DESCRIBE TABLE`, Python blocks are compiled and YAML blocks parsed. An invented table or column, or a syntax error, fails the case. Only `EXPLAIN` and `DESCRIBE TABLE` are sent; both read metadata, never rows. Use an identity that can only read the development catalog, and set the variables the skills use under `eval.execution.variables`.

## The real agent check

Evals call a model, not the agent itself. Before a skill becomes `active`, someone tries it with the real agent, using the prompts `check` writes into `report.md`:

1. Install the draft as a personal skill (in `workspace.personal_skills_path`, without `skill.yaml` and `evals/`).
2. In a new session, open a file in the folder the task belongs to and paste two trigger prompts.
3. Check: the skill was used; real helpers and conventions; nothing hardcoded; consent before risky steps; the trajectory holds for what the agent actually read and ran.
4. If it read repo files to finish the task, the skill is missing what it went looking for: add that to the skill. Reading the source is the cost the skill exists to remove.
5. If the task can start outside the repo, ask once with no repo file open: `AGENTS.md` does not load then.
6. For a skill that uses others, give each journey's prompt: whether the agent loads a skill named in another skill's steps is only visible here.

## Symptoms and fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Invents a helper, field or value | It was not written in | Write in the signature or vocabulary (term, values, default, consequence) |
| Execution gate: column or table not found | The skill names something that does not exist, or the model invented it | `check-names`; write down the real column list where the task needs it |
| Catalog or table names that exist nowhere in the code | Example always-on instructions or `AGENTS.md` were injected | Use the real instructions; check the case's `agents` paths |
| Journey fails, each skill passes alone | The skills do not hand over | Use the same names in both; say in the using skill what it passes |
| Skill not used for a prompt it should handle | The description lacks the situation or the words people type | Add the situation to the description (not the exact words of that one prompt, which overfits); keep the prompt as a trigger case |
| Skill used for the wrong task | Two descriptions overlap | Sharpen both; add a near miss naming the right skill |
| Hardcodes a catalog or path | The step did not say where the value comes from | Name the bundle variable or widget in the step |
| Does something destructive without asking | No guard at that step | Add the consent step where the risk occurs, non-destructive option first |
| Reads the repo or a wiki to find a convention | The skill points instead of baking it in, or leaves it out | Write the convention in; add the detour to `trajectory.avoid` |
| Right answer, wrong order | Steps out of order or missing | Reorder; read-only checks before writes |
| Improvises after an error | No `Check:` on the step, or no Recovery row | Add both, with a stop where improvising would harm |
| Two teams' ways mixed in one answer | Variant condition unclear | State the condition in step 1; each way in its own reference file |
| NO EFFECT on every case | The model already knows this | Delete the skill |
