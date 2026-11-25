# Update: one skill, one trigger

Use this instead of steps 2–4 when the run is about one skill: its sources changed (a freshness comment on a source-repo PR, a changed doc page), it gave a wrong answer, an eval regressed, its review date passed, or a reviewer changed a decision it depends on. Also used from step 3 of a create run when a new scope shows that an existing skill fails.

1. Get the skill and the trigger: the changed paths with the commit range, the changed page ids, the wrong answer with its prompt, or the changed row in `decisions.md`.
2. Read the skill folder and its `skill.yaml` sources, then only what changed: `git diff <range> -- <paths>` for repo sources (docs in Git included), the current version of a changed page, or the new decision.
3. Decide what changed for the agent: a renamed helper, a new step, a removed template, a new rule. If nothing the skill says is affected, change only `last_reviewed`.
4. For a wrong answer, first add it to `evals/evals.json` as a case that fails today.
5. Edit the smallest set of lines that makes the skill true again. Keep everything else byte for byte: other lines may hold fixes people made after evals.
6. Adjust `sources` if files moved and set `last_reviewed` to today (in a context repo: `skillkit-ops reviewed <name>`, and `skillkit-ops confluence-check <name> --write` for new page versions). Check the journeys that include the skill: if what it produces or expects changed (a table name, a parameter), update their checks too.
7. Record it in `decisions.md` (Skill family: "updated: <failing case or trigger>"; "proposed to <owner>" for another team's skill), then go to step 5 of SKILL.md. All cases and journeys pass before the pull request, which states the trigger, what changed and the eval result.
