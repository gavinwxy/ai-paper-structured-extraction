# Findings

## Repository Notes
- Python project with production entry point `python -m production`, implemented by `production/__main__.py` -> `production/cli.py`.
- Core runtime defaults are in `production/cli.py`, mirrored by `production/config.py`.
- `section_pipeline.py` also exposes synchronous API defaults; some historical defaults differ from the production CLI.

## Runtime Setting Sources
- CLI args in `production/cli.py`: positional `input_dir`, `output_dir`; options for input format, model/base URL, concurrency, temperature, token budgets, retries, logging, limit/resume behavior, score verification, reference body slicing, and content-cache warming.
- Environment variables in production CLI: `API_KEY` or `API-KEY`, `BASE_URL`. `MODEL` appears in README and smoke test defaults but is not read by production CLI.
- `Config` dataclass in `production/config.py` holds the effective runtime settings after CLI/env resolution.
- Async LLM client receives `base_url`, `api_key`, `llm_concurrency`, and `max_retries`.
- JSON parse/shape retries use `section_pipeline.MAX_SECTION_RETRIES = 2`, separate from CLI `--max-retries` transport/API retries.
- Derived model behavior: Qwen/DeepSeek use `json_object` mode and thinking-off `extra_body`; other models use strict `json_schema`. Official DeepSeek models skip explicit prompt-cache kwargs.

## Open Questions
- Done. Included production, sync API, auxiliary tools, smoke tests, and fixed-path experiment scripts.
- Note: `docs/` is gitignored, so the generated inventory is local unless moved or force-added.
