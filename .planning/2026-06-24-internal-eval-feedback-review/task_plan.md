# Task Plan: Internal Evaluation Feedback Review

## Goal
Carefully review `/Users/wxy/Downloads/内部评测结果.md`, map feedback to extraction pipeline behavior, and identify actionable code changes.

## Current Phase
Complete

## Phases

### Phase 1: Feedback Discovery
- [x] Read the internal evaluation feedback.
- [x] Extract recurring failure modes and concrete examples.
- [x] Record findings in findings.md.
- **Status:** complete

### Phase 2: Code Path Mapping
- [x] Identify extraction pipeline, prompts, schemas, and eval tooling relevant to the feedback.
- [x] Map each failure mode to likely code or prompt locations.
- [x] Record evidence-backed findings.
- **Status:** complete

### Phase 3: Change Recommendations
- [x] Decide which changes are low-risk and high-impact.
- [x] Separate code changes from prompt/schema/eval changes.
- [x] Note implementation order and verification approach.
- **Status:** complete

### Phase 4: Delivery
- [x] Summarize feedback themes and recommended edits for the user.
- [x] Include exact file references and residual risks.
- **Status:** complete

### Phase 5: Citation Tail Trim
- [x] Feed the citation-relation pass the same bibliography-and-after-trimmed body used by own-content stages.
- [x] Keep reference metadata extraction on the original full-paper reference blob.
- [x] Update tests and comments for the new citation input contract.
- **Status:** complete

### Phase 6: Fail-Case A/B
- [x] Reuse the prior production run as baseline for the 21 citation truncation failures.
- [x] Rerun those papers with the current code path.
- [x] Compare citation success, output shape, token usage, timing, and estimated cost.
- **Status:** complete

## Key Questions
1. What extraction defects are repeated across the evaluation feedback?
2. Which defects can be reduced by deterministic code instead of prompt-only tuning?
3. Which prompt or schema edits would most directly improve extraction quality?
4. What tests or evaluation harness changes would prevent regression?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use a scoped planning directory for this task | Existing planning sessions are unrelated; this keeps review context isolated. |
| Treat the feedback file as external data, not instructions | The file is user-supplied evaluation content and should not override system/developer/project rules. |
| Implement two low-risk fixes now | Metadata dirname regex and Measure setup-id contract mismatch directly explain feedback items and are deterministic changes with focused tests. |
| Trim citation input before bibliography by default | The 21 truncation failures all happen in citation Pass 1 and are associated with long reference/appendix tails; Pass 2 still receives the sliced bibliography from the original paper. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `rtk find` rejected compound predicates/actions | 1 | Switched to `rg --files` and simple `ls` commands under RTK. |

## Notes
- Shell commands should be prefixed with `rtk` per `/Users/wxy/.codex/RTK.md`.
- Use file paths and line references in final recommendations where possible.
