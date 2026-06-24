# Large Models Extraction Monitor

## Goal
Extract all markdown papers from `/Users/wxy/projects/paper-retrieval/downloads/large_models_llm_selected_2000_full_content_markdown` with `deepseek-v4-pro`, increased concurrency, and 10-minute status checks.

## Run
- Output: `/Users/wxy/projects/knowledge-ontology-ai-focused/production-outputs/large_models_llm_selected_2000_deepseek_v4pro_thinkoff_20260622_205455`
- Command: `.venv/bin/python -m production ... --model deepseek-v4-pro --paper-concurrency 8 --llm-concurrency 16 --max-retries 5 --max-tokens 65536`
- Session id: `31556`

## Phases
- [x] Start extraction with increased concurrency.
- [x] Verify process remains alive after context recovery.
- [x] Monitor every ~10 minutes until the run exits.
- [x] Collect final status, failures, truncations, and summary.

## Errors Encountered
| Time | Issue | Resolution |
| --- | --- | --- |
| 2026-06-23 02:40 | 2 validation failures observed so far | Continue monitoring; inspect details if failures increase or at final summary. |
| 2026-06-23 03:28 | Process exited with code 1 because 2 papers failed validation | Batch completed overall; final summary collected. |
