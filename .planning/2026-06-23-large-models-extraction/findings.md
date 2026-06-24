# Findings

- 2026-06-23 02:40 status: 1709 completed, 8 in progress, 2 failed, 20 truncated, no `run_summary.json` yet.
- 2026-06-23 02:50 status: 1769 completed, 8 in progress, 2 failed, 20 truncated, no `run_summary.json` yet.
- 2026-06-23 03:01 status: 1836 completed, 8 in progress, 2 failed, 20 truncated, no `run_summary.json` yet.
- 2026-06-23 03:11 status: 1895 completed, 8 in progress, 2 failed, 20 truncated, no `run_summary.json` yet.
- 2026-06-23 03:21 status: 1961 completed, 8 in progress, 2 failed, 21 truncated, no `run_summary.json` yet.
- 2026-06-23 03:28 final: 2000 processed, 1998 completed, 2 failed, 21 truncated, `run_summary.json` present.
- Failed items observed: `ACL_2025_0998-12b967decb8e`, `NeurIPS_2024_4166-ddbd4d79cf28`.
- Final failure reasons: `ACL_2025_0998-12b967decb8e` has legacy paradigm fields/forbidden unit types; `NeurIPS_2024_4166-ddbd4d79cf28` has four evidence units with invalid Component type.
- Latest logs after recovery show the process continuing normally into `NeurIPS_2025_*` items with no network or rate-limit crash.
