# Progress Log

## Session: 2026-06-24

### Current Status
- **Phase:** 2 - Concurrency Trial Design
- **Started:** 2026-06-24

### Actions Taken
- Read `RTK.md`; all shell commands must be prefixed with `rtk`.
- Read the planning-with-files skill and created a dedicated active planning directory.
- Confirmed the input folder contains 10000 Markdown files.
- Confirmed production CLI options and defaults.
- Confirmed `deepseek-v4-pro` thinking is disabled automatically by the async LLM client.
- Confirmed `--limit` and resumability semantics in `production/runner.py`.
- Inspected `production/worker.py` to estimate per-paper LLM fanout and choose a paired concurrency ladder.

### Planned Trial Output
- Output directory will be under `production-outputs/` and reused for both the 200-paper trial and the full extraction if quality passes.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Input file discovery | 10000 Markdown files | `rtk find` reported `10000F` | pass |
| CLI availability | Production CLI help renders | `rtk .venv/bin/python -m production --help` succeeded | pass |
| Thinking disabled | DeepSeek receives thinking-off body | `production/llm.py` calls `_thinking_off_extra_body(model)` | pass |
| Concurrency Step A | 20 papers at `10/30` with no failures | 20/20 completed, 0 failed, 0 truncated, 246.9s elapsed, 160 LLM calls | pass |
| Concurrency Step B | Remaining papers through limit 60 at `16/48` with no failures | 40/40 completed, 0 failed, 0 truncated, 253.5s elapsed, 320 LLM calls, `total_errors=0` | pass |
| Concurrency Step C | Remaining papers through limit 120 at `24/72` with no failures | 60/60 completed, 0 failed, 0 truncated, 272.9s elapsed, 480 LLM calls, `total_errors=0` | pass |
| Concurrency Step D | Remaining papers through limit 200 at `32/96` with no failures | 80/80 completed, 0 failed, 0 truncated, 297.2s elapsed, 639 LLM calls, `total_errors=0` | pass |
| 200-paper quality gate | No missing files, no validation issues, no truncation, no empty final units | 200/200 completed; required files present; validation issue total 0; metadata venue/year 200/200; 5534 final units all have ids/provenance/non-empty payload | pass |

### Errors
| Error | Resolution |
|-------|------------|
| `python3 /Users/wxy/.codex/skills/planning-with-files/scripts/session-catchup.py` failed because the file was absent | Used project-local `.codex/skills/planning-with-files/scripts/session-catchup.py`. |
| Piped `find | wc -l` through `rtk` returned `4` | Treated it as an `rtk` compression artifact and verified using `rtk find` summary. |

### Full Run
- Decision: continue with `--paper-concurrency 32 --llm-concurrency 96`, the largest reliable setting observed in the 200-paper trial.
- Rationale: Step D was clean and fastest among tested settings; trial quality checks found no blocking content issue.
- Started full run in the same output directory without `--limit`; runner skipped 200 completed trial papers and began processing 9800 remaining papers.
- Early full-run checkpoint: about 10 minutes in, progress was 217/9800 with 0 failed and ETA around 7.4 hours; no warning/error/truncation pattern observed in console output.
- Interrupted the first full run after one census truncation on `AAAI_2025_1967-02d3cd9a2b8a` to avoid accumulating avoidable failures with the default planning token budget.
- Post-interrupt status: 572 completed, 1 failed, 32 `in_progress`; runner resumability only skips `completed`, so failed/interrupted papers will be retried.
- Resume plan: rerun the same output directory at `32/96` with `--planning-max-tokens 32768`.
- Resume checkpoint: `AAAI_2025_1967-02d3cd9a2b8a` completed successfully with 0 validation issues after increasing planning max tokens.
- Resume checkpoint at 101/9428 processed: 0 failed; ETA stabilized around 9 hours; no API/rate-limit failures observed.
- Resume checkpoint at 200/9428 processed: 0 failed; ACL long papers with very large appendices are being trimmed before body-fed stages and completing normally.
- Resume checkpoint around 394/9428 processed: 0 paper failures; one nonfatal citation-layer truncation observed on `ACL_2024_0096-3ec913a0da3f`, to inspect/retry after the bulk run.
- Resume checkpoint at 500/9428 processed: 0 paper failures; one known nonfatal citation warning; ETA remains about 8.3 hours.
- Monitor checkpoint at 1406 total completed: 0 paper failures, 0 validation issues, 2 citation-layer truncation warnings (`ACL_2024_0096-3ec913a0da3f`, `ACL_2024_0786-8ba822748d47`).
- Monitor checkpoint at 1733 total completed: 0 paper failures, 0 validation issues, 3 citation-layer truncation warnings (`ACL_2024_0096-3ec913a0da3f`, `ACL_2024_0786-8ba822748d47`, `ACL_2025_0178-7bba1d0d05fd`).
- User requested a pause; sent Ctrl-C to the production process and the monitor sleep. Stop checkpoint: 2145 completed, 32 `in_progress`, 0 failed, 0 validation issues, 6 citation-layer truncation warnings. The stopped run used `--paper-concurrency 32 --llm-concurrency 96`.
- User requested 3x concurrency; resumed with `--paper-concurrency 96 --llm-concurrency 288` and `--planning-max-tokens 32768`.
- High-concurrency checkpoint after startup: 2381 completed, 96 `in_progress`, 0 failed, 0 validation issues, 6 citation-layer truncation warnings (no new warnings since resume).
- High-concurrency checkpoint after ~5 minutes: 2646 completed, 96 `in_progress`, 2 failed, 2 validation issues. Failures were validation-quality failures, not explicit rate-limit/API errors, but they appeared immediately after increasing concurrency from a previously clean 2145-paper baseline.
- Stopped the `96/288` run and rolled back to the previously tested stable setting `--paper-concurrency 32 --llm-concurrency 96`; stop checkpoint before rollback resume was 2675 completed, 96 `in_progress`, 2 failed, 2 validation issues.
- Rollback run at `32/96` started from the same output directory and skipped 2675 completed papers. During the early rollback window the proxy/API returned repeated `Connection Closed` / proxy connection errors and failed attempts concentrated in the first resumed batch.
- Rollback monitor checkpoint: 3522 completed, 32 `in_progress`, 15 failed, 25 warnings, 3 validation issues. Failed timestamps were concentrated near the early rollback/proxy-error window; latest status updates were completing normally, so the run remained at `32/96` for continued monitoring rather than immediately lowering again.
- Rollback stability checkpoint after another short window: 3586 completed, 32 `in_progress`, 15 failed, 25 warnings, 3 validation issues. Failed and warning counts stayed flat while completed increased, so `32/96` remained active.
- Later monitor checkpoint: 3655 completed, 32 `in_progress`, 16 failed, 26 warnings, 4 validation issues. The new failure was `EMNLP_2025_0672-0bf5906f5c80`: evidence validation rejected `cmp:gpt4o_fewshot` as a `Component` in the evidence section.
- Paused the `32/96` run to avoid accumulating this validation pattern. Clean pause checkpoint: 3694 completed, 32 `in_progress`, 16 failed, 26 warnings, 4 validation issues; no production process remained.
- Diagnosed `EMNLP_2025_0672-0bf5906f5c80`: DeepSeek emitted a baseline as `id: cmp:gpt4o_fewshot`, `type: ExperimentSetup` inside evidence `experiment_setups[]`; assembly then re-typed it to `Component` by id prefix, leaving a method-family unit in evidence.
- Implemented a deterministic assembly guard in `section_pipeline.py`: flatten only typed arrays owned by the current section, and after prefix/type reconciliation drop units whose final type is not allowed for that section, recording warnings in `extraction_notes.uncertain_assignments`.
- Verification: the new AssemblyTests regression cases passed; full `tests/test_section_pipeline.py` passed (326 tests); `tests/test_agent_artifacts.py` passed (64 tests); local reassembly of `EMNLP_2025_0672-0bf5906f5c80` now validates with `issues []`.
- Resumed at `32/96` after the assembly guard. Checkpoint: `EMNLP_2025_0672-0bf5906f5c80` completed successfully, but 4 validation failures remained/appeared with `Legacy paradigm fields or forbidden unit types are present`.
- Diagnosed those 4 failures as validator false positives: `_contains_legacy_marker` was matching forbidden legacy type strings anywhere in the extraction, including legitimate content values such as score variants `Relation`, `Proposition`, `Category` and unit name `Setting`.
- Paused again at 3783 completed, 32 `in_progress`, 4 failed, 25 warnings, 4 validation issues; no production process remained.
- Patched `_contains_legacy_marker` to flag `paradigm_tags` and legacy values only in discriminator fields (`type`, `unit_type`, `node_type`), not arbitrary content strings.
- Verification: `tests/test_section_pipeline.py` passed (328 tests); `tests/test_agent_artifacts.py` passed (64 tests); the 4 failed papers' existing `06_extraction.json` files now validate with `issues []`.
- User requested switching from `32/96` to `64/192`. Stopped the `32/96` resume cleanly; switch checkpoint before restart: 3783 completed, 36 `in_progress`, 0 failed, 25 warnings, 0 validation issues.
- Started resume with `--paper-concurrency 64 --llm-concurrency 192 --planning-max-tokens 32768`; runner skipped 3783 completed papers and began processing 6217 remaining papers.
- `64/192` startup checkpoint after ~2 minutes: 3851 completed, 64 `in_progress`, 0 failed, 25 warnings, 0 validation issues. No new warnings since the switch; `EMNLP_2024_0059-92e7f8cb4275` completed successfully after the legacy-marker validator fix.
- `64/192` stability checkpoint after ~5 more minutes: 4044 completed, 64 `in_progress`, 0 failed, 26 warnings, 0 validation issues. Only one new warning appeared, a known nonfatal citation-layer truncation (`EMNLP_2025_1079-010cdba5a4cf`); no API/proxy failure wave observed.
- `64/192` second stability checkpoint after another ~5 minutes: 4248 completed, 63 `in_progress`, 0 failed, 26 warnings, 0 validation issues. Warning count stayed flat; keep `64/192`.
- `64/192` 10-minute checkpoint: 4696 completed, 64 `in_progress`, 0 failed, 28 warnings, 0 validation issues. Two new warnings were both nonfatal citation-layer truncations (`EMNLP_2025_1751-49905974dcd9`, `ICLR_2024_1261-d20a14b4a23e`); no API/proxy failure wave or validation failures.
- `64/192` 15-minute checkpoint: 5278 completed, 64 `in_progress`, 0 failed, 32 warnings, 0 validation issues. New warnings continued to be citation-layer truncations only; no concurrency/API failure wave.
- `64/192` later checkpoint: 5847 completed, 64 `in_progress`, 0 failed, 35 warnings, 0 validation issues. New warnings remained long-output truncations (citation layer, plus one reference-metadata truncation on `ICLR_2025_3304-f27a817e91ff`); batch has moved into ICML 2024.
- `64/192` 20-minute checkpoint: 6672 completed, 64 `in_progress`, 3 failed, 39 warnings, 0 validation issues. Failed papers were not API/proxy or validation failures: two evidence sections hit output truncation at 32768 completion tokens (`ICML_2025_1218-69acd5930858`, `ICML_2025_1422-3b66a53c8343`), and one method section failed after 3 non-truncated attempts (`ICML_2025_2499-951ac042a432`). Continue `64/192` while monitoring failed growth.
- `64/192` follow-up checkpoint: 7169 completed, 64 `in_progress`, 3 failed, 44 warnings, 0 validation issues. Failed count stayed flat; new warnings are still truncation-only. Batch has advanced into NAACL 2024.
- `64/192` later checkpoint: 7545 completed, 64 `in_progress`, 3 failed, 44 warnings, 0 validation issues. A brief lull in completed updates resolved; latest in-progress timestamps were fresh (~37s old), so the process was running normally.
- `64/192` checkpoint after moving into NeurIPS 2024: 8157 completed, 64 `in_progress`, 5 failed, 47 warnings, 0 validation issues. The two new failures were section-output truncations (`NAACL_2025_0473-584c1424ad6d` evidence, `NeurIPS_2024_0071-401f6b3db0ff` method), not API/proxy or validation failures; keep `64/192`.
- `64/192` later checkpoint: 8788 completed, 63 `in_progress`, 5 failed, 49 warnings, 0 validation issues. Failed count stayed flat; new warnings were citation-layer truncations only. Remaining corpus is roughly 1200 papers.
- `64/192` near-finish checkpoint: 9430 completed, 64 `in_progress`, 5 failed, 50 warnings, 0 validation issues. Failed count stayed flat; only one new citation-layer truncation warning. Remaining main-run work is roughly 500 papers plus active workers.
- `64/192` tail checkpoint: 9860 completed, 63 `in_progress`, 6 failed, 51 warnings, 0 validation issues. One new failed paper (`NeurIPS_2025_4201-df4bd3bcd45f`) was a method section failure after retries, not API/proxy or validation; one new citation-layer truncation warning. Waiting for final active workers.
- `64/192` main run finished: 9993 completed, 7 failed, 55 warnings, 0 validation issues, 0 `in_progress`. No production process remained. Failed papers are section-output truncation or section retry failures, not API/proxy/validation failures.
- Started a targeted failed-sample retry using the same output directory with `--paper-concurrency 2 --llm-concurrency 6 --max-tokens 65536 --planning-max-tokens 32768`. Runner skipped 9993 completed papers and began processing the 7 failed papers only.
- Targeted failed-sample retry result: 6/7 recovered to `completed` with 0 validation issues. Final aggregate became 9999 completed, 1 failed, 55 warnings, 0 validation issues. The remaining failed paper is `NeurIPS_2025_4201-df4bd3bcd45f`, still failing in method extraction after 3 non-truncated attempts; it failed both in the main run and in the targeted retry, so ordinary retry is not sufficient for this one.
