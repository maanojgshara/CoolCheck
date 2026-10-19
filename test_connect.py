from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
spark.sql("SELECT current_user() AS me, current_timezone() AS tz").show()