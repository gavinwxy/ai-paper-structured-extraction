# Extraction Runbook

This is the quick-start guide for future Codex sessions that need to run large
section-IR extraction batches in this repository.

## First Things First

- Work from repo root: `/Users/wxy/projects/knowledge-ontology-ai-focused`.
- In Codex shell commands, prefix commands with `rtk`.
- Check local state before running or editing:

```bash
rtk git status --short
```

- Batch outputs live under `production-outputs/`, which is gitignored.
- The extraction entry point is:

```bash
rtk .venv/bin/python -m production <input_dir> <output_dir> [flags]
```

`uv run` also works for tests and tools, but the committed README examples use
`.venv/bin/python`.

## Environment

The CLI loads `.env` automatically.

| Variable | Meaning | Default/fallback |
|---|---|---|
| `API_KEY` / `API-KEY` | OpenAI-compatible API key | required unless endpoint ignores auth |
| `BASE_URL` | OpenAI-compatible endpoint | `http://35.220.164.252:3888/v1` |

The transport disables model thinking/reasoning for Qwen and DeepSeek families
automatically.

## Input Expectations

Preferred input is a flat directory of one Markdown file per paper:

```text
input_dir/
  AAAI_2025_1234-example.md
  ACL_2025_5678-example.md
```

Markdown should contain `[§N]` block markers. Parsed JSON/JSONL inputs can be
converted by the runner:

```bash
rtk .venv/bin/python -m production <input_dir> <output_dir> --input-format auto
```

`--input-format auto` uses existing `*.md` if present, otherwise converts
JSON/JSONL into `<output_dir>/_prepared_markdown/`.

## Recommended Batch Command

For a normal large production run:

```bash
rtk .venv/bin/python -m production \
  <input_dir> \
  production-outputs/<run_name> \
  --model qwen3.5-35b-a3b \
  --paper-concurrency 10 \
  --llm-concurrency 30 \
  --max-tokens 32768 \
  --planning-max-tokens 24576 \
  --log-level INFO
```

For DeepSeek comparison / quality-priority reruns, use the same command with:

```bash
--model deepseek-v4-pro --base-url http://35.220.164.252:3888/v1
```

For a first smoke test, add:

```bash
--limit 5
```

Then inspect outputs before launching the full run.

## Defaults To Preserve

| Setting | Default | Keep it unless... |
|---|---:|---|
| `--input-format` | `md` | Use `auto/json/jsonl` only for parsed-block inputs. |
| `--temperature` | `0.0` | Do not change for production consistency. |
| `--max-tokens` | `32768` | Content-section output budget. |
| `--planning-max-tokens` | `24576` | Census, relations, metadata, citation, reference metadata budget. |
| `--paper-concurrency` | `10` | Lower if endpoint is saturated or rate-limiting. |
| `--llm-concurrency` | `30` | Lower for proxy stability; prior DeepSeek A/B used `8/16`. |
| score verification | on | Disable only with `--no-verify-scores` for speed/debug. |
| content-cache warming | on | Disable only with `--no-warm-content-cache` for latency tests. |
| reference/body cut | on | Do not pass `--keep-references-in-body` except for A/B/debug. |

Current input hygiene: census, relations, section fills, and citation Pass 1
receive `slice_body_content(paper_content)`, which removes bibliography and
everything after it. Metadata, reference metadata, assembly, marker resolution,
source tables, and references blob still use the full original paper.

## Output Layout

Each paper gets:

```text
<output_dir>/<paper_id>/
  01_census.json
  02_metadata.json
  03_citations.json
  03_reference_metadata.json
  03_references.json
  04_relations.json
  05_sections/{problem,method,evidence}.json
  06_extraction.json
  07_validation.json
  extraction.html
  status.json
```

Run-level files:

```text
<output_dir>/_manifest.json
<output_dir>/run.log
<output_dir>/run_summary.json
```

The canonical final per-paper artifact is `06_extraction.json`.

## Resuming And Reprocessing

Runs are resumable. Re-run the same command without `--force` to skip completed
papers.

Use `--force` only when intentionally regenerating every paper in the input set.

If a run is interrupted, resume with the same `<input_dir>` and `<output_dir>`.

## Monitoring

Watch the log:

```bash
rtk tail -f production-outputs/<run_name>/run.log
```

Check batch summary:

```bash
rtk python - <<'PY'
import json
from pathlib import Path
root = Path("production-outputs/<run_name>")
s = json.loads((root / "run_summary.json").read_text())
print(json.dumps({
    k: s.get(k)
    for k in ["processed", "completed", "failed", "skipped", "truncated_papers", "model", "base_url"]
}, indent=2, ensure_ascii=False))
PY
```

List failed/truncated papers:

```bash
rtk python - <<'PY'
import json
from pathlib import Path
root = Path("production-outputs/<run_name>")
for st in sorted(root.glob("*/status.json")):
    d = json.loads(st.read_text())
    usage = d.get("token_usage") or {}
    if d.get("status") != "completed" or (usage.get("totals") or {}).get("truncated"):
        print(st.parent.name, d.get("status"), d.get("error"), d.get("warnings"))
PY
```

## Post-Run Artifacts

Build corpus-level agent artifacts after a successful run:

```bash
rtk .venv/bin/python tools/build_agent_index.py production-outputs/<run_name> --flatten-sections
```

This creates or refreshes:

```text
_catalog.jsonl
_cards.jsonl
_result_rows.jsonl
_entity_index.json
```

Generate a cost/cache report:

```bash
rtk .venv/bin/python tools/token_cost_report.py production-outputs/<run_name> --cache
```

Render one paper manually if needed:

```bash
rtk .venv/bin/python tools/render_extraction.py production-outputs/<run_name>/<paper_id>/
```

Fresh production runs already attempt to write `extraction.html` for every
paper; rendering failures are non-fatal.

## Quality Checks

Minimum checks after a large run:

1. Confirm `run_summary.json` has `failed == 0` or inspect failures.
2. Confirm `truncated_papers` is small and identify stages.
3. Spot-check several `extraction.html` files.
4. Run `tools/token_cost_report.py --cache`.
5. Run `tools/build_agent_index.py --flatten-sections`.
6. Inspect `_catalog.jsonl`, `_cards.jsonl`, and `_result_rows.jsonl` row counts.

Quick validation counter:

```bash
rtk python - <<'PY'
import json
from pathlib import Path
root = Path("production-outputs/<run_name>")
bad = []
for p in sorted(root.glob("*/07_validation.json")):
    d = json.loads(p.read_text())
    if not d.get("valid"):
        bad.append((p.parent.name, len(d.get("issues") or [])))
print("invalid:", len(bad))
for row in bad[:30]:
    print(row)
PY
```

## Common Failure Modes

- `No papers found`: input directory has no `*.md`, or parsed-block inputs need
  `--input-format auto/json/jsonl`.
- `citation layer failed: LLM response truncated`: main extraction may still be
  valid, but `03_citations.json` and `03_references.json` may be empty. Current
  default trims post-reference appendices before citation Pass 1; remaining
  truncations are usually dense-body citation-output cases.
- Validation failures: inspect `<paper_id>/07_validation.json`, then
  `<paper_id>/06_extraction.json`.
- API/rate failures: lower `--paper-concurrency` and `--llm-concurrency`, then
  resume without `--force`.
- Bad or missing venue/year: current `enrich_metadata()` backfills from dirname
  patterns like `ACL_2025_...`, `NNN_NeurIPS_2024_...`, `NNN_2024_...`, and
  `2024_...`.

## Tests Before Code Changes

When changing extraction logic, run the related suite:

```bash
rtk uv run pytest \
  tests/test_production_worker.py \
  tests/test_section_pipeline.py \
  tests/test_body_slice.py \
  tests/test_schema_generator_descriptions.py \
  tests/test_agent_artifacts.py
```

Recent known-good result for this suite: `430 passed`.

If schemas change:

```bash
rtk .venv/bin/python tools/generate_section_schemas.py
rtk git diff schemas/
```

Only commit generated schema changes that match the intended contract.

## Naming Runs

Use descriptive output names with model/date:

```text
production-outputs/<corpus>_<model>_thinkoff_YYYYMMDD_HHMMSS
production-outputs/<corpus>_smoke5_<model>_YYYYMMDD_HHMMSS
```

`production-outputs/` is ignored by git. If outputs must be shared, archive the
run directory explicitly.

