# Update mode: one skill, changed sources

Also used from create mode (step 6) when a new scope shows that an existing skill fails: the trigger is then an eval case, written from the new folders or pages, that fails with the skill today. New facts alone are not a trigger. The change is recorded as "updated" in `skill-map.md`, and as "proposed" when another team owns the skill.

Triggered by a freshness comment on a source-repo PR, a changed doc page, a failed eval, a review date, or a reported wrong answer.

1. Get the skill name and the trigger: changed paths with the commit range, changed page ids, the failing eval case, or the wrong answer with the prompt that caused it.
2. Read the skill folder and its `skill.yaml` sources. Read only the changed sources: `git diff <range> -- <paths>` for repo sources (including docs kept in Git), and the current version of any changed doc page.
3. Decide what changed for the agent: a renamed helper, a new step, a removed template, a new rule. If nothing the skill says is affected, change nothing except `last_reviewed`.
4. Edit the smallest set of lines that makes the skill true again. Keep everything else byte for byte: other lines may hold fixes people made after evals.
5. A reported wrong answer: first add it to `evals/evals.json` as a case that fails today, then change the skill until it passes.
6. Adjust `sources` if files moved and set `last_reviewed` to today. Where the ops layer is set up, `skillkit-ops reviewed <name>` does that and `skillkit-ops confluence-check <name> --write` records new page versions.
7. Check the journeys in `evals/journeys.json` that include this skill: if what the skill produces or expects changed (a table name, a parameter, a step), update their checks too.
8. Run the skill's scripts: `lint` and `eval <name>`; the eval also runs the journeys that include the skill. All cases and journeys pass before the PR.
9. Open the PR with: trigger, what changed in the skill and its journeys, eval report.
