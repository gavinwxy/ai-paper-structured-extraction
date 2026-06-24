# Task Plan: DeepSeek Large Models Extra 10000 Extraction

## Goal
Extract the 10000-paper corpus with `deepseek-v4-pro` thinking disabled, first validating a 200-paper concurrency trial and then continuing the same output directory to the full corpus if quality is acceptable.

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Confirm user intent: 200-paper trial first, inspect quality, then continue to all 10000 papers if clean.
- [x] Confirm input directory and file count.
- [x] Confirm model and thinking-off behavior.
- [x] Confirm production CLI resumability and `--limit` behavior.
- **Status:** complete

### Phase 2: Concurrency Trial Design
- [x] Use one reusable output directory so completed trial papers are not reprocessed.
- [x] Use increasing `--limit` values to cover 200 unique papers while stepping concurrency upward.
- [x] Run ladder and choose the highest reliable concurrency observed.
- **Status:** complete

### Phase 3: 200-Paper Trial Extraction
- [x] Complete exactly the first 200 sorted papers in the corpus output directory.
- [x] Record failures, truncations, retries, token totals, and wall-clock throughput.
- **Status:** complete

### Phase 4: Quality Check
- [x] Inspect `run_summary.json`, per-paper `status.json`, validation files, and sampled `06_extraction.json`.
- [x] Check for missing core sections, metadata anomalies, validation failures, and citation/reference problems.
- **Status:** complete

### Phase 5: Full Extraction
- [x] If the 200-paper trial is acceptable, resume the same output directory without `--limit`.
- [ ] Monitor progress and failures during the remaining corpus run.
- **Status:** in_progress

## Planned Concurrency Ladder
| Step | Limit | New papers | paper_concurrency | llm_concurrency | Purpose |
|------|-------|------------|-------------------|-----------------|---------|
| A | 20 | 20 | 10 | 30 | Passed: 20/20 completed, 0 failed, 0 truncated |
| B | 60 | 40 | 16 | 48 | Passed: 40/40 completed, 0 failed, 0 truncated |
| C | 120 | 60 | 24 | 72 | Passed: 60/60 completed, 0 failed, 0 truncated |
| D | 200 | 80 | 32 | 96 | Passed: 80/80 completed, 0 failed, 0 truncated |

If a step fails due to API saturation, rate limits, transport instability, or widespread parsing failures, retry the remaining papers at the previous reliable concurrency rather than repeating the same failing setting.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use `deepseek-v4-pro` with default base URL `http://35.220.164.252:3888/v1` | Requested model; project config default points at the OpenAI-compatible proxy. |
| Do not pass `--keep-references-in-body` | Default body hygiene strips bibliography tails before body-fed stages and was recently validated. |
| Keep `--max-tokens 32768` and `--planning-max-tokens 24576` | Current DeepSeek/Qwen-safe defaults. |
| Keep cache warming enabled | Default cost lever; avoids racing the shared paper prompt cold across content sections. |
| Use the same output directory for trial and full run | Production runner skips completed papers when rerun without `--force`. |
| Use `32/96` for the full run | It was the highest tested reliable setting and the fastest trial step: 80 papers in 297.2s with 0 failures/errors/truncations. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Initial `wc -l` through `rtk` showed `4` for the input folder | Verified with `rtk find`, which reported `10000F`; the first result was an artifact of output compression/pipeline behavior. |
