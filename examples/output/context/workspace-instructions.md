# Workspace instructions

<!-- EXAMPLE: replace the environments and rules with your organisation's own. -->

Deployed to /Workspace/.assistant_workspace_instructions.md by the genie-context pipeline.
Do not edit in the workspace; change it in the genie-context repo.

## Environments

| Environment | Catalog | Use |
| --- | --- | --- |
| Development | lakehouse_dev | All development and testing |
| Staging | lakehouse_stg | Release verification only |
| Production | lakehouse_prd | Read-only for people; changes arrive through the release pipeline |

- Develop and test in development first. Never test first in staging or production.
- In code, never hardcode a catalog, workspace URL, pool, warehouse, secret or email. Use bundle variables and notebook widgets.

## Hard rules

- Destructive operations need the user's explicit consent and a non-destructive alternative offered first: DROP, TRUNCATE, INSERT OVERWRITE, replacing or recreating a table, deleting checkpoints, full reloads, reruns of production pipelines.
- Do not read or process rows from PII tables (names ending in `_pii`, or columns tagged `pii`). Reading schemas, tags and comments is fine.
- In development and staging, never expose rows where `_is_restricted = true`.
- GDPR delete and restrict requests are handled only by the platform's GDPR pipelines. Never write INSERT, UPDATE or DELETE against `gdpr_*` tables or customer rows to fulfil a GDPR request.
- PII columns are tagged with the tag name `pii`; the value is the PII type (`name`, `email`, `phone`, ...).
- Row filters and column masks use `is_account_group_member()`; new functions go in the `governance` schema.
- Grant access to groups, never to individual users.

## Where team context lives

- Each repo, and some team folders, have an `AGENTS.md` with their conventions. Follow the most specific one; a team folder's `AGENTS.md` says where it overrides the repo's.
- Workspace skills cover repeatable tasks (onboarding a source table, changing a table, preparing a PR, the daily load check). Prefer them over writing your own approach.
- Table meaning, grain and source system are in Unity Catalog comments; read them before using a table.
