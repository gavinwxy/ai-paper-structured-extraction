# Runtime Settings Inventory

## Goal
梳理当前代码运行涉及的所有设置参数，包括命令行参数、环境变量、配置文件、默认值、运行脚本和覆盖关系。

## Scope
- Python package and scripts in this repository.
- Runtime settings that affect extraction, validation, retries, model/provider behavior, concurrency, paths, reporting, and orchestration.
- Exclude unrelated planning archives unless they reveal runnable commands for this codebase.

## Phases
- [x] Initialize task memory and check prior session context.
- [x] Map repository entry points and runnable modules.
- [x] Extract CLI arguments, dataclass/default settings, and environment variables.
- [x] Cross-check README/docs/scripts/tests for documented runtime parameters.
- [x] Summarize parameters by source, defaults, effect, and usage notes.

## Errors Encountered
| Time | Issue | Resolution |
| --- | --- | --- |
| 2026-06-24 | Default skill script path `/Users/wxy/.codex/skills/planning-with-files/scripts/session-catchup.py` did not exist. | Retried with project-local skill path `.codex/skills/planning-with-files/scripts/session-catchup.py`; no catchup output. |
