# Databricks notebook source
# MAGIC %md
# MAGIC # Run skillkit in the workspace
# MAGIC For authors who work in Genie Code instead of a local terminal. Clone `genie-context` and the
# MAGIC source repos (e.g. data-platform) as Git folders side by side under `/Workspace/Users/<you>/`, then run
# MAGIC this notebook on serverless. Set the widgets and run all. Evals call model serving endpoints as you.

# COMMAND ----------

# MAGIC %pip install -q pyyaml requests databricks-sdk

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import os
import sys

me = spark.sql("SELECT current_user()").first()[0]
default_root = f"/Workspace/Users/{me}/genie-context"

dbutils.widgets.text("root", default_root, "genie-context folder")
dbutils.widgets.text("repos_root", f"/Workspace/Users/{me}", "Folder holding source repo checkouts")
dbutils.widgets.dropdown("command", "lint", ["lint", "catalog", "eval", "check-names", "genie-checklist", "new", "freshness", "stale", "reviewed", "build"], "Command")
dbutils.widgets.text("skills", "", "Skill names (space separated)")
dbutils.widgets.dropdown("execute", "no", ["no", "yes"], "Execution gate (EXPLAIN / DESCRIBE TABLE)")
dbutils.widgets.text("warehouse_id", "", "Dev SQL warehouse for the gate (empty: this notebook's Spark session)")
dbutils.widgets.text("extra", "", "Extra arguments, e.g. --case-filter silver-01, or --repo <path> for check-names")

root = dbutils.widgets.get("root")
sys.path.insert(0, root)  # import skillkit straight from the Git folder, no install needed
from skillkit.cli import main  # noqa: E402

# COMMAND ----------

command = dbutils.widgets.get("command")
skills = dbutils.widgets.get("skills").split()
extra = dbutils.widgets.get("extra").split()
args = ["--root", root, command, *skills]
installed = "/Workspace/.assistant/skills"  # what workspace users already have
if command == "eval":
    args += ["--repos-root", dbutils.widgets.get("repos_root"), "--out", f"{root}/authoring/last-eval-report.md"]
if command == "eval" and dbutils.widgets.get("execute") == "yes":
    # Only EXPLAIN and DESCRIBE TABLE are sent, as you; they read metadata, never rows
    args += ["--execute"]
    if dbutils.widgets.get("warehouse_id"):
        args += ["--warehouse-id", dbutils.widgets.get("warehouse_id")]
if command in ("eval", "catalog") and os.path.isdir(installed):
    args += ["--installed", installed]
args += extra
print("skillkit", " ".join(args[2:]))
exit_code = main(args)
print(f"\nexit code {exit_code}")
