CREATE TABLE IF NOT EXISTS ${table} (
  approval_id STRING NOT NULL COMMENT 'UUID made with the draft; the Approve MERGE matches on it, so a second press writes no second row.',
  approved_at TIMESTAMP NOT NULL COMMENT 'When the person pressed Approve (the warehouse clock, an instant; shown in Asia/Singapore).',
  approved_sgt_date DATE NOT NULL COMMENT 'The date of approved_at in Asia/Singapore.',
  target_date DATE NOT NULL COMMENT 'The briefing date the plan is for (gold.area_heat_risk.target_date).',
  region STRING COMMENT 'Region the plan was drafted for; NULL for the whole island.',
  call_capacity INT NOT NULL COMMENT 'Calls passed to get_priority_areas.',
  capacity_basis STRING NOT NULL COMMENT 'Where call_capacity came from, e.g. form: 800 calls (placeholder), or request: 8 volunteers x 25 calls per volunteer (assumption) = 200.',
  calls_allocated INT NOT NULL COMMENT 'Calls allocated in the approved plan (the sum over areas, as get_priority_areas returned it).',
  source STRING NOT NULL COMMENT 'agent: the summary was written by the model and passed the checks; template: the per-tier template (decision 4).',
  fallback_reason STRING COMMENT 'Why the template was used; NULL when source is agent.',
  request_text STRING COMMENT 'The request as typed, with NRIC-like strings and 8-digit phone-like numbers masked before storing.',
  draft_text STRING NOT NULL COMMENT 'The draft exactly as the approver saw it.',
  plan_json STRING NOT NULL COMMENT 'The areas given calls, with their blocks and calls, from get_priority_areas (JSON).',
  tool_calls_json STRING NOT NULL COMMENT 'Every tool call behind the draft: name, arguments, row count (JSON); results are in the trace.',
  llm_model STRING COMMENT 'The model service that wrote the summary; NULL for the template.',
  mlflow_trace_id STRING COMMENT 'The MLflow trace of the draft.',
  forecast_run_id STRING COMMENT 'The nightly scoring run the plan was built on (gold.area_heat_risk.run_id).',
  forecast_scored_at TIMESTAMP COMMENT 'When that forecast was scored (gold.area_heat_risk.scored_at).',
  approved_by STRING NOT NULL COMMENT 'The approver as the Databricks user ID the Apps proxy passes (X-Forwarded-User); never a name or e-mail.',
  app_commit STRING COMMENT 'Git commit of the deployed App.',
  status STRING NOT NULL COMMENT 'Always approved_not_sent: CoolCheck sends nothing.'
)
COMMENT 'Plans a person approved in the CoolCheck App, one row per Approve. CoolCheck sends nothing: the Active Ageing Centre acts on the plan with its own client list. No personal data about residents; the approver is a Databricks user ID.'
