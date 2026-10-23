# Free Edition: pay-per-token models and one tool call (PT 11)

Checked 23 Oct 2026 (window A), CLI profile `freeedition`; the two requests ran at 16:52 SGT. Two read-only listings (`databricks serving-endpoints list`, `databricks ai-gateway list-model-services --parent schemas/system.ai`), then one request on each of the two request paths. Nothing else was done on Free Edition.

## Answer

- **Free Edition has 12 pay-per-token models: 9 chat and 3 embedding models.** Each exists both as a `databricks-*` serving endpoint (all 12 `READY`) and as a Unity Gateway model service in `system.ai`.
- **Tool calling works.** Llama 3.3 70B Instruct, the model that passed in the trial on 21 Oct (`tool_calling_model_test.md`), returned one well-formed `save_advisory` call (`finish_reason` `tool_calls`) to a single request with a tools list. It did so on both request paths.
- **Both request paths work on Free Edition today**: the serving-endpoint path the trial test used, and the Unity Gateway path. Databricks' guidance favours the gateway path (`system.ai.<model>`) for new code, and the serving-endpoint path for pay-per-token models can be switched off per workspace (the "Enforce Unity Gateway" setting). My recommendation: the agent uses the gateway path with the model-service name exactly as listed below.

## The 12 models

| Serving endpoint | Unity Gateway model service | Gateway APIs |
|---|---|---|
| `databricks-deepseek-v4-flash-0731` | `system.ai.deepseek-v4-flash-0731` | chat completions, responses |
| `databricks-gemma-3-12b` | `system.ai.gemma-3-12b` | chat completions, responses |
| `databricks-gpt-oss-120b` | `system.ai.gpt-oss-120b` | chat completions, responses |
| `databricks-gpt-oss-20b` | `system.ai.gpt-oss-20b` | chat completions, responses |
| `databricks-llama-4-maverick` | `system.ai.llama-4-maverick` | chat completions, responses |
| `databricks-meta-llama-3-1-8b-instruct` | `system.ai.meta-llama-3-1-8b-instruct` | chat completions |
| `databricks-meta-llama-3-3-70b-instruct` | `system.ai.meta-llama-3-3-70b-instruct` | chat completions |
| `databricks-qwen3-next-80b-a3b-instruct` | `system.ai.qwen3-next-80b-a3b-instruct` | chat completions, responses |
| `databricks-qwen35-122b-a10b` | `system.ai.qwen35-122b-a10b` | chat completions, responses |
| `databricks-bge-large-en` | `system.ai.bge-large-en` | embeddings |
| `databricks-gte-large-en` | `system.ai.gte-large-en` | embeddings |
| `databricks-qwen3-embedding-0-6b` | `system.ai.qwen3-embedding-0-6b` | embeddings |

The names differ between the two lists, and from the model name inside the endpoint: the endpoint `databricks-meta-llama-3-3-70b-instruct` serves the foundation model `system.ai.llama_v3_3_70b_instruct`, while the gateway's service is `system.ai.meta-llama-3-3-70b-instruct`. All 12 are open-weight models hosted by Databricks; none comes from an outside provider.

## The two requests

Both send the trial's body unchanged: one user message asking for a one-sentence heat advisory for seniors in Malay and one in Tamil, saved by calling `save_advisory` once; `tools` holds that one function; `tool_choice` `auto`; `max_tokens` 600. The script gained `--profile`, `--api`, `--model`, `--out` and `--title`; its defaults are the trial's request.

```
.venv\Scripts\python scripts/checks/tool_calling_model_test.py --profile freeedition --api gateway --model system.ai.meta-llama-3-3-70b-instruct
.venv\Scripts\python scripts/checks/tool_calling_model_test.py --profile freeedition --api serving-endpoints --model databricks-meta-llama-3-3-70b-instruct
```

On Windows, set `PYTHONIOENCODING=utf-8` so the Tamil text prints to the console. The report file is written before the print either way.

Output of the gateway request (16:52 SGT), copied unchanged:

- Model service: `system.ai.meta-llama-3-3-70b-instruct` through Unity Gateway `/ai-gateway/mlflow/v1/chat/completions` (pay-per-token, workspace profile `freeedition`)
- finish_reason: `tool_calls`; tool calls returned: 1
- Tool calls well-formed (known name, valid JSON, exact argument keys): yes
- `save_advisory` well-formed=True
  - Malay: Warga emas dinasihatkan untuk mengambil langkah-langkah berjaga-jaga untuk mengelakkan kepanasan yang terlalu tinggi esok.
  - Tamil: முதியோர்கள் அதிக வெப்பத்தைத் தவிர்ப்பதற்கான பாதுகாப்பு நடவடிக்கைகளை எடுக்க வேண்டும்.

Output of the serving-endpoint request (16:52 SGT), copied unchanged:

- Endpoint: `databricks-meta-llama-3-3-70b-instruct` (pay-per-token, workspace profile `freeedition`)
- finish_reason: `tool_calls`; tool calls returned: 1
- Tool calls well-formed (known name, valid JSON, exact argument keys): yes
- `save_advisory` well-formed=True
  - Malay: Warga emas dinasihatkan untuk mengambil langkah berjaga-jaga untuk mengelakkan tekanan haba yang tinggi esok.
  - Tamil: மூத்தோர்கள் அடுத்த நாள் அதிக வெப்ப அழுத்தத்தைத் தவிர்க்க பாதுகாப்பு நடவடிக்கைகளை எடுக்குமாறு அறிவுறுத்தப்படுகிறார்கள்.

## Not tested

- Tool calling on the other 8 chat models.
- The quality of the Malay and Tamil text; that is Sunday's back-translation check. The endpoint's own description of Llama 3.3 70B says: "It is not intended for use in languages other than English."
- Free Edition's rate limits and daily quota for these calls; the two requests ran without error.
