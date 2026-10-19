# Databricks notebook source
# Smoke test: Delta write, MLflow run, outbound HTTPS. Prints no keys or tokens.

# COMMAND ----------

import json
import urllib.error
import urllib.request

import mlflow

dbutils.widgets.text("catalog", "coolcheck")
dbutils.widgets.text("experiment_path", "")
catalog = dbutils.widgets.get("catalog")
experiment_path = dbutils.widgets.get("experiment_path")

spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")

# COMMAND ----------

# 1. Delta table: three rows in <catalog>.bronze._smoke (this table only).
table = f"{catalog}.bronze._smoke"
rows = [(1, "alpha"), (2, "beta"), (3, "gamma")]
spark.createDataFrame(rows, "id INT, label STRING").write.mode("overwrite").saveAsTable(table)
print("table rows:", spark.table(table).count())

# COMMAND ----------

# 2. MLflow: one run, one param, one metric, in an experiment under the user's own path.
mlflow.set_experiment(experiment_path)
with mlflow.start_run(run_name="smoke") as run:
    mlflow.log_param("purpose", "toolchain_smoke")
    mlflow.log_metric("rows_written", len(rows))
    print("mlflow run id:", run.info.run_id)

# COMMAND ----------

# 3. HTTPS GET to the data.gov.sg real-time air temperature endpoint (no key).
URL = "https://api-open.data.gov.sg/v2/real-time/api/air-temperature"
try:
    with urllib.request.urlopen(URL, timeout=30) as resp:
        status = resp.status
        body = json.load(resp)
except urllib.error.HTTPError as e:
    status, body = e.code, {}

readings = (body.get("data") or {}).get("readings") or []
records = len(readings[0]["data"]) if readings else 0
print("http status:", status)
print("records:", records)
