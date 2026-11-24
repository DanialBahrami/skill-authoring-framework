# AGENTS.md — data-platform

<!-- Example root AGENTS.md for a fictional metadata-driven medallion platform shared by several teams.
     Replace every value with your own. Keep only what an agent cannot infer from the code:
     vocabulary, conventions, the contract, non-obvious commands. No overviews of things the code shows.
     Guardrails (destructive operations, PII, GDPR) live in the workspace instructions, not here. -->

## What this repo is

A metadata-driven medallion platform. A config-driven Auto Loader notebook loads Bronze; one notebook per table merges Bronze into Silver with shared helpers; Gold notebooks build the dimensional model; a Global step consolidates every region into `global_*` tables keyed by `region_key`. Table DDL lives in setup notebooks, changes to existing tables ship as deployment scripts, jobs ship through the `data_platform` bundle.

```
raw files -> Bronze/autoloader (row in <region>_bronze.autoloader_inputs)
          -> <region>_bronze.<source>_<table>
          -> Silver/<source>_<table> (merge_template -> merge_table_silver)
          -> <region>_silver.<source>_<table>[_pii]
          -> Global/update_global_table -> global_silver.<table> (+ v_<table>)
          -> Gold/<DimX|FactY> (gold_template -> merge_table + DQ tests)
```

Ownership: Bronze and Silver = Data Platform. Gold = domain teams (Analytics, Forecasting).

## Layout

```
data-platform/
├── Databricks/
│   ├── databricks.yml                 # bundle 'data_platform': variables + targets
│   ├── bundle_resources/jobs/<area>/  # job definitions
│   ├── Bronze/autoloader              # ingestion
│   ├── Silver/<source>_<table>        # one notebook per silver table
│   ├── Gold/<DimX>, <FactY>
│   ├── Global/                        # cross-region consolidation
│   ├── Setup/{Bronze,Silver,Global}/  # DDL for new tables
│   ├── Common/silver_lib/merge_template
│   ├── Common/gold_lib/gold_template, data_quality_tests
│   └── Config/<region>/autoloader_<region>_config.json
├── Deployment_Scripts/Template/       # templates; scripts in the root run in the next release
└── pull_request_template.md
```

## Vocabulary

| Concept | Values |
| --- | --- |
| Region (schema prefix) | `nordics`, `baltics`, `iberia`, `global` |
| Layer schema | `<region>_bronze`, `_silver`, `_gold`; also `governance` |
| Bronze technical columns | `_file_name, _created_date, _updated_date, _is_active, _row_hash` (+ `_is_restricted` if PII) |
| Silver technical columns | `_load_date, _is_deleted, _is_active` (+ `_is_restricted` if PII) |
| Merge key | column `COMMENT 'UQ'` |
| Silver read filter | `_is_deleted = false AND _is_active = true` |
| Global key | `region_key STRING COMMENT 'UQ'`, value = region |
| load_type | `incremental` or `full` |
| DQ test type | `Error` (stops the merge) or `Warning` |
| Bundle targets | `dev_build` (personal, triggers paused), `development`, `staging`, `production` |

Resolve catalog, storage and region from notebook widgets and bundle variables, never literals.

## Contract (applies in every folder, every team)

- Every table has its layer's technical columns and `UQ` merge keys; shared helpers and monitoring depend on them.
- New tables: DDL in the setup notebooks. Existing tables: a deployment script from `Deployment_Scripts/Template`, plus the setup notebook updated in the same PR, so fresh and upgraded environments end up identical.
- Global tables stay `PARTITIONED BY (region_key)`; the Global overwrite relies on it. New standalone tables use `CLUSTER BY`.
- PII columns: tag `pii` with the PII type as value; PII goes in `_pii` tables.
- Jobs ship through the `data_platform` bundle, with per-environment values from bundle variables.
- Develop with `dev_build`; merge to the day's `release/YYYY-MM-DD` branch. Hotfixes use `hotfix/*`.

## Team folders

| Folder | Team | Conventions |
| --- | --- | --- |
| `Databricks/Gold/forecasting/` | Forecasting | `Databricks/Gold/forecasting/AGENTS.md` |
| `Databricks/Gold/analytics/` | Analytics | `Databricks/Gold/analytics/AGENTS.md` |

## Tasks with skills

| Task | Skill | Then |
| --- | --- | --- |
| Onboard a new source end to end | `dp-onboard-source` | |
| Create a Silver table and its global twin | `dp-create-silver-table` | `dp-prepare-pr` |
| Change an existing table | `dp-change-existing-table` | `dp-prepare-pr` |
| Prepare a PR or hotfix | `dp-prepare-pr` | |
| Daily load check, failed run, rerun | `dp-check-daily-load` | |
