# Findings & Decisions

## Requirements
- Input corpus: `/Users/wxy/projects/paper-retrieval/downloads/large_models_extra_10000_full_content_markdown`
- Target size: 10000 Markdown papers.
- Model: `deepseek-v4-pro`.
- Thinking mode: disabled.
- Desired workflow: first extract 200 papers while finding the largest reliable concurrency; inspect outputs; if no issues, continue the remaining corpus.

## Research Findings
- The input directory contains 10000 top-level Markdown files.
- `production` discovers sorted `*.md` files. `--limit 200` selects the first 200 sorted papers.
- Rerunning the same output directory without `--force` skips completed papers, so a trial run can be continued into the full run.
- `production/llm.py` automatically disables thinking for DeepSeek models with `extra_body={"thinking": {"type": "disabled"}}`.
- CLI defaults: `--temperature 0.0`, `--max-tokens 32768`, `--planning-max-tokens 24576`, `--paper-concurrency 10`, `--llm-concurrency 30`.
- The current default strips references-and-after for body-fed stages; do not pass `--keep-references-in-body` for production extraction.
- Per-paper first phase runs census, metadata, and citation layer in parallel, so up to roughly three LLM calls per active paper can be in flight. With cache warming on, content sections run one warmer call, then two concurrent calls.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Test `paper_concurrency` and `llm_concurrency` as paired settings | The worker can create up to about 3 LLM calls per active paper, so `llm_concurrency = 3 * paper_concurrency` keeps the paper workers from stalling without opening unbounded calls. |
| Use an increasing-limit ladder over one output directory | Avoids paying for duplicate extraction while still testing progressively higher concurrency across unique papers. |
| Start with 20 papers at default concurrency before increasing | Confirms endpoint, credentials, and schema behavior before stressing the proxy. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| The planning skill's documented `~/.codex/.../session-catchup.py` path did not exist | Used the project-local skill path `.codex/skills/planning-with-files/scripts/session-catchup.py`. |
| `rtk find ... | wc -l` returned a misleading count | Used `rtk find` summary output to confirm `10000F`. |
| DeepSeek `json_object` can route a baseline into a legal evidence array with an id prefix that later canonicalizes to a disallowed type, e.g. `experiment_setups[]` item `id: cmp:gpt4o_fewshot`, `type: ExperimentSetup` becoming a `Component` in evidence | Added deterministic assembly guards: only flatten typed arrays owned by the current section, and after prefix reconciliation drop units whose final type is not allowed for that section while logging an uncertain assignment. |
| Legacy-marker validation was too broad: it treated any string equal to a retired type name (`Relation`, `Setting`, `Category`, `Proposition`, etc.) as a forbidden legacy marker, even when the string was a legitimate score variant or unit name | Narrowed `_contains_legacy_marker` to `paradigm_tags` plus discriminator fields (`type`, `unit_type`, `node_type`) so content text is not rejected. |

## Resources
- CLI entrypoint: `/Users/wxy/projects/knowledge-ontology-ai-focused/production/cli.py`
- Runner resumability: `/Users/wxy/projects/knowledge-ontology-ai-focused/production/runner.py`
- LLM thinking-off behavior: `/Users/wxy/projects/knowledge-ontology-ai-focused/production/llm.py`
- Operational guide: `/Users/wxy/projects/knowledge-ontology-ai-focused/EXTRACTION_RUNBOOK.md`
