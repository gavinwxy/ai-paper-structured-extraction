# 代码库审计 — section-ir-0.13

**日期**：2026-06-11  
**分支**：`planning-stage-redesign-deepseek-light`  
**方法**：15 个子系统 finder agent 各自精读所属代码并报告有依据的缺陷；每条 finding 由独立的怀疑者 agent 对抗式复核（默认反驳，必须能从代码确认缺陷真实发生才保留）。45 个 agent，约 19 分钟。

**结果**：30 条原始 finding → **26 条确认 / 4 条反驳**。
按严重度（确认项）：high 6 ｜ medium 8 ｜ low 12。

> 注：confirmed 列表里 `section_pipeline.py:1561-1563` 的同一 bug 被 census / assembly / cross-contracts 三个 finder 各自独立发现（三角验证 → 高置信）。去重后为 24 个唯一缺陷。

---

## 🔴 High

### 1. normalize_census_nodes demotes a contribution_finding (Finding) extra root to "benchmark", producing an invalid census that hard-fails the whole paper

- **位置**：`section_pipeline.py:1561-1563`
- **类别**：bug ｜ **子系统**：census-stageA ｜ **复核置信度**：high
- **佐证**：另由 assembly, cross-contracts finder 独立发现同一缺陷

**问题**：When a census has more than one contribution root, the demotion branch sets the extra root's role to `"component" if extra.get("type") == "Method" else "benchmark"`. This is correct only for Method (->component) and ExperimentSetup (->benchmark) roots. A `contribution_finding` root has type `Finding` (id prefix `fnd:`); demoting it to `"benchmark"` (an ExperimentSetup role) makes its role/type/prefix mutually inconsistent. `validate_census` then re-derives node_type=ExperimentSetup from role `benchmark` and flags 'has role benchmark (type ExperimentSetup) but id prefix is not exp:'. Because validate_census runs once after normalize with NO retry (production/worker.py:134-138 and section_pipeline.py:4491-4495 both `raise ValueError` on any census issue), this kills the entire paper. Triggered by an analysis-style paper whose census emits a contribution_finding plus a weaker should-salient extra contribution/contribution_resource (so the finding root is not in must_roots and gets demoted), or any case where a contribution_finding is the demoted extra. Repro confirmed: census with `mth:demo`(contribution,must) + `fnd:bottleneck`(contribution_finding,should) -> after normalize, fnd:bottleneck.role='benchmark', and validate_census returns the prefix-mismatch error.

**证据**：`extra["role"] = "component" if extra.get("type") == "Method" else "benchmark"  (the else-branch maps a Finding-type extra to an ExperimentSetup role; type stays "Finding"/`fnd:` so validate_census rejects it)`

**建议修复**：Demote per the extra's actual type, e.g. a small map {Method: 'component', ExperimentSetup: 'benchmark', Finding: 'descriptive'} keyed on extra.get('type'), so a demoted contribution_finding becomes a valid Finding role (and re-derive node['type'] from the new role if needed). Add a regression test for a contribution_finding demoted extra.

<details><summary>对抗复核结论</summary>

Confirmed by reading the code and reproducing the failure. At section_pipeline.py:1561-1563 the multi-root demotion branch is `extra["role"] = "component" if extra.get("type") == "Method" else "benchmark"`. A `contribution_finding` root has type `Finding` (ROLE_TO_TYPE["contribution_finding"]=="Finding", lines 204-218) and id prefix `fnd:` (NODE_ID_PREFIX_BY_TYPE["Finding"]=="fnd:", line 168). When such a root is the demoted extra it falls into the else-branch and gets role `benchmark` (an ExperimentSetup role), while its `type` stays `Finding` and its id stays `fnd:...` (the type-derivation loop at lines 1498-1501 runs BEFORE demotion and is not re-run; demotion only mutates `role`). validate_census then re-derives node_type=ROLE_TO_TYPE.get("benchmark")=="ExperimentSetup" (line 1620), looks up expected prefix "exp:" (line 1624), and since `fnd:bottleneck` does not start with "exp:" appends the issue (lines 1625-1629). I reproduced this exactly: census with mth:demo(contribution,must)+fnd:bottleneck(contribution_finding,should) -> after normalize fnd:bottleneck.role=='benchmark', validate_census returns ["Census node fnd:bottleneck has role benchmark (type ExperimentSetup) but id prefix is not 'exp:'"]. A second path (all-should roots, finding at index>=1, keep_ids==roots[:1]) reproduces the same error; the control case (finding root is the kept must root) validates clean. The impact is real and hard: both call sites — section_pipeline.py:4491-4495 and production/worker.py:134-138 — call normalize_census_nodes then validate_census and `raise ValueError` on any non-empty issues list with no retry, so the entire paper fails. Test-gap verified: the demotion tests (tests/test_section_pipeline.py:209, 373) only exercise a Method extra (->component) and a Method-vs-resource case; FindingRootTests (2377-2413) only ever uses a single contribution_finding root (make_finding_root_census), so no passing test covers a demoted contribution_finding extra. Trigger plausibility: a census that emits a contribution_finding plus a co-equal/should-salient method or resource root (FG-7 multi-root analysis paper, or a mis-tagged weak census) is realistic given FG-5/FG-7 are designed exactly around multi-root/finding-root papers.

</details>

---

### 2. ExperimentSetup dedup loses per-score-row setup_id binding instead of repointing it

- **位置**：`section_pipeline.py:975-988`
- **类别**：data-loss ｜ **子系统**：assembly ｜ **复核置信度**：high

**问题**：_dedup_experiment_setups merges a duplicate ExperimentSetup (same name + section type) into a survivor and calls _rewrite_unit_references to repoint references. But _rewrite_unit_references only rewrites the Measure-level list fields REFERENCE_LIST_FIELDS = ("setup_ids", "finding_ids"); it does NOT rewrite the per-score-row setup_id (nor system_id/opponent_id/judge_id). So a score row whose setup_id pointed at the merged-away duplicate now dangles. The later _repair_score_refs (runs after dedup in assemble_extraction: dedup at L3381, repair at L3393) then sees a dangling/non-local setup_id and BLANKS it (score["setup_id"] = ""), silently destroying the row's setup binding even though the survivor exists and the Measure-level setup_ids list was correctly repointed. This is asymmetric with _sanitize_unit_ids (L2167-2172), which correctly rewrites the per-row setup_id/system_id/opponent_id/judge_id when it remaps ids. Reproduced: two same-name evidence ExperimentSetups (exp:eval, exp:eval_dup) with a Measure score row setup_id='exp:eval_dup' -> after assembly, measure setup_ids became ['exp:eval'] (correctly repointed) but the score row's setup_id became '' (lost, not repointed to exp:eval).

**证据**：`_rewrite_unit_references only iterates list fields: `for field in REFERENCE_LIST_FIELDS: values = unit.get(field); if isinstance(values, list): unit[field] = [replacements.get(value, value) for value in values]` — no per-score-row setup_id rewrite. Then _repair_score_refs blanks it: `score["setup_id"] = ""`. Test test_dedup_experiment_setup_rewrites_relation_endpoint only asserts relation-endpoint repointing, never score-row setup_id.`

**建议修复**：In _rewrite_unit_references, after rewriting REFERENCE_LIST_FIELDS, also iterate the Measure's score rows and apply replacements to per-row setup_id (and, for symmetry/safety, system_id/opponent_id/judge_id), mirroring _sanitize_unit_ids L2167-2172. e.g.: `for row in unit.get("scores", []) or []: if isinstance(row, dict): for key in ("system_id","setup_id","opponent_id","judge_id"): if row.get(key) in replacements: row[key] = replacements[row[key]]`.

<details><summary>对抗复核结论</summary>

Confirmed by reading the code and reproducing the defect end-to-end with the project's own test fixtures.

ROOT: `_rewrite_unit_references` (section_pipeline.py:975-988) only rewrites `REFERENCE_LIST_FIELDS`, which is defined at L524 as `("setup_ids", "finding_ids")` — i.e. only Measure-level list fields. It never touches the per-score-row `setup_id` (nor `system_id/opponent_id/judge_id`). This is asymmetric with `_sanitize_unit_ids`, which at L2167-2172 explicitly remaps `("system_id", "setup_id", "opponent_id", "judge_id")` on each score row.

ORDER: In `assemble_extraction`, dedup runs at L3381 (`_dedup_experiment_setups(...)`) and `_repair_score_refs` runs later at L3393. `_dedup_experiment_setups` builds `replacements` (L1049-1050) and calls `_rewrite_unit_references(sections, replacements)` at L1075. Born (non-census, non-covered) ExperimentSetups dedup normally (protection at L1046-1048 only shields census/covered ids; docstring L1011-1015 confirms born setups still dedup). After dedup the merged-away id no longer exists as a local unit, so `_repair_score_refs` finds the row's `setup_id` not in `local_ids`/not an ExperimentSetup and BLANKS it: `score["setup_id"] = ""` (L2426-2435).

REPRO (using tests/test_section_pipeline.py fixtures): two same-name evidence ExperimentSetups exp:eval and exp:eval_dup (name 'eval'), with mea:score carrying measure-level setup_ids=['exp:eval_dup'] and scores[0].setup_id='exp:eval_dup'. After assemble_extraction: exp:eval_dup merged away; measure setup_ids correctly repointed to ['exp:eval']; but scores[0].setup_id == '' (binding destroyed, not repointed to the surviving exp:eval). This is silent data loss of the per-row setup binding even though the survivor exists.

TEST GAP: the only relevant test, test_dedup_experiment_setup_rewrites_relation_endpoint (tests/test_section_pipeline.py:510-523), asserts only relation-endpoint repointing (target_id -> exp:demoset) and never asserts a score-row setup_id is repointed. test_dedup_preserves_same_name_census_setups covers protection, not row repointing. No passing test covers this path.

The proposed fix (mirror L2167-2172 inside _rewrite_unit_references, iterating scores and applying `replacements`) is correct. Severity high is appropriate: it silently destroys a score row's experiment-setup binding (which row was measured on which dataset/split) — a core relation in the IR — and the loss is masked as a benign "blanked dangling ref" warning.

</details>

---

### 3. value_num silently mis-parses 'e'/'E' scientific notation to the bare mantissa (off by 10^exp)

- **位置**：`section_pipeline.py:2262-2296`
- **类别**：correctness ｜ **子系统**：blob-evidence ｜ **复核置信度**：high

**问题**：_parse_value_num handles only the '<m> × 10^<e>' sci-notation form (via _SCI_NOTATION_RE). For standard E-notation strings ('1e3', '1e-3', '1.18e+13', '6.4e-4'), neither _SCI_NOTATION_RE nor _LEADING_NUM_RE recognizes the exponent: _LEADING_NUM_RE matches only the mantissa ('1', '1.18', '6.4') and stops at 'e', and float() of just the mantissa is returned. So value_num becomes the mantissa with the exponent dropped — e.g. '1.18e+13' -> 1.18 (off by 10^13), '6.4e-4' -> 6.4 (off by 10^4). This is exactly the failure the comment at line 2260-2261 warns about ('mis-parse the mantissa alone'), but the fix only covered the '× 10' form. The wrong value is the agent-facing numeric field and is reused by tools/build_agent_index.py (lines 332 and 547) to populate the corpus retrieval column and to classify table cells as numeric, so the error propagates into the agent index. Grounded in real production data: 06_extraction.json for papers 031_ICLR_2025 (FLOP counts '1.18e+13','1.13e+13','1.09e+13') and 053_NeurIPS_2025 ('6.4e-4') contain E-notation score values; the current parser stamps value_num=1.18 / 6.4 for these. (Those on-disk files show value_num=None because they were emitted by an older parser — the current code is strictly worse, producing a confidently-wrong number.)

**证据**：`_LEADING_NUM_RE = re.compile(r"^([+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))")  (no exponent alternative); _SCI_NOTATION_RE only matches r"...[x×*]\s*10...". Probe: _parse_value_num('1.18e+13') == 1.18, _parse_value_num('1e-3') == 1.0, _parse_value_num('6.4e-4') == 6.4.`

**建议修复**：Recognize E-notation before the mantissa-only fallback. Either add an optional exponent to the leading-number regex (e.g. r"^([+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)") and let float() parse it, or detect a trailing [eE][+-]?\d+ and parse the whole token via float(). Add test cases ('1e3'->1000.0, '6.4e-4'->0.00064, '1.18e+13') to tests/test_agent_artifacts.py::test_parse_table, which currently covers only the '× 10^' form.

<details><summary>对抗复核结论</summary>

Confirmed from the actual code. section_pipeline.py:2270-2296 `_parse_value_num`: `_SCI_NOTATION_RE` (line 2262-2264) only matches the `<m> [x×*] 10^<e>` multiplication form; `_LEADING_NUM_RE` (line 2265) `^([+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))` has NO exponent alternative. For canonical E-notation the regex matches only the mantissa and `float(match.group(1))` returns it, dropping the exponent. I ran the parser logic verbatim: `'1.18e+13'->1.18`, `'6.4e-4'->6.4`, `'1e3'->1.0`, `'3.2E5'->3.2` — off by 10^exp. The defect is LIVE: `_annotate_quantitative_payload(sections)` is called unconditionally in the main assembly path (line 3427) and stamps `score['value_num'] = _parse_value_num(score.get('value'))` on every Measure row (line 2313). It propagates downstream: tools/build_agent_index.py imports the same `_parse_value_num` (line 42-49) and uses it at line 332 (corpus retrieval value_num column) and lines 478/536/547 (numeric-cell classification of table blobs). Grounded in real production data: I scanned the repo's extraction JSON and found genuine E-notation score `value` strings — 031_ICLR_2025 has '1.18e+13'/'1.13e+13'/'1.09e+13', 053_NeurIPS_2025 has '6.4e-4'. The transcription passes these through verbatim (the raw value string is literally '1.18e+13'). On disk these rows currently have NO value_num key (they predate the stamping pass), so under current code they become confidently-wrong numbers — strictly worse, as the finding states. Test gap confirmed: tests/test_agent_artifacts.py::test_parse_table (lines 41-55) covers only '1 × 10−2' and '3.2 x 10^-4' (multiplication form); no E-notation case exists, so the bug passes all tests. Mitigating context (why not critical): value_raw/value always retains the faithful string so no source data is lost — only the derived agent-facing value_num field and the corpus retrieval index get a wrong number; the proposed fix (append optional `(?:[eE][+-]?\d+)?` to the leading-number regex) is correct and minimal.

</details>

---

### 4. Retrofit revalidates and overwrites 07_validation.json with the CURRENT validator, flipping previously-valid pre-0.12 corpora to invalid

- **位置**：`tools/build_agent_index.py:161-166`
- **类别**：data-loss ｜ **子系统**：agent-index ｜ **复核置信度**：high

**问题**：retrofit_paper() unconditionally re-runs validate_section_ir(extraction, census=...) and overwrites 07_validation.json for every paper dir, with NO IR-version gate. The module docstring claims version gating exists ('version gating' in the task spec / RF-21 retrofit version gate), but there is no ir_version check anywhere in build_agent_index.py (grep for 'ir_version'/'version' returns nothing). The current validator rejects any ir_version not in ACCEPTED_IR_VERSIONS = {section-ir-0.12, section-ir-0.13}. The project's own retrofit targets include the ros_ai-0.10 corpus (ir_version 'section-ir-0.10'). Running retrofit over it rewrites every paper's 07_validation.json to valid:false with at minimum the spurious issue 'extraction_notes has invalid ir_version: section-ir-0.10' (plus any 0.13-only structural rules), destroying the original recorded validation status of a finished older run.

**证据**：`Lines 161-166: `issues = validate_section_ir(extraction, census=census); validation = {"issues": issues, "valid": len(issues) == 0}; if _dumps(_load(paper_dir / "07_validation.json")) != _dumps(validation): save_json(paper_dir / "07_validation.json", validation)`. Confirmed empirically: a valid 0.10-style extraction yields `valid? False` with `['extraction_notes has invalid ir_version: section-ir-0.10']` because ACCEPTED_IR_VERSIONS = {'section-ir-0.12','section-ir-0.13'} (section_pipeline.py:159).`

**建议修复**：Before retrofitting, read extraction_notes.ir_version from 06_extraction.json and skip (or warn-and-skip) paper dirs whose version is not in ACCEPTED_IR_VERSIONS; at minimum do not re-run validate_section_ir / overwrite 07_validation.json for out-of-version corpora. Add a --force/--only-version flag for the deliberate case.

<details><summary>对抗复核结论</summary>

Confirmed from the actual code. tools/build_agent_index.py has NO ir_version/version gate anywhere (grep returns 0 hits). main() (lines 670-673) iterates every dir with 06_extraction.json and unconditionally calls retrofit_paper unless --no-retrofit; there is no --only-version/--force flag. retrofit_paper (lines 161-165) unconditionally runs `issues = validate_section_ir(extraction, census=census)` then overwrites 07_validation.json whenever `_dumps(_load(...)) != _dumps(validation)`. The validator (section_pipeline.py:159 ACCEPTED_IR_VERSIONS = {section-ir-0.12, section-ir-0.13}; lines 5007-5008) appends `extraction_notes has invalid ir_version: <v>` for any other version, and that branch runs for every extraction. I empirically reproduced it: a section-ir-0.10 extraction returns valid=False with issue 'extraction_notes has invalid ir_version: section-ir-0.10'. The 0.10 corpus is a genuine retrofit target — the user's own memory note (retrieval-fitness-question.md) states verbatim: "ros_ai 0.10 retrofit BLOCKED on version gate (validator would mark 0.10 outputs invalid — extend ACCEPTED_IR_VERSIONS first)", proving the author already recognized this exact hazard. No test covers it: tests/test_agent_artifacts.py has no test exercising retrofit_paper against an old version or checking the 07_validation overwrite (test_idempotent is about _annotate_quantitative_payload). So running build_agent_index.py over a pre-0.12 corpus silently rewrites every 07_validation.json to valid:false. Calibration: this is real data loss of the recorded validation status, though the lost status is reconstructible (original-version validator / VCS / re-extract) and requires the tool to be pointed at an out-of-version corpus; severity high is appropriate given the flip is silent, corpus-wide, and over a stated retrofit target.

</details>

---

## 🟠 Medium

### 5. main() exits 0 when no papers are found, masking the error

- **位置**：`production/cli.py:140-141`
- **类别**：error-handling ｜ **子系统**：orchestration ｜ **复核置信度**：high

**问题**：run_batch() returns {"error": "No papers found"} (runner.py:53-55) when discover_papers finds zero .md files (wrong input dir, all non-.md files, etc.). main() decides the process exit code solely from summary.get("failed", 0) > 0. The error dict has no "failed" key, so the check is 0 > 0 == False, sys.exit(1) is never called, and the process exits 0 (success) despite logging an error. A batch/CI script wrapping `python -m production` cannot detect 'no input discovered' via exit code, so a mis-pointed run looks like a clean success. The only success/failure signal the CLI exposes is its exit code, and it is wrong for this case.

**证据**：`cli.py:140 `if summary.get("failed", 0) > 0:` combined with runner.py:55 `return {"error": "No papers found"}` — the error path produces a summary with no `failed` key, so `.get("failed", 0)` is 0 and exit is 0.`

**建议修复**：In main(), also exit non-zero when the summary carries an error: `if summary.get("failed", 0) > 0 or summary.get("error"): sys.exit(1)`. Alternatively have run_batch return a `failed` count or raise for the no-papers case so the existing check fires.

<details><summary>对抗复核结论</summary>

Verified directly in code. production/runner.py:53-55 returns {"error": "No papers found"} (no "failed" key) when discover_papers(config.input_dir) yields zero .md files. production/cli.py:140-141 derives the process exit code solely from `if summary.get("failed", 0) > 0: sys.exit(1)`. With no "failed" key the expression is 0 > 0 == False, so sys.exit(1) is never reached and main() returns normally, exiting 0 despite the logged error at runner.py:54. I confirmed that only the normal-run summary carries a "failed" key: it comes from progress.summary() (production/progress.py:88-94 includes "failed": self.failed, spread into the summary at runner.py:145-146). The two early-return dicts (runner.py:55 no-papers, runner.py:82 all-skipped) have no "failed" key, so the guard cannot fire for them. No test exercises this path — grep of tests/ for run_batch / "No papers found" / the cli exit logic found nothing (the only matches are unrelated helper-script main()/summary.get() usages). One scoping correction to the finding: cli.py:103-105 already exits 1 for a non-existent input directory, so the bug does NOT fire for a wholly bogus path; it fires when the directory exists but yields zero .md files (empty dir, wrong-but-existing dir, all-non-.md files), which is exactly the case the description centers on. The proposed fix (also exit non-zero on summary.get("error")) is correct. Real, grounded, and matters for CI/batch wrappers that detect failure via exit code.

</details>

---

### 6. Retry backoff sleep is awaited while holding the global concurrency semaphore, throttling the whole batch under error storms

- **位置**：`production/llm.py:159-211`
- **类别**：concurrency ｜ **子系统**：llm-transport ｜ **复核置信度**：high

**问题**：In LLMClient.call the retry loop body — including the exponential-backoff `await asyncio.sleep(delay)` (up to 30s, 2/4/8s for the default max_retries=3) — runs INSIDE `async with self._semaphore:`. The semaphore is the only global backpressure for the entire run (constructed with max_concurrency=30 and shared across all papers — paper_concurrency=10 papers each fire census/relations/metadata/references/3-sections through this one client). When a call fails with a retryable transport error (429/5xx/timeout), the task keeps occupying its concurrency slot for the full backoff sleep instead of releasing it. Under any wave of transient proxy errors (exactly when backoff matters), every retrying call pins a slot for up to ~14s of pure sleep, so effective concurrency collapses far below 30 and unrelated papers' calls are starved waiting to acquire the semaphore. The sleep must happen with the slot released.

**证据**：`for attempt in range(self._max_retries + 1):
    async with self._semaphore:
        ...
        except Exception as exc:
            ...
            if attempt < self._max_retries:
                delay = min(2 ** attempt * 2, 30)
                ...
                await asyncio.sleep(delay)   # <-- still inside `async with self._semaphore``

**建议修复**：Move the backoff sleep outside the semaphore context. E.g. acquire/release the semaphore only around the `await self._client.chat.completions.create(...)` (and finish_reason check), capture the needed `delay` in the except block, then `await asyncio.sleep(delay)` after the `async with` block has exited (still inside the for-loop) so the slot is free during the wait.

<details><summary>对抗复核结论</summary>

Confirmed from the code. In production/llm.py the retry loop (line 158 `for attempt in range(self._max_retries + 1):`) acquires the global slot via `async with self._semaphore:` at line 159, and that block fully encloses the `except Exception` branch including `await asyncio.sleep(delay)` at line 206 (indentation: for=8sp, async-with=12sp, try/except=16sp, sleep=24sp). asyncio.Semaphore holds the permit until __aexit__; awaiting inside (including the backoff sleep) does NOT release it, and the next loop iteration re-acquires it. So a retrying call pins its concurrency slot for the entire backoff.\n\nThe semaphore is genuinely the single global backpressure: LLMClient is constructed once in production/runner.py:90 with max_concurrency=config.llm_concurrency and passed into process_paper (runner.py:102) for every paper; production/worker.py routes every pass (census/relations/metadata/references/sections via _call_and_parse → llm.call at worker.py:267/492) through that one client. Defaults match the finding: config.py llm_concurrency=30, paper_concurrency=10, max_retries=3. delay = min(2**attempt*2, 30) yields 2/4/8s for attempts 0/1/2 = 14s cumulative sleep per fully-retried call. Under a wave of retryable transport errors (429/5xx/timeout) these sleeping-but-slot-holding tasks shrink effective concurrency well below 30 and starve unrelated papers' calls waiting on the semaphore — exactly when backoff is supposed to help. The proposed fix (acquire/release the semaphore only around the create() call and finish_reason check, sleep after the async-with exits but still inside the for-loop) is correct.\n\nNo test protects the current placement: tests/test_production_worker.py covers usage accounting (LLMUsageAccountingTests), truncation fail-fast (TruncationFailFastTests, line 235), parse-retry (line 269), and content-section scheduling concurrency (line 136-150), but none assert that the backoff sleep is held inside the semaphore, so moving it out would not fail any passing test.\n\nDowngrading severity to medium: this is a real concurrency anti-pattern that degrades batch throughput under error storms, but it does not cause incorrect output, data loss, deadlock, or hangs — the pipeline still completes correctly and the effect self-resolves once transient errors subside, so it is below 'high' impact.

</details>

---

### 7. Measure comparison_direction omitted from optional-enum repair, so an empty-string value hard-fails the paper on the DeepSeek default path

- **位置**：`section_pipeline.py:2518-2531`
- **类别**：error-handling ｜ **子系统**：schema-contracts ｜ **复核置信度**：high

**问题**：_repair_unit_enums() exists to drop degenerate / out-of-vocab values on the freely-filled optional enum fields so an otherwise-sound extraction is not hard-failed (its docstring lists Finding.polarity, Method.method_kind, Measure.objective_class, and the per-score-row value_kind). For a Measure it repairs objective_class, table_role, and value_kind, but it never touches comparison_direction. comparison_direction is nonetheless validated strictly in _validate_unit_fields (line 4740: `if "comparison_direction" in unit and comparison_direction not in COMPARISON_DIRECTIONS`). The evidence prompt module (prompts/.../evidence.md line 20 and evidence-blob.md line 29) explicitly tells the model: 'When the paper gives no direction, omit the field entirely — do not emit unspecified or ""' — i.e. an empty-string comparison_direction is a known model failure mode the prompt is fighting. In json_object mode (DeepSeek is the baked-in default per config) the schema enum [higher_is_better, lower_is_better, target, unspecified] is only prompt guidance, not enforced at decode, so the model can emit `comparison_direction: ""`. _sanitize_unit_text only strips control chars (not empty strings), and no other assembly step removes it, so `"" not in COMPARISON_DIRECTIONS` fires at line 4740, producing a validation issue. production/worker.py line 192 sets `"valid": len(validation_issues) == 0`, so this single benign degenerate value marks the whole paper invalid — exactly the outcome the sibling enum repairs prevent. This is the lone optional Measure enum missing from the repair set.

**证据**：`In _repair_unit_enums, Measure branch: `_drop_invalid_optional(unit, "objective_class", MEASURE_OBJECTIVE_CLASSES, ...)` and `_drop_invalid_optional(unit, "table_role", MEASURE_TABLE_ROLES, ...)` and per-row `_drop_invalid_optional(row, "value_kind", SCORE_VALUE_KINDS, ...)` — but NO `_drop_invalid_optional(unit, "comparison_direction", COMPARISON_DIRECTIONS, ...)`. Meanwhile validation (line 4740): `if "comparison_direction" in unit and comparison_direction not in COMPARISON_DIRECTIONS:` appends a hard issue. Tests UnitEnumRepairTests cover polarity/method_kind/objective_class/table_role/value_kind but never comparison_direction.`

**建议修复**：Add `_drop_invalid_optional(unit, "comparison_direction", COMPARISON_DIRECTIONS, "Measure", uid)` to the Measure branch of _repair_unit_enums (line ~2524), so an out-of-vocab or empty-string comparison_direction is dropped (falling back to the omitted/unspecified default) instead of hard-failing the paper, mirroring objective_class/table_role. Add a regression test for `comparison_direction: ""`.

<details><summary>对抗复核结论</summary>

Confirmed every link in the causal chain by reading the code.

1) section_pipeline.py:2518-2531 — `_repair_unit_enums` Measure branch repairs `objective_class` (MEASURE_OBJECTIVE_CLASSES), `table_role` (MEASURE_TABLE_ROLES), and per-row `value_kind` (SCORE_VALUE_KINDS) via `_drop_invalid_optional`, but there is NO `_drop_invalid_optional(unit, "comparison_direction", COMPARISON_DIRECTIONS, ...)`. grep over the whole file confirms `comparison_direction` appears only in the schema field list (489), prompt-context comments (358, 2024), and the validator — never in any repair/normalization.

2) Schema (line 482-506) lists `comparison_direction` (489) as an optional Measure enum field, a peer of the very fields that ARE repaired (`objective_class` 490, `table_role` 499). COMPARISON_DIRECTIONS = {higher_is_better, lower_is_better, target, unspecified} (line 353); `""` is not a member.

3) Validation is strict: line 4740 `if "comparison_direction" in unit and comparison_direction not in COMPARISON_DIRECTIONS:` -> for value "" the key IS present and "" is not in the vocab, so line 4741 appends `Measure {uid} has invalid comparison_direction:`.

4) No upstream rescue: `_sanitize_str` (2072-2075) only strips control chars and collapses/strips whitespace — `""` returns `""` unchanged and the key is not deleted. No generic empty-string drop pass exists (verified by searching assembly for empty-string handling; only score/section/formula/objective_function drops exist).

5) Hard-fail confirmed: `validate_section_ir` accumulates issues from `_validate_unit_fields` (call at 4924); worker.py:192 sets `"valid": len(validation_issues) == 0`. A single "" comparison_direction issue therefore marks the whole paper invalid.

6) Known model failure mode: prompts/.../evidence.md:20 and evidence-blob.md:29 both say "do not emit unspecified or \"\"", confirming the model does emit "" and that on the json_object/DeepSeek default path the enum is prompt-guidance only, not decode-enforced.

7) Test gap: UnitEnumRepairTests (tests/test_section_pipeline.py:1641-1733) covers polarity, method_kind, objective_class, value_kind, and even an end-to-end `test_empty_polarity_survives_assembly` proving the explicit design intent that a degenerate empty optional enum must not hard-fail the paper. There is NO test for comparison_direction and no repair — the lone optional Measure enum omitted from both repair and regression coverage.

Severity nuance: this is a tail trigger (depends on the model emitting "" / out-of-vocab, which the prompt discourages), not a guaranteed every-paper break, but it is a real, reproducible inconsistency causing a benign value to invalidate an otherwise-sound paper — precisely the failure class the sibling repairs were written to prevent. medium is correct.

</details>

---

### 8. Misplaced `break` aborts contribution search at first contribution-role node; FG-12 reference-edge backfill silently skipped when a non-materialized contribution (e.g. contribution_finding) precedes the materialized one

- **位置**：`section_pipeline.py:3977-3982`
- **类别**：bug ｜ **子系统**：blob-references ｜ **复核置信度**：high

**问题**：In reconcile_reference_units the loop that resolves `contribution_id` (the source of all FG-12 reference-origin edges) only assigns `contribution_id` when the node is materialized in `type_by_id` (Method/ExperimentSetup units only), but the `break` is unconditional inside the `if role in CONTRIBUTION_ROLES` block. So it stops at the FIRST contribution-role node. CONTRIBUTION_ROLES = {contribution, contribution_resource, contribution_finding}, and a `contribution_finding` node materializes as a Finding (never in type_by_id). If a `contribution_finding` (or any contribution-role node whose unit didn't materialize as Method/ExperimentSetup) appears before a materialized Method/ExperimentSetup contribution in census['nodes'], the loop breaks with contribution_id=None and ALL builds_on/uses/compares_to edge backfill is skipped, even though references still link via cite_key. Census node order is preserved verbatim from the model (normalize_census_nodes does not reorder), so the model emitting the finding before the method triggers this. The FG-5 finding-root census fixture (make_finding_root_census, tests line 143-150) has exactly this shape (fnd:bottleneck contribution_finding first) but is never run through reconcile_reference_units, so no test covers it. Affects the sync pipeline (line 4522), production/worker.py:181, tools/build_agent_index.py:153, and tools/relink_references.py:70 (replays inherit the same loss).

**证据**：`Lines 3978-3982:
            if isinstance(node, dict) and node.get("role") in CONTRIBUTION_ROLES:
                cid = node.get("node_id")
                if isinstance(cid, str) and cid in type_by_id:
                    contribution_id = cid
                break
Repro: census nodes [contribution_finding 'fnd:root' (not in type_by_id), contribution 'mth:main' (materialized)], reference '7' role builds_on -> produces RELATIONS: [] (only 'Linked reference 7' warning). Reversing node order produces the expected edge {source_id: mth:main, relation: builds_on, target_id: mth:bert, origin: reference}.`

**建议修复**：Only break once a materialized contribution is found; otherwise keep scanning: replace the `break` so it is conditional, e.g. `if isinstance(cid, str) and cid in type_by_id: contribution_id = cid; break`. (Decide separately whether a Finding contribution should itself be a valid edge source; at minimum the search must not abandon a later materialized Method/ExperimentSetup contribution.)

<details><summary>对抗复核结论</summary>

Confirmed by reading the code and an empirical repro against the live module. At section_pipeline.py:3977-3982 the contribution-resolution loop:

    for node in census.get("nodes", []) or []:
        if isinstance(node, dict) and node.get("role") in CONTRIBUTION_ROLES:
            cid = node.get("node_id")
            if isinstance(cid, str) and cid in type_by_id:
                contribution_id = cid
            break

The `break` (line 3982) is indented at the outer `if role in CONTRIBUTION_ROLES` level, NOT inside the inner `if cid in type_by_id` block, so it stops at the FIRST contribution-role node unconditionally. CONTRIBUTION_ROLES = {contribution, contribution_resource, contribution_finding} (line 246), and contribution_finding maps to Finding via ROLE_TO_TYPE (line 207). type_by_id is built (lines 3925-3936) to contain ONLY Method/ExperimentSetup units, so a contribution_finding node is never in type_by_id. When such a node precedes the materialized contribution Method/ExperimentSetup in census order, the loop breaks with contribution_id=None, and because the FG-12 backfill is gated on `contribution_id` being truthy (line 4039), all builds_on/uses/compares_to reference-origin edges are silently skipped (no alternate path re-derives them at lines 4094-4110).

Empirical repro on the actual module: census [contribution_finding 'fnd:root' first, contribution 'mth:main' second, builds_on 'mth:bert' cite_key 7], reference 7 role builds_on -> produced relations: [] with only the "Linked reference '7'" warning; reversing to method-first produced ('mth:main','builds_on','mth:bert'). Exactly matches the finding's repro.

normalize_census_nodes (lines 1481-1564) does NOT reorder nodes (verified: it mutates roles/ids in place; order is verbatim from the model), and it explicitly keeps MULTIPLE must-salient contribution roots for FG-7 co_contribution (lines 1551-1563), so a Finding-root co-existing with a method/resource contribution emitted finding-first is a supported, realistic data shape. All four call sites share the function (sync section_pipeline.py:4522, production/worker.py:181, tools/build_agent_index.py:153, tools/relink_references.py:70) and inherit the loss; relink_references replays it.

Test gap confirmed: every FG-12 backfill test (tests/test_section_pipeline.py:2879-3005) places the materialized `contribution` Method FIRST, so the misplaced break happens to land on the materialized node. make_finding_root_census (lines 134-150) has the contribution_finding first but is only exercised through validate/normalize/assemble (tests 2380-2407), never through reconcile_reference_units, so no test covers this path.

The defect is a genuine logic error (off-by-one-scope misplaced break) causing silent loss of reference-origin graph edges; the finding's diagnosis, repro, scope, and proposed fix are all accurate.

Severity note: I downgrade from high to medium because the loss is partial (the reference still links via cite_key/provides_unit_ids; only the derived dependency/comparison edges are lost) and the trigger is specific (requires a non-materializing contribution-role node, in practice contribution_finding, to precede the materialized contribution AND for that reference to carry builds_on/uses/compares_to roles).

</details>

---

### 9. _manifest.json stamps the current IR_VERSION onto retrofitted older corpora it never upgraded

- **位置**：`tools/build_agent_index.py:704-710`
- **类别**：contract-mismatch ｜ **子系统**：agent-index ｜ **复核置信度**：high

**问题**：build_output_manifest() hardcodes ir_version=IR_VERSION ('section-ir-0.13', section_pipeline.py:1951) and the driver calls it with no version derived from the per-paper extractions. When run over a corpus produced by an older pipeline (e.g. section-ir-0.10), the emitted _manifest.json declares ir_version 'section-ir-0.13' even though the per-paper 06_extraction.json files still carry their original (older) extraction_notes.ir_version. An agent reading the manifest's data dictionary is told the wrong schema version for the files it is about to consume, and the manifest contracts (blob_primary_*, flat sections) may not even apply to that corpus.

**证据**：`Line 704-709: `manifest = build_output_manifest(blob_primary_evidence=True, blob_primary_references=blob_refs_seen, verify_scores=fidelity_checked_seen, flattened_sections=not wrapped_sections_seen)` — no version argument; build_output_manifest sets `"ir_version": IR_VERSION` (section_pipeline.py:1951). blob_primary_evidence is also hardcoded True regardless of what the corpus actually used.`

**建议修复**：Derive the manifest ir_version (and blob_primary_evidence flag) from the observed extraction_notes across the corpus rather than hardcoding; if versions are mixed or pre-0.12, refuse to emit a 0.13 manifest or stamp the actual observed version.

<details><summary>对抗复核结论</summary>

Confirmed from the code. build_agent_index.py:704-709 calls build_output_manifest() with NO version argument; build_output_manifest unconditionally sets "ir_version": IR_VERSION (section_pipeline.py:1951), and IR_VERSION="section-ir-0.13" (build_agent_index.py:158). A whole-file grep for "ir_version" in build_agent_index.py returns zero matches, proving (a) retrofit_paper (lines 115-175) never upgrades the per-paper extraction_notes.ir_version — it only setdefaults marker_namespaces and score_fidelity, reconciles refs, and annotates payload — and (b) the driver loop (670-702) reads `notes` only for blob_primary_references and score_fidelity, never the per-paper version. So when this tool is run over an older corpus (the MEMORY note explicitly lists "ros_ai-0.10 retrofit version gate" as an OPEN item, confirming the tool is meant to run over 0.10 corpora), each 06_extraction.json keeps extraction_notes.ir_version="section-ir-0.10" while the freshly written _manifest.json declares "section-ir-0.13". The manifest is literally a data dictionary that tells the consuming agent the schema version and the blob_primary contracts (lines 1994-1998: "baseline rows stay VERBATIM in source_tables[<marker>]"), so the agent is told the wrong version and contracts. The bug compounds: retrofit re-runs validate_section_ir (line 161), which at section_pipeline.py:5007 flags ir_version not in ACCEPTED_IR_VERSIONS={0.12,0.13} as invalid — so the very same run marks every old-corpus paper invalid per-paper yet stamps a 0.13 manifest beside them, an internal contradiction. The secondary claim is also true: blob_primary_evidence=True is hardcoded at line 705 regardless of what the corpus used. No test covers this path — tests/test_agent_artifacts.py:206-219 only asserts the hardcoded IR_VERSION stamp and the blob flag toggles; nothing exercises a retrofit over an older corpus. Refutation attempts (handled elsewhere / test-covered / intentional) all fail. Severity medium is correct: silently-wrong contract metadata handed to downstream agents, not a crash; only manifests when pointed at a pre-0.13 corpus, but that scenario is a documented intended use.

</details>

---

### 10. lift_blob_rows emits the row-group (rowspan) category as `system`, dropping the real method name and duplicating the label across grouped rows

- **位置**：`tools/build_agent_index.py:535-539`
- **类别**：correctness ｜ **子系统**：agent-index ｜ **复核置信度**：high

**问题**：Row-label (system) selection takes the first non-numeric cell among row[:2]. When a table uses a leading rowspan group column (very common in segmentation/leaderboard tables — e.g. a 'Weak'/'Full supervision' group spanning several method rows), _expand_grid correctly fills the group cell into column 0 of every spanned row, so every grouped body row begins with the group label. row[:2] then picks the group label as `system` and never reaches the actual method name in column 1. Result: multiple distinct systems collapse to the same group label, the true method names ('SEC', 'AffinityNet') are silently lost, and the leaderboard view is wrong, not merely missing.

**证据**：`Lines 535-539: `for cell in row[:2]:\n    if cell["text"] and _parse_value_num(cell["text"]) is None:\n        row_label = cell["text"]\n        label_cell_id = id(cell)\n        break`. Reproduced: a body with `<td rowspan='2'>Weak</td><td>SEC</td><td>50.7</td>` then `<td>AffinityNet</td><td>61.7</td>` produces two rows both with system='Weak' (SEC and AffinityNet lost). Tests only cover rowspan in the HEADER (test_rowspan_colspan_expand_and_multilevel_header), never a body group column.`

**建议修复**：Detect a leading rowspan-carried group column and prefer the rightmost leading non-numeric cell (or concatenate group + method, e.g. 'Weak / SEC') as the row label; alternatively, skip cells whose object id is shared with the previous row (rowspan carryover) when choosing the row label.

<details><summary>对抗复核结论</summary>

Confirmed by reading tools/build_agent_index.py:535-539 plus _expand_grid (437-464) and reproducing the bug. Lines 535-539 pick the first non-numeric cell in row[:2] as row_label (→ the `system` field, set at line 562). _expand_grid shares the same rowspan cell object across every spanned body row's column 0, so when a table uses a leading rowspan group column, column 0 of every grouped row carries the group label and row[:2] selects it before reaching the real method in column 1.

Reproduced exactly: `<td rowspan='2'>Weak</td><td>SEC</td><td>50.7</td>` then `<td>AffinityNet</td><td>61.7</td>` yields two rows both with system='Weak' (SEC/AffinityNet lost). Also reproduced with a realistic 3-row group taken from a real corpus table (benchmark paper 028, tests/benchmark/028_ICML...md contains `<td rowspan="6">Atm-based</td>` followed by Transformer/FLASH/Performer/...): all distinct models collapse to system='Atm-based' and the real model names are gone — 9 numeric cells all mislabeled under one fabricated system. The numeric values themselves are still emitted correctly (label_cell_id only suppresses the group cell), so the defect is wrong attribution, not missing data — matching the finding's claim that the leaderboard view is wrong rather than merely incomplete.

Output impact confirmed: lift_blob_rows feeds result_rows.extend(...) at line 699 and is persisted to _result_rows.jsonl (line 713), the agent-facing leaderboard artifact; no downstream filter corrects the `system` field.

Test gap confirmed in tests/test_agent_artifacts.py: the only rowspan test, test_rowspan_colspan_expand_and_multilevel_header (495-507), places rowspan on a <th> HEADER cell (it collapses into the multi-level header path, not a body group column); test_section_separator_row_emits_nothing (509-514) exercises a colspan full-width separator row, a different pattern that is correctly skipped. Neither exercises a body data row with a leading rowspan group column, so a passing test does not cover this.

Severity medium is fair: this is a corpus-realistic CV/leaderboard table layout (the pipeline's target domain), it silently produces incorrect data, but it is confined to the best-effort blob-lift baseline view (table_role='baseline', system_id=None), not the authoritative transcribed rows.

</details>

---

### 11. count_extraction.py rglob double-counts the same paper from nested/archived extraction copies, inflating the headline recall metric

- **位置**：`tools/count_extraction.py:44-48`
- **类别**：correctness ｜ **子系统**：tools-misc ｜ **复核置信度**：high

**问题**：iter_extraction_files uses path.rglob("*extraction.json") and returns every match with no de-duplication by paper id. When the target tree contains more than one copy of a paper's extraction file (an archived baseline subdir, a nested *_v2 re-run, a backup folder), each copy is counted as a separate paper: n_papers is inflated and every per-paper average (NODES, RELATIONS, FIELD-EDGES, RELATIONS_TOTAL) is skewed silently. This directly corrupts the tool's stated headline output -- a comparable before/after per-paper recall number. The pipeline.json exclusion (`not p.name.endswith("pipeline.json")`) does not help: the glob `*extraction.json` can never match a `*pipeline.json` name, so it is dead, and it does nothing to suppress duplicate `*extraction.json` files.

**证据**：`for p in path.rglob("*extraction.json") if not p.name.endswith("pipeline.json"). Confirmed empirically: iter_extraction_files('tests/deepseek-thinking-off') returns 20 files for 10 distinct papers (each appears once under the dir and once under _old_baseline_pre_strip/), so every paper (ds_off_014, _017, _028, ...) is counted x2 and all per-paper averages are halved/doubled with no warning.`

**建议修复**：De-duplicate by logical paper key before counting: e.g. collapse matches on (parent dir relative path stem) or on the extraction's own paper id, or stop recursing into known archive/baseline subdirs. At minimum, dedupe by file stem and warn when multiple files map to the same paper id so the inflated n_papers is visible rather than silent.

<details><summary>对抗复核结论</summary>

Confirmed from code and reproduced empirically. tools/count_extraction.py:44-48 `iter_extraction_files` uses `path.rglob("*extraction.json")` and returns every match with no dedup by paper id. Running the tool's own function on the in-repo fixture tests/deepseek-thinking-off returns 20 files for 10 distinct paper IDs (ds_off_014/017/028/... each appears once under the dir and once under _old_baseline_pre_strip/). In summarize() (line 104) `n_papers += 1` fires once per file, and per() divides `agg[key] / n_papers` (line 113), so n_papers is doubled and every per-paper average (NODES, RELATIONS, FIELD-EDGES, RELATIONS_TOTAL) is corrupted silently — exactly the headline before/after recall number the docstring (lines 4-6) says is the tool's purpose. Worse, the two copies are different content (verified: ds_off_014 = 30968B current vs 37351B baseline; ds_off_028 = 70362B vs 63788B), so the "pre_strip" baseline and post-strip current generations of the same paper are blended into one average. The secondary dead-code claim also holds: via fnmatch I confirmed no name matching `*extraction.json` can end in `pipeline.json`, so the `if not p.name.endswith("pipeline.json")` guard at line 47 never excludes anything (pipeline-wrapping is actually handled separately at lines 100-101). No test in tests/ references count_extraction / iter_extraction_files / count_one (grep returned nothing), so no passing test covers or guards this, and there is no warning emitted. Could not refute: the recursion into archive subdirs is unconditional, dedup is absent, and a real committed tree triggers it.

</details>

---

### 12. Table-blob safety auditor permits zero-click HTML injection (meta-refresh redirect, img/base beacons, javascript: links) from untrusted paper content

- **位置**：`tools/render_extraction.py:626-687`
- **类别**：error-handling ｜ **子系统**：render ｜ **复核置信度**：high

**问题**：render_table_prettify() inserts a source-table blob VERBATIM (unescaped) into the rendered page whenever _table_blob_is_safe() returns True (line 705: `body = html if _table_blob_is_safe(html) else ...`). That html is `m.group(0)` sliced directly from the OCR'd/converted paper content by _slice_source_tables() in section_pipeline.py (TABLE_BLOCK_RE = `<table\b.*?</table>`, line 79) — i.e. fully untrusted input. The auditor (_TableBlobAuditor / _table_blob_is_safe) only rejects the tags script/style/iframe/object/embed (_BLOB_REJECT_TAGS, line 631) and `on*` event-handler attributes (_check_tag, line 648). It uses a reject-list, not a table-tag allow-list, and it never inspects attribute VALUES for dangerous URI schemes. As a result the following all pass the audit and are emitted live into the page: `<meta http-equiv=refresh content="0;url=//evil">` (zero-click full-page redirect to an attacker URL the instant the HTML is opened), `<img src="//evil/track.png">` (zero-click network beacon / data exfil on load), `<base href="//evil/">` (rewrites relative URLs), and `<a href="javascript:...">` / `<form><button formaction=javascript:...>` / `<svg><a xlink:href=javascript:...>` (one-click script execution). This directly violates the auditor's documented contract ('nothing executable', lines 638-640, 696). The existing tests cover only the <script> tag and on* attribute cases (test_render_extraction.py:225,231) — the meta/base/img/form/javascript:-scheme vectors have no test, so the gap is not intentionally accepted.

**证据**：`_BLOB_REJECT_TAGS = {"script", "style", "iframe", "object", "embed"} and `_check_tag`: `if tag in _BLOB_REJECT_TAGS or any(str(a or "").lower().startswith("on") for a, _ in attrs): self.ok = False`. Verified live: `render_table_prettify('<table><tr><td><a href="javascript:fetch(...document.cookie)">x</a></td></tr></table>','','§5')` emits the javascript: link verbatim (no kb-mt-raw fallback); `_table_blob_is_safe('<table><tr><td><meta http-equiv=refresh content="0;url=//evil"></td></tr></table>')` returns True.`

**建议修复**：Switch the auditor from a small reject-list to an allow-list of benign table tags (table, thead, tbody, tfoot, tr, td, th, caption, colgroup, col, b, i, em, strong, sub, sup, br, span, etc.) — any tag outside it (meta, base, link, img, form, button, a, svg, ...) fails the audit. Additionally validate attribute values: reject any href/src/action/formaction/xlink:href/style whose value, after trimming/lowercasing/stripping whitespace, begins with `javascript:`, `data:`, or `vbscript:`. Add regression tests for the meta-refresh, img, base, form/formaction, and javascript:-scheme anchor cases asserting kb-mt-raw fallback.

<details><summary>对抗复核结论</summary>

Confirmed from code + live reproduction. The auditor is a reject-list, not an allow-list: tools/render_extraction.py:631 `_BLOB_REJECT_TAGS = {"script","style","iframe","object","embed"}` and `_check_tag` (line 648) `if tag in _BLOB_REJECT_TAGS or any(str(a or "").lower().startswith("on") for a,_ in attrs): self.ok = False`. It never inspects attribute VALUES for dangerous URI schemes. When `_table_blob_is_safe` returns True the blob is inserted unescaped at line 705 (`body = html if _table_blob_is_safe(html) else <pre>...`), via render_table_prettify, which is fed `entry.get("html")` at line 763 — i.e. the verbatim `<table>` slice from section_pipeline.py: TABLE_BLOCK_RE (line 79, `<table\b.*?</table>`) over `paper_content` at `_slice_source_tables` line 2788 (`html = m.group(0)`), untrusted OCR'd/converted paper content. I ran the code: meta-refresh, img beacon, base rewrite, javascript:-scheme anchor, form/formaction, svg xlink:href, and data: URI img all return is_safe=True and emit live (no kb-mt-raw fallback); I verified the literal emitted markup for the meta-refresh (`<meta http-equiv=refresh content="0;url=//evil">`) and javascript: anchor cases — both appear unescaped inside the page. This violates the auditor's stated contract ("nothing executable", docstring lines 638-640 / render_table_prettify line 696). Test gap confirmed: tests/test_render_extraction.py covers only `<script>` (line 225) and `on*` attribute (line 231); none of the meta/base/img/form/javascript: vectors are tested, so the gap is not intentionally accepted. The defect genuinely occurs. Severity is the only overstatement: the output is a STATIC offline HTML report generated from ingested papers and opened locally by the pipeline operator (full `<!DOCTYPE html>` page at line 1180), not a server-rendered multi-tenant web surface — there is no ambient cookie/session/auth for `document.cookie` exfil in the normal flow, and exploitation requires an attacker to plant crafted `<table>` HTML into a paper's converted content. Meta-refresh redirect and img/base/data: beacons are real zero-click-on-open effects, so it is a genuine HTML-injection / contract-violation bug, but the offline-artifact threat model makes "high" too strong; "medium" is accurate.

</details>

---

## 🟡 Low

### 13. Truncation path double-counts call latency and classifies one call as both success and error in LLMClient.stats

- **位置**：`production/llm.py:163-192`
- **类别**：bug ｜ **子系统**：worker ｜ **复核置信度**：high

**问题**：When a response returns with finish_reason=='length', the success-accounting block at lines 163-166 has already run: it sets `elapsed = time.monotonic() - t0`, does `self._call_count += 1` and `self._total_latency += elapsed`, then records usage. The code then raises TruncationError (line 172), which is caught at line 182 where it AGAIN computes `elapsed = time.monotonic() - t0` and does `self._total_latency += elapsed` (line 186) plus `self._error_count += 1` (line 187). Result for a single truncated HTTP call: `_total_latency` is incremented twice (with two slightly different elapsed measurements), while `_call_count` is incremented once and `_error_count` once. This corrupts the global `stats` property: `avg_latency_s = _total_latency / max(_call_count,1)` is inflated because the numerator counts the truncated call's latency twice but the denominator counts it once, and the same call is reported as both a completed call and an error. The generic `except Exception` branch (line 194) does NOT have this problem because a normal exception is raised from `.create()` before the success-accounting at 163-166 ever executes; only the truncation path runs success-accounting and then re-accounts in its except handler.

**证据**：`Lines 163-166: `elapsed = time.monotonic() - t0` / `self._call_count += 1` / `self._total_latency += elapsed`. Then line 169 `if choice.finish_reason == "length":` ... line 172 `raise TruncationError(...)`. Caught at line 182 `except TruncationError:` lines 185-187: `elapsed = time.monotonic() - t0` / `self._total_latency += elapsed` / `self._error_count += 1`.`

**建议修复**：In the `except TruncationError` handler, do not re-add latency (it was already added at line 165). Remove lines 185-186 (`elapsed = time.monotonic() - t0` and `self._total_latency += elapsed`) so the truncated call's latency is counted exactly once. Decide deliberately whether a truncation should also count as an error: if yes keep `_error_count += 1` but stop double-counting `_call_count` vs `_error_count` semantics; if the intent is to count it only as an error, move `_call_count += 1` out of the success block. The existing test `test_truncation_raises_and_does_not_retry` only checks per-paper drain_usage, not `client.stats`, so this is uncovered.

<details><summary>对抗复核结论</summary>

Verified directly against production/llm.py:159-197. On a truncated call (finish_reason=="length"): the success-accounting block runs first — line 163 `elapsed = time.monotonic() - t0`, line 164 `self._call_count += 1`, line 165 `self._total_latency += elapsed`, line 166 `_record_usage` — then line 169 detects `finish_reason == "length"` and line 172 `raise TruncationError`. That exception is caught at line 182, whose handler at lines 185-187 recomputes `elapsed = time.monotonic() - t0`, does `self._total_latency += elapsed` AGAIN, and `self._error_count += 1`. So for one truncated HTTP call: `_total_latency` is incremented twice (two slightly different measurements), `_call_count` +1, `_error_count` +1. The `stats` property (lines 43-50) computes `avg_latency_s = _total_latency / max(_call_count,1)`, whose numerator double-counts the truncated call's latency while the denominator counts it once → inflated avg; the same call is reported as both a `total_calls` and a `total_errors`. The finding's claim that the generic `except Exception` branch (line 194) is unaffected is also correct: a failure raised from `.create()` (line 162) jumps straight there before lines 163-165 ever run, so latency is added exactly once. I confirmed the test gap: tests/test_production_worker.py:235-250 (`test_truncation_raises_and_does_not_retry`) asserts only on `fake.create_calls` and `drain_usage` token totals; it never reads `client.stats` / `_total_latency` / `_call_count` / `_error_count`, so the bug is uncovered. Materiality confirmed: `llm.stats` is not dead — it is serialized into the run summary at production/runner.py:147. Scope note: the corruption is telemetry-only (run-summary latency/call/error counts); the token/cost path uses the separate `_usage`/`drain_usage` accumulator, which is correctly counted once per call (verified in _record_usage lines 57-89 and drain_usage 102-117), and extraction data/control flow are unaffected. Defect occurs only on truncation events (a rare fail-fast), so low severity is correct.

</details>

---

### 14. Gather-level exception bypasses ProgressTracker, desyncing run_summary counts and exit code

- **位置**：`production/runner.py:121-131`
- **类别**：error-handling ｜ **子系统**：orchestration ｜ **复核置信度**：medium

**问题**：asyncio.gather(*tasks, return_exceptions=True) can return a BaseException for a task (most realistically asyncio.CancelledError on Ctrl-C / shutdown, since _process_and_track itself awaits process_paper while holding the paper semaphore). The exception branch appends a {"status": "failed"} entry to paper_results but does NOT call progress.mark_failed(). Because the only place the tracker is updated is inside _process_and_track (which never ran to completion for that task), progress.completed/failed undercount. run_summary.json is built from progress.summary() (runner.py:145-153) and main()'s exit code reads summary['failed'] — both will then disagree with the paper_results list that records the actual failure. The summary 'failed' and exit status can therefore be wrong relative to reality.

**证据**：`runner.py:122-129 — the `if isinstance(result, BaseException):` branch appends to `paper_results` but the surrounding block never touches `progress`; `progress.mark_failed()` is only reached at runner.py:106 inside `_process_and_track`, which did not complete for the exceptioned task.`

**建议修复**：Call `progress.mark_failed()` inside the BaseException branch (runner.py:122) before appending the failed record, so progress.summary() stays consistent with paper_results regardless of where the failure surfaced.

<details><summary>对抗复核结论</summary>

The cited mechanism is accurate. runner.py:121-131: `for i, result in enumerate(results): if isinstance(result, BaseException): ... paper_results.append({"status": "failed", ...})` — this branch records a failed paper but never calls `progress.mark_failed()`. The only place the tracker counts a failure is runner.py:106 inside `_process_and_track`, which only runs if that coroutine completed. `summary` is built from `progress.summary()` (runner.py:145) and cli.py:140 reads `summary.get("failed", 0) > 0` for the exit code, so a paper landing in the BaseException branch is recorded in paper_results yet absent from progress.failed and the exit code. Confirmed empirically: asyncio.CancelledError is a BaseException but NOT an Exception (Python 3.10.13 here), and asyncio.gather(return_exceptions=True) returns a per-task CancelledError as a result element that isinstance(result, BaseException) catches while isinstance(result, Exception) would not. So the branch is genuinely reachable and the desync genuinely occurs when it fires.

However, the materiality is narrow. process_paper/_run_paper_pipeline (worker.py:90, 229) wraps the entire pipeline in `except Exception as exc:` and RETURNS a {"status":"failed"} dict — so EVERY ordinary failure surfaces as a returned dict, hits the runner.py:131 `else` branch, AND already had mark_failed() called at runner.py:106. The counts are fully consistent for all normal failures; the finding does not apply to them. The BaseException branch only fires for non-Exception BaseExceptions (CancelledError/KeyboardInterrupt/SystemExit). I verified there is NO per-task timeout (no asyncio.wait_for), NO task.cancel() on paper tasks (the only .cancel() is progress.py:86 for the reporter task), NO TaskGroup, and NO signal handling anywhere in production/. The realistic trigger is Ctrl-C, where the cancellation/KeyboardInterrupt typically propagates out of `await gather(...)` itself so the collection loop (runner.py:119-166) never runs at all — making the desync unreachable in that dominant case. No test covers run_batch/ProgressTracker or this branch (tests/test_production_worker.py drives process_paper only), so it is not a test-covered behavior.

Verdict: a real latent inconsistency — the branch was written specifically to record a failure yet omits the matching tracker update, leaving progress.failed and the exit code wrong relative to paper_results whenever it fires — but the firing conditions essentially do not arise in this codebase's actual runtime, so 'low' severity is correct.

</details>

---

### 15. process_paper failure before the try block bypasses ProgressTracker accounting, undercounting failures in the run summary

- **位置**：`production/worker.py:86-90`
- **类别**：error-handling ｜ **子系统**：worker ｜ **复核置信度**：high

**问题**：In `_run_paper_pipeline`, `paper_dir = ensure_paper_dir(...)` (line 87) and `write_status(paper_dir, "in_progress")` (line 88) run OUTSIDE the `try:` that begins on line 90. If either raises (e.g. mkdir/OSError from a permission or disk-full condition), the exception escapes `_run_paper_pipeline` and `process_paper` entirely rather than being converted into a `{status: "failed"}` dict. In the runner, `_process_and_track` (runner.py:101-107) only calls `progress.mark_failed()` when `process_paper` RETURNS a dict; an exception propagates to the outer `asyncio.gather(..., return_exceptions=True)` (runner.py:113) and is recorded into `paper_results` as failed (runner.py:122-129) but `progress.mark_failed()` is never invoked for it. Consequently `summary()` (built from the ProgressTracker at runner.py:146) reports fewer failures than the `paper_results` list, and the per-paper status.json is never written for that paper, so resumability cannot distinguish it from never-started.

**证据**：`worker.py lines 87-88 (`paper_dir = ensure_paper_dir(config.output_dir, paper_id)` and `write_status(paper_dir, "in_progress")`) sit before `try:` on line 90. runner.py:102-106 `result = await process_paper(...)` then `if result["status"] == "completed": progress.mark_completed() else: progress.mark_failed()` — only reached when process_paper returns, not when it raises.`

**建议修复**：Move `paper_dir = ensure_paper_dir(...)` and the initial `write_status(..., "in_progress")` inside the try/except in `_run_paper_pipeline` (guarding the failure-branch `write_status` against the case where paper_dir was never created), or wrap the body of `_process_and_track` in runner.py so an escaped exception still calls `progress.mark_failed()`. This keeps ProgressTracker counts consistent with paper_results.

<details><summary>对抗复核结论</summary>

Confirmed from the actual code. In production/worker.py:86-88, `t0 = time.monotonic()`, `paper_dir = ensure_paper_dir(config.output_dir, paper_id)`, and `write_status(paper_dir, "in_progress")` execute BEFORE the `try:` at line 90. ensure_paper_dir (production/outputs.py:12-17) calls `paper_dir.mkdir(...)` and `(paper_dir/"05_sections").mkdir(...)` (OSError on permission/disk-full/path issues); write_status->save_json (outputs.py:32-44) does `tmp.write_text(...)` then `tmp.rename(...)` (OSError). Either raise escapes _run_paper_pipeline. process_paper (worker.py:75-76) wraps the call in `async with paper_sem:` — asyncio.Semaphore.__aexit__ does NOT suppress exceptions, so the error propagates out of process_paper rather than returning a dict.

In the runner: _process_and_track (runner.py:101-107) does `result = await process_paper(...)` then branches on `result["status"]` to call progress.mark_completed()/mark_failed(); if the await raises, neither runs. The exception is captured by `asyncio.gather(..., return_exceptions=True)` (runner.py:113) and recorded into paper_results as `{"status":"failed",...}` (runner.py:122-129) — but progress.mark_failed() was never invoked. Since ProgressTracker.summary() (production/progress.py:88-97) derives `failed`/`processed`/`completed` solely from the counters, summary["failed"] undercounts relative to the count of failed entries in summary["paper_results"], and both are written together into run_summary.json (runner.py:145-154) with no reconciliation, producing an internally inconsistent persisted artifact. The "%d failed" log at runner.py:159-160 also undercounts. The except block at worker.py:229-243 (which converts errors to a failed dict AND writes status.json="failed") only catches exceptions raised inside the try (line 90+), so the pre-try setup failures also leave no per-paper status.json.

Not covered by tests: tests/test_production_worker.py only drives process_paper against a FakeLLM (no run_batch / _process_and_track test, no OSError-before-try test); grep found no run_batch/mark_failed/gather test anywhere in tests/.

Caveats that keep severity at low: the trigger requires a genuine OS-level failure (disk full, permission change, path collision) on the per-paper mkdir or status write, which is uncommon because run_batch already created/validated the parent output_dir at runner.py:36 before any paper runs. The finding's resumability sub-claim is mildly overstated — a missing status.json makes is_paper_completed (outputs.py:20-29) return False, causing a safe retry on resume (benign, not harmful) — but the core counter-vs-paper_results inconsistency is real and ungrounded by any test. Net: real, actionable, low severity.

</details>

---

### 16. Warm-cache scheduler catches BaseException (incl. CancelledError) and rethrows as RuntimeError

- **位置**：`production/worker.py:421-427`
- **类别**：concurrency ｜ **子系统**：orchestration ｜ **复核置信度**：high

**问题**：In the warm-content-cache branch the first section is run as `try: first = await _section(...) except BaseException as exc: first = exc`. Catching BaseException swallows asyncio.CancelledError: instead of propagating the cancellation, the loop at lines 435-445 treats the CancelledError as an ordinary section error and re-raises it as a plain RuntimeError ('Content extraction failed for N section(s)'). This converts a cooperative cancellation into a normal exception and also still launches `rest` (method+evidence) after the warmer was cancelled, doing extra LLM work during shutdown. The comment claims this 'matches gather's exception capture', but gather(return_exceptions=True) preserves the CancelledError object as-is rather than reclassifying it into a RuntimeError.

**证据**：`worker.py:422 `except BaseException as exc:  # noqa: BLE001 — match gather's exception capture` then worker.py:436-445 turns any captured exception (including CancelledError) into `raise RuntimeError(f"Content extraction failed ...")`.`

**建议修复**：Narrow the catch to `except Exception` (so CancelledError propagates and cancellation is honored), or explicitly re-raise asyncio.CancelledError before storing the exception in `first`.

<details><summary>对抗复核结论</summary>

Confirmed from the actual code and reproduced the path. At production/worker.py:420-427 the warm-cache branch runs the first section under `try: first = await _section(SECTION_ORDER[0]) except BaseException as exc: first = exc`. On Python 3.10 (verified), asyncio.CancelledError subclasses BaseException, so this catch swallows cancellation. The loop at worker.py:435-445 then treats any captured BaseException (including CancelledError) as an ordinary section error and raises `RuntimeError("Content extraction failed for N section(s)")`. I reproduced this exactly: a CancelledError delivered while awaiting the warmer is reclassified into RuntimeError, AND `rest = asyncio.gather(... SECTION_ORDER[1:] ...)` still launches method+evidence afterward (verified: launched == ['problem','method','evidence']). 

The outer handler in _run_paper_pipeline is `except Exception` (worker.py:229) — it does NOT catch a bare CancelledError but DOES catch the reclassified RuntimeError, so the divergence has real effect: on Ctrl-C/shutdown the paper is written to disk as status "failed" with a misleading "Content extraction failed" message and extra method+evidence LLM calls are issued, instead of the cancellation propagating cleanly. I confirmed the non-warm branch (worker.py:429-431, pure `gather(return_exceptions=True)`) propagates an EXTERNAL CancelledError correctly (verified by reproduction), so the warm branch genuinely diverges from gather's behavior under the realistic external-cancellation/shutdown path — contradicting the code comment "match gather's exception capture."

Caveat on the finding's comment-critique: for an INTERNALLY-raised CancelledError, gather(return_exceptions=True) actually DOES capture it as a result object (verified), so the two branches behave the same in that narrow case; the divergence the finding cares about is the external-cancellation case, where it holds. This nuance does not change the verdict.

The warm branch is the DEFAULT live path (production/config.py:42 `warm_content_cache: bool = True`). No test covers cancellation — tests/test_production_worker.py:98-150 only exercises ordering/concurrency of the warm scheduler, never delivers a CancelledError, so this is a genuine uncovered defect. Severity "low" is correct: cancellation only occurs on shutdown/Ctrl-C (no wait_for/timeout wraps these calls), so normal batch correctness is unaffected, but it causes incorrect "failed" accounting on disk and wasted LLM spend during shutdown.

</details>

---

### 17. _extract_balanced_json commits to the first '{' in the response, mis-parsing JSON wrapped in prose that contains braces

- **位置**：`section_pipeline.py:3523-3549`
- **类别**：error-handling ｜ **子系统**：census-stageA ｜ **复核置信度**：high

**问题**：_extract_balanced_json does `start = raw.find("{")` and balances from there, returning the first balanced brace group. When the model (not in a fenced block) prepends prose that itself contains braces before the real JSON object (e.g. 'Here is the output for set {A, B}: {"spine_summary":...}'), it returns `{A, B}`, which then fails json.loads, and the backslash-repair fallback cannot fix it, so _parse_llm_json raises JSONDecodeError. This burns a census retry (or fails outright if the model reliably emits such a preamble). The function should find the first '{' that begins a parseable object, not the first '{' anywhere. Repro confirmed: `_parse_llm_json('Sure! ... set {A, B}: {"spine_summary":{...},"nodes":[]}')` raises JSONDecodeError instead of returning the object.

**证据**：`start = raw.find("{")  ... for pos in range(start, len(raw)): ... if depth == 0: return raw[start : pos + 1]  (returns the FIRST balanced group, even if it is brace-prose, never retrying from a later '{')`

**建议修复**：If json.loads of the first balanced group fails, scan for subsequent '{' positions and try balancing/parsing from each, returning the first one that json.loads accepts; or attempt to find the largest/last balanced object. At minimum, fall back to scanning further '{' candidates rather than committing to the first.

<details><summary>对抗复核结论</summary>

Reproduced the exact defect against the real code. `_extract_balanced_json` (section_pipeline.py:3524) does `start = raw.find("{")` then balances from there, returning the FIRST balanced group (line 3547-3548 `if depth == 0: return raw[start : pos + 1]`) and never retries from a later '{'. I ran `_parse_llm_json('... set {A, B}: {"spine_summary":{"x":1},"nodes":[]}')` and it returns `{A, B}` from the balancer, json.loads fails, the backslash-repair fallback (line 3565) cannot fix `{A, B}`, and `_parse_llm_json` raises JSONDecodeError — the repro in the finding is accurate. I confirmed no test in tests/ references `_extract_balanced_json` or `_parse_llm_json` (grep returned nothing; tests/test_section_pipeline.py only has unrelated startswith assertions), so no passing test covers this. The logic error and the absence of test coverage are both confirmed.

HOWEVER the severity is overstated. `_extract_balanced_json` is reached only via `_parse_llm_json` when `not cleaned.startswith("{")` after <think>-stripping + fence extraction (line 3558) — a degraded/off-contract fallback, not the normal path. Every production caller (run_node_census:3646-3653, run_relation_pass:3675, metadata:3731, references:3839, section:4309) sets `response_format` via `build_response_format`. For the default model `deepseek-v4-pro` (production/config.py:13, cli.py:56, README:235/259 → api.deepseek.com) this is `{"type":"json_object"}`, and for the OpenAI/Gemini proxy it is strict `json_schema` (lines 570-579, 712-721). Both modes constrain the API response to a pure JSON object with no prose preamble, so the brace-prose-preamble scenario requires the model to violate its response_format contract. I also confirmed the fallback already correctly handles the realistic degraded case it exists for — prose WITHOUT braces ("Here is the JSON:\n{...}") parses fine; only leaked prose that itself contains a brace group mis-parses. So this is a genuine but narrow robustness gap in a defensive fallback path, not a live census-failure path under the documented production setup. Real, fix is sound (scan subsequent '{' candidates and return the first json.loads-acceptable one), but low severity.

</details>

---

### 18. Dead/stale SECTION_MATERIALIZED_NODE_TYPES contradicts RF-08 Problem-as-census-node and is never referenced

- **位置**：`section_pipeline.py:128-138`
- **类别**：dead-code ｜ **子系统**：census-stageA ｜ **复核置信度**：high

**问题**：SECTION_MATERIALIZED_NODE_TYPES maps `"problem": set()` with the comment 'Problem and Finding are not census nodes'. This reflects pre-RF-08 behavior, but RF-08 (section-ir-0.13) made the `prb:` Problem a first-class census node planned by the census and materialized (id-reused) by the problem section (see lines 169-171 and ROLE_TO_TYPE['problem']='Problem'). The constant is never read anywhere in section_pipeline.py, production/, tools/, or tests/ (grep confirms a single definition-site hit), so it is dead code, but its presence and stale comment misrepresent the current contract and could mislead a future change that wires it into coverage logic (where `problem: set()` would wrongly treat a must `prb:` node as non-materializable). No runtime impact today only because it is unused.

**证据**：`SECTION_MATERIALIZED_NODE_TYPES: dict[str, set[str]] = { "problem": set(), ... } with comment '# Problem and Finding are not census nodes' — contradicted by NODE_ID_PREFIX_BY_TYPE['Problem']='prb:' and the RF-08 census-Problem design; the symbol has zero references.`

**建议修复**：Either delete SECTION_MATERIALIZED_NODE_TYPES and its stale comment, or update it to `"problem": {"Problem"}` and correct the comment to reflect that the census now plans the Problem node (RF-08); ensure it stays consistent with SECTION_ALLOWED_UNIT_TYPES.

<details><summary>对抗复核结论</summary>

Verified all factual claims against the code. (1) Dead code: a repo-wide search (excluding .git and archive/) for SECTION_MATERIALIZED_NODE_TYPES returns exactly one hit — the definition at section_pipeline.py:131. No reads in section_pipeline.py, production/, tools/, or tests/. The only other textual mentions are in archive/*.md docs and an unrelated comment in tests (line 154, about contribution_finding, not the constant). No dynamic/getattr/globals() access either. (2) Coverage logic does NOT consume it: build_extraction_notes (section_pipeline.py:1876-1898) computes coverage structurally as census_must_node_ids(census) & materialized_ids; the assembly trace (~5043-5086) does the same. The constant is never wired in, confirming the finding's claim that it could mislead a future change but has no runtime impact today. (3) Stale comment confirmed: line 128 'Problem and Finding are not census nodes' contradicts the current RF-08 contract — NODE_ID_PREFIX_BY_TYPE['Problem']='prb:' (line 171), ROLE_TO_TYPE['problem']='Problem' (line 217), the census 'problem' role (lines 198-200, 233), and the in-file comments at 169-170/199-200 that the census plans the Problem and the problem section materializes it by id reuse. The Finding half is likewise stale (lines 134-135 note the census plans the contribution_finding root Finding). (4) No test asserts consistency of this constant, so no passing test refutes it. Minor inaccuracy in the finding: the dict's 'evidence' value already correctly includes 'Finding' (line 137), so only the 'problem': set() entry and the blanket prose comment are actually stale — the finding slightly over-frames this, but its core characterization (dead code + stale/misleading comment, no runtime impact) is correct and self-acknowledged. This is a genuine dead-code/documentation-hazard defect, not a logic/data-loss bug; low severity is appropriate.

</details>

---

### 19. _attach_model_captions misattaches a caption to the anchorless ('') source table when a Measure has empty source_table_marker but a set caption_marker

- **位置**：`section_pipeline.py:2964-2996`
- **类别**：edge-case ｜ **子系统**：blob-evidence ｜ **复核置信度**：high

**问题**：The guard `if not cmarker or tmarker not in source_tables: continue` fails to exclude the case where tmarker canonicalizes to '' (the Measure has no source_table_marker) AND _slice_source_tables captured an anchorless table (one that precedes the first [§N] block), which is stored under the empty-string key ''. In that situation `tmarker not in source_tables` is False (the '' key exists), so the code proceeds and overwrites the anchorless table's caption (and sets caption_marker) using an unrelated, marker-less Measure's caption_marker. The anchorless '' table is deliberately excluded from build_table_index, so a Measure pointing at no table by marker should never drive its caption. The wrong caption is display-only and anchorless tables are rare, hence low severity, but it is an unintended write keyed on the empty marker.

**证据**：`Probe: source_tables == {'': {...}} (anchorless table) plus a Measure {source_table_marker:'', caption_marker:'§1'} -> _attach_model_captions sets source_tables['']['caption']='**Caption Foo**' and ['caption_marker']='§1' with no warning. Guard at line 2966: `if not cmarker or tmarker not in source_tables: continue` (tmarker=='' is a valid key).`

**建议修复**：Tighten the guard to require a non-empty tmarker, e.g. `if not cmarker or not tmarker or tmarker not in source_tables: continue`, so a Measure with no source_table_marker can never attach a caption to the anchorless '' table entry.

<details><summary>对抗复核结论</summary>

Confirmed reproducible. In section_pipeline.py:2964-2966, `tmarker = _canon_marker(unit.get("source_table_marker") or "")` yields "" for a Measure with no source_table_marker (verified _canon_marker("")=="" at lines 3009-3015), and the guard `if not cmarker or tmarker not in source_tables: continue` does NOT skip when tmarker=="" and "" is a key in source_tables. An anchorless table (one preceding the first [§N] marker) IS stored under the "" key by _slice_source_tables (line 2777 `anchor=""`, line 2791 `tables[anchor]={...}`), as the code's own comment at 2814-2817 and the test test_anchorless_table_excluded_from_index confirm. So a Measure that omits source_table_marker but sets caption_marker reaches lines 2995-2996 and silently overwrites source_tables[""]["caption"] and caption_marker with an unrelated caption, emitting NO warning (unlike every other reject/conflict branch in the function which appends to `warnings`).

Direct probe reproduced it exactly: paper with a table before [§1] plus a Measure {caption_marker:'§1'} (no source_table_marker) -> source_tables[''] caption changed from '' to 'Table 1: a totally unrelated caption', caption_marker set to '§1', warns==[].

Impact: the finding called this display-only, but it actually propagates further — tools/build_agent_index.py lift_blob_rows iterates ALL source_tables.items() INCLUDING the "" key (line 524) and emits `table_caption` (line 573) for the anchorless table's lifted rows; a second probe confirmed those rows carry the misattributed caption into the agent-readiness index. The renderer's render_measure_block does NOT read the "" entry (line 754-755 gates on a non-empty marker), so the HTML render is unaffected, but the agent index is. No test covers the empty-source_table_marker + anchorless-table conjunction (CaptionGuardTests only uses real §N markers). The proposed fix (`if not cmarker or not tmarker or tmarker not in source_tables: continue`) is sound and aligns with design intent (the "" table is deliberately unaddressable, so a Measure should never drive its caption); it does not affect legitimate Measures, which always carry a real non-empty tmarker. Severity low is appropriate: anchorless tables are rare, the trigger requires the unusual caption_marker-without-source_table_marker combination, and only a label (not numeric data) is corrupted.

</details>

---

### 20. Generator emits inconsistent IR version strings across schemas (0.13 vs 0.12) for the same release

- **位置**：`tools/generate_section_schemas.py:530, 633`
- **类别**：contract-mismatch ｜ **子系统**：schema-generator ｜ **复核置信度**：high

**问题**：node_census_schema() embeds "Stage A of section-ir-0.13" in its description (line 530) while relation_pass_schema() embeds "Stage B of section-ir-0.12" (line 633). Both are produced by the same generator run for the same release, and both description strings are shipped verbatim into the model-facing structured-output schemas (build_response_format / _augment_prompt_for_json_object). The canonical version is IR_VERSION = "section-ir-0.13" (section_pipeline.py:158), so the relation-pass label is stale. This is not a parsing bug (no version gate reads these strings), but it ships a wrong/contradictory version label to the model and into the committed schemas/relation-pass-output.schema.json.

**证据**：`L530: "Stage A of section-ir-0.13: a flat census ..."  vs  L633: "Stage B of section-ir-0.12: structural edges ...". section_pipeline.py:158 IR_VERSION = "section-ir-0.13".`

**建议修复**：Change line 633 from "Stage B of section-ir-0.12" to "Stage B of section-ir-0.13" (and ideally derive the version label from a single imported IR_VERSION constant so the two stage descriptions cannot drift apart again).

<details><summary>对抗复核结论</summary>

Confirmed all factual claims by reading the cited code. tools/generate_section_schemas.py:531 (node_census_schema) embeds "Stage A of section-ir-0.13" while line 634 (relation_pass_schema) embeds "Stage B of section-ir-0.12"; the canonical version is section_pipeline.py:158 IR_VERSION = "section-ir-0.13". The stale "0.12" label is committed verbatim into schemas/relation-pass-output.schema.json:4. I also verified the string actually ships to the model: run_relation_pass (section_pipeline.py:3674) loads the committed JSON via load_relation_pass_schema, then _augment_prompt_for_json_object (line 3676) -> schema_to_prompt_spec, which at lines 662/672-673 extracts the top-level description and appends it to the prompt for json_object-mode models (DeepSeek, the baked-in default per memory). So the relation pass genuinely conveys a contradictory version label to the model within the same 0.13 release. Tried to refute via tests: tests/test_schema_generator_descriptions.py::test_stage_schemas_byte_stable (lines 126-135) only pins generator output == committed JSON bytes; both sides carry the same stale "0.12" string, so the test passes and does NOT assert the label is 0.13 — it does not cover/catch this drift. No test asserts the version label is correct; the other version-string mentions in tests are docstrings/help-text. I ran the byte-stability test (unittest) and it passes, confirming generator and committed schema are currently in sync on the stale string (the generator has not been pre-fixed). IMPACT IS LIMITED: as the finding itself states, no version gate parses these description strings (ACCEPTED_IR_VERSIONS operates on IR output, not schema prose), so this is a non-functional contract-label inconsistency, not a parsing/correctness bug. It is real and actionable (wrong/contradictory version label shipped to the model and into the committed schema) but cosmetic.

</details>

---

### 21. Stage-B/Stage-C relation enums and the salience enum are hardcoded literals, not derived from the authoritative runtime vocab — silent strict-mode rejection on drift

- **位置**：`tools/generate_section_schemas.py:104-105, 112-115, 103`
- **类别**：contract-mismatch ｜ **子系统**：schema-generator ｜ **复核置信度**：high

**问题**：Every classificatory enum the generator emits (node_role, method_role, finding_role, method_kind, comparison_direction, finding_polarity, score_value_kind, measure_objective_class, measure_table_role) is imported from section_pipeline and routed through ordered_enum(), which appends `sorted(values - set(preferred))` so any vocab member missing from the order hint is still emitted — it self-heals against drift. The relation vocabularies and salience do NOT get this treatment: STAGE_B_RELATION_ORDER (L104-105) and STAGE_C_RELATIONS_BY_SECTION (L112-115) are frozen literal lists used RAW as the schema enum (relation_pass_schema L652 uses STAGE_B_RELATION_ORDER directly; relations_schema L471 uses the per-section list directly), and SALIENCE_ORDER (L103) is fed raw to inline_enum_schema in node_census_schema. The generator does not even import the authoritative sets STAGE_B_RELATIONS / STAGE_C_RELATIONS / SALIENCE_LEVELS from section_pipeline, so nothing ties these enums to the runtime vocabulary. Confirmed by simulation: adding a relation to section_pipeline.STAGE_B_RELATIONS leaves the generated relation-pass enum unchanged, so a strict-mode (response_format) decode would reject that valid edge = data loss. The byte-stability test (tests/test_schema_generator_descriptions.py GeneratorByteStabilityTests) cannot catch this — it only compares generator output to the committed bytes, not against section_pipeline.STAGE_B_RELATIONS. co_contribution was added to STAGE_B_RELATIONS in FG-7; the next such addition would silently desync.

**证据**：`L104-105: `STAGE_B_RELATION_ORDER = ["part_of", "builds_on", "uses", "assumes", "co_contribution", "compares_to", "evaluates"]` (literal); L652 `"enum": STAGE_B_RELATION_ORDER`. Import block (L29-41) imports the role/kind enums but NOT STAGE_B_RELATIONS / STAGE_C_RELATIONS / SALIENCE_LEVELS. Simulation: after `STAGE_B_RELATIONS |= {'refutes'}`, generated relation-pass enum still = ['part_of','builds_on','uses','assumes','co_contribution','compares_to','evaluates'] (no 'refutes').`

**建议修复**：Import STAGE_B_RELATIONS, STAGE_C_RELATIONS and SALIENCE_LEVELS from section_pipeline and validate the hardcoded order lists are a superset/subset of them (e.g. route through an ordered_enum-style helper that appends `sorted(values - preferred)`), or assert set-equality at generation time so a mismatch raises instead of silently producing a wrong enum. Add a test asserting set(STAGE_B_RELATION_ORDER) == STAGE_B_RELATIONS, the STAGE_C union == STAGE_C_RELATIONS, and set(SALIENCE_ORDER) == SALIENCE_LEVELS.

<details><summary>对抗复核结论</summary>

Verified every mechanical claim by reading the code and reproducing the simulation. (1) The relation/salience schema enums are hardcoded literals: tools/generate_section_schemas.py L103 `SALIENCE_ORDER = ["must", "should"]`, L104-105 `STAGE_B_RELATION_ORDER = ["part_of","builds_on","uses","assumes","co_contribution","compares_to","evaluates"]`, L112-115 `STAGE_C_RELATIONS_BY_SECTION`. (2) These literals are used RAW as schema enums: L652 `"enum": STAGE_B_RELATION_ORDER` in relation_pass_schema, L470 `"enum": allowed` (=STAGE_C_RELATIONS_BY_SECTION[section_type]) in relations_schema, L617-618 `inline_enum_schema(SALIENCE_ORDER, ...)` in the census node schema. (3) The import block L29-41 does NOT import STAGE_B_RELATIONS / STAGE_C_RELATIONS / SALIENCE_LEVELS — confirmed by reading lines 29-41. (4) Asymmetry confirmed: role/kind enums route through ENUM_VALUES (L137-148, which hold live references to the authoritative sets, e.g. ENUM_VALUES['node_role'] IS sp.NODE_ROLES) → ordered_enum (L151-154) which appends `sorted(values - set(preferred))`, so an in-place add to NODE_ROLES self-heals (reproduced: in-place add became visible). The relation/salience enums have no such tie. (5) Drift reproduced: after `STAGE_B_RELATIONS |= {'refutes'}`, the regenerated relation-pass enum still lacks 'refutes'. The authoritative sets do exist in section_pipeline.py (L173 SALIENCE_LEVELS, L413-414 STAGE_B_RELATIONS, L415 STAGE_C_RELATIONS) and are currently in sync with the generator literals (verified set-equality True for all three). (6) Test gap confirmed: GeneratorByteStabilityTests (tests/test_schema_generator_descriptions.py L107-135) only compares generator output to committed JSON bytes, never to the authoritative sets; the only set-equality assertion (L78) checks MEASURE_TABLE_ROLES against literals. A repo-wide grep found no test asserting set(STAGE_B_RELATION_ORDER)==STAGE_B_RELATIONS et al.

So the described desync genuinely occurs and no guard catches it. However I down-correct severity from medium to low for three grounded reasons: (a) it is a LATENT maintenance-time hazard, not a live bug — all three vocabs are currently in sync; it only bites a future vocab extension. (b) The "silent strict-mode rejection = data loss" harm applies only to the json_schema (Gemini/OpenAI proxy) path where the schema strictly constrains decoding (L723 strict:True). The CURRENT default model is DeepSeek/json_object (L579, per project memory), where the schema is only prompt guidance via schema_to_prompt_spec (L597-601) and is NOT a decode constraint — a missing enum value would fail to advertise the relation in the prompt but would not reject it, and the runtime gate for relations is RELATION_MATRIX (L1315, L4806), not these sets, which would still accept the edge. (c) Adding a new relation already requires editing RELATION_MATRIX, so a maintainer is in the vicinity; the fix (import the sets + a one-line set-equality assert/test) is cheap and the right call, but the real-world blast radius is small. Real, worth fixing, low severity.

</details>

---

### 22. Generator docstring overclaims coverage; two live structured-output schemas (metadata, references) are unowned and hand-maintained

- **位置**：`tools/generate_section_schemas.py:2-3, 667-682`
- **类别**：dead-code ｜ **子系统**：schema-generator ｜ **复核置信度**：high

**问题**：The module docstring states it generates "every structured-output schema from the controlled vocabularies in section_pipeline.py" (line 3). main() only writes 5 files: the three section schemas plus node-census and relation-pass (L669-681). But schemas/metadata-output.schema.json and schemas/references-output.schema.json are BOTH loaded at runtime as strict structured-output contracts (section_pipeline.py:3730 build_response_format for metadata, :3838 for references), so the docstring's "every structured-output schema" claim is false — those two are hand-maintained outside the generator. The risk: references-output.schema.json's roles enum [builds_on, uses, compares_to, background] mirrors section_pipeline.REFERENCE_EDGE_ROLES + background, but nothing generates or cross-checks it, so it can drift from REFERENCE_EDGE_ROLES silently (the same drift class as finding #2 but with zero machinery at all). Not currently broken (verified the enums match today), but it is an unguarded contract.

**证据**：`Docstring L3: "generates every structured-output schema from the controlled vocabularies". main() (L669-682) writes only section-{problem,method,evidence}, node-census-output, relation-pass-output. section_pipeline.py:30-31 define METADATA_SCHEMA_PATH / REFERENCES_SCHEMA_PATH; :3730 and :3838 load them as response_format contracts. references roles enum == REFERENCE_EDGE_ROLES|{'background'} (verified) but no generator/test pins it.`

**建议修复**：Either reword the docstring to scope it to the 5 schemas it actually owns, or extend the generator to also emit metadata-output and references-output (deriving the references roles enum from REFERENCE_EDGE_ROLES). At minimum add a test asserting the committed references roles enum equals sorted(REFERENCE_EDGE_ROLES)|{'background'}.

<details><summary>对抗复核结论</summary>

All factual claims verified against the code:

1. Docstring overclaim is real. tools/generate_section_schemas.py:5-6 states the script "generates every structured-output schema from the controlled vocabularies in section_pipeline.py." But main() (L667-682) writes exactly 5 files: section-{problem,method,evidence}, node-census-output, relation-pass-output. The directory has 7 schemas; metadata-output.schema.json and references-output.schema.json are not produced.

2. Both unowned files ARE live structured-output contracts. section_pipeline.py:30-31 define METADATA_SCHEMA_PATH/REFERENCES_SCHEMA_PATH; :3730 loads metadata and :826 loads references, each passed to build_response_format (defined :712-723), which returns a strict json_schema (strict:True) or a prompt-conveyed json_object contract — confirming both are "structured-output schemas" the "every" claim should cover but does not.

3. Drift risk on references roles is real and unguarded. section_pipeline.py:435 REFERENCE_EDGE_ROLES = frozenset({"builds_on","uses","compares_to"}); references-output.schema.json:45 roles enum = ["builds_on","uses","compares_to","background"], i.e. REFERENCE_EDGE_ROLES | {"background"}. They match today, but nothing pins this. grep REFERENCE_EDGE_ROLES over tests/ returns nothing. The sole generator test (tests/test_schema_generator_descriptions.py) only byte-checks the 5 owned schemas: GeneratorByteStabilityTests covers section schemas (L117-124) and the two stage schemas (L126-135), with no coverage of metadata-output or references-output. So no test covers the gap.

Refutation attempts failed: the "controlled vocabularies" scoping does not save the docstring because the references enum literally derives from REFERENCE_EDGE_ROLES yet is unowned; no passing test guards the enum; the enums genuinely match so it is not currently broken.

Caveats lowering impact, not reality: the finding's own category label "dead-code" is a misnomer (this is a documentation-accuracy + unguarded-contract issue, not dead code), and the finding concedes the contract is not currently broken — the harm is latent drift on a code-generation utility whose stated purpose is to prevent hand-maintenance drift. That makes it genuinely real but minor.

</details>

---

### 23. Empty-body marker silently dropped: marker text lost when two markers are adjacent or a marker is trailing (never-worse-than-raw violation)

- **位置**：`tools/reference_formatter.py:267-272`
- **类别**：data-loss ｜ **子系统**：ref-formatter ｜ **复核置信度**：high

**问题**：In `_split_numbered`, each kept boundary contributes an entry only when its body is non-empty (`if body:`). When two markers are adjacent (e.g. OCR `[1][2] B. Two. ...`), the first marker's body slice `text[m.end():nxt]` is empty, so the whole `(marker, body)` pair is skipped and the marker text `[1]` is never rendered. The same happens for a trailing marker with nothing after it (`...In V, 2021.[4]` at end of blob): `[4]`'s body is empty, so `[4]` is dropped. This violates the module's governing 'never render worse than raw' invariant (docstring lines 12-15: returns are supposed to be lossless under-splits, and the marker IS input text). I reproduced both: `[1][2] B. Two. ...[3]...[4]...` renders only `[2][3][4]` (squashed-whitespace fidelity check fails, `[1]` absent); `...2021.[4]` renders only `[1][2][3]` ([4] absent). The fidelity test suite never exercises adjacent or trailing-empty markers, so the regression is uncovered.

**证据**：`for i, m in enumerate(boundaries):\n    nxt = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)\n    marker = text[m.start():m.end()].strip()\n    body = _collapse(text[m.end():nxt])\n    if body:\n        entries.append((marker, body))   # marker dropped when body == ""`

**建议修复**：Do not discard the marker when the body is empty. Either always append the marker (with an empty body) — `entries.append((marker, body))` unconditionally, then let the renderer show a bare marker — or, better, fold an empty-bodied marker into the adjacent (next) entry's marker/body so no character is lost. Minimal fix: replace `if body: entries.append((marker, body))` with logic that, when `body` is empty, prepends `marker` to the following entry's marker or keeps `(marker, "")`. Add adjacent-marker (`[1][2]...`) and trailing-empty-marker (`...[N]`) fidelity tests.

<details><summary>对抗复核结论</summary>

CONFIRMED in code and reproduced. In `_split_numbered` (tools/reference_formatter.py:267-272) the loop only appends `(marker, body)` when `if body:` is truthy; `body = _collapse(text[m.end():nxt])`. When two markers are adjacent (`[1][2] ...`) the first marker's body slice is empty, and when a marker is trailing with nothing after it (`...2021.[4]`) its body is also empty, so the entire `(marker, body)` pair — including the marker text — is skipped and never reaches `entries`. The identical defect exists in `_split_bracketed_keys` at lines 323-328.\n\nI reproduced both empirically against the actual module:\n- Adjacent `[1][2] B. Two. ... [3]... [4]...` → entries markers = ['[2]','[3]','[4]'], `[1]` absent, `assertCoversInput`-style squash check returns covers=False (expected stream contains `[1][2]`, joined contains only `[2]`).\n- Trailing `...2021.[4]` → entries markers = ['[1]','[2]','[3]'], `[4]` absent, covers=False.\n- bracket-key trailing `...2019.[Lee20]` → `[Lee20]` absent, covers=False.\n\nThe renderer (tools/render_extraction.py:1066-1072) iterates exactly `formatted.entries` to build the `<ul>`, so a dropped marker is dropped from the rendered HTML — it does not fall back to the verbatim `<pre>` (the split is non-None and passes the sanity/content/undersplit gates, as my reproduction shows). This violates the module's explicit, tested losslessness invariant (docstring lines 12-15 'never render worse than raw'; the FidelityMixin.assertCoversInput property in tests/test_reference_formatter.py asserts every successful split COVERS its input modulo whitespace).\n\nTest-gap claim verified: all six `][` occurrences in the test file are `fmt.entries[0][1]` index expressions, not adjacent markers; no fixture exercises an adjacent (`[1][2]`) or trailing bare (`...[N]`) marker, so the regression is genuinely uncovered. A fidelity fixture for either case would fail.\n\nSeverity correction: the finding labels this 'high'. That overstates impact. By explicit design this module is display-only/cosmetic and post-LLM — the extraction/graph path and cite-key reconciliation always consume the raw `references_blob`, never this output (docstring lines 4-15; render comment line 1065). The lost text is a single bracketed citation marker (`[1]`/`[4]`/`[Lee20]`), never a reference body, on a non-essential render artifact. It is a real, reproducible violation of the module's own invariant with a trivial fix, but the consequence is cosmetic, so low is the honest severity.

</details>

---

### 24. Bracket-key splitter has the identical empty-body marker-drop loss

- **位置**：`tools/reference_formatter.py:323-328`
- **类别**：data-loss ｜ **子系统**：ref-formatter ｜ **复核置信度**：high

**问题**：`_split_bracketed_keys` repeats the exact `if body:` skip pattern of `_split_numbered`. A bracketed key whose body slice is empty — two adjacent keys `[Bar93][Vas17] ...` (the `< _MIN_BODY` proximity skip only drops the *second* close key from boundaries, but if the gap is exactly 0 the first key still becomes a kept boundary with empty body), or a trailing key at the very end of the blob — loses its marker text from the render, again breaking the never-worse-than-raw invariant. Same root cause and same uncovered-by-tests status as the numbered case.

**证据**：`marker = text[m.start():m.end()].strip()\nbody = _collapse(text[m.end():nxt])\nif body:\n    entries.append((marker, body))`

**建议修复**：Apply the same fix as the numbered splitter: never drop the marker when its body is empty — emit `(marker, body)` regardless, or fold the marker into the next entry — so the bracketed-key characters are always preserved in the rendered list.

<details><summary>对抗复核结论</summary>

CONFIRMED REAL (with one sub-claim refuted). I read tools/reference_formatter.py:299-329 and the sibling _split_numbered (232-273), and reproduced both scenarios with the project's python3.10.

Core defect is real: in _split_bracketed_keys, lines 326-328:
  body = _collapse(text[m.end():nxt])
  if body:
      entries.append((marker, body))
When the LAST surviving boundary's body slice is empty (a trailing bare marker at the very end of the blob, e.g. "...[Dev19] J. Devlin... [Sun20]"), nxt = len(text), the collapsed body is empty, so `if body:` is False and the marker is dropped entirely. My repro: regime=bracket-key, 3 entries returned, COVERS INPUT: False — the trailing "[Sun20]" characters vanish. The renderer (tools/render_extraction.py:1066-1072) iterates formatted.entries and renders ONLY those as <li>; it does NOT fall back to the raw <pre> when entries is non-empty (line 1067 `if formatted and formatted.entries`), so the dropped marker genuinely never appears in the rendered HTML, violating the module's stated absolute "never render worse than raw" / losslessness invariant. The numbered splitter (lines 270-272) shares the identical pattern (I reproduced the same loss with a trailing "[4]"), so the "same root cause as the numbered case" claim is accurate. The FidelityMixin.assertCoversInput property test in tests/test_reference_formatter.py would fail on such a fixture, and no existing test covers a trailing-empty-marker (the only "trailing" test at line 138 is a benign fold-into-prior-body, different mechanism) — genuine test gap.

REFUTED sub-claim: the description's first scenario (adjacent keys "[Bar93][Vas17]" producing an empty body for [Bar93]) is WRONG. The proximity guard at line 311 skips [Vas17] (gap 0 < _MIN_BODY=15), so [Bar93]'s body extends to the NEXT surviving boundary and absorbs "[Vas17] A. Vaswani..." — body is non-empty and COVERS INPUT: True (verified). Only the trailing-empty-marker case loses text.

Severity correction high->low: this is render-only/display-only code; the module docstring and memory note both state errors cost only readability, never graph correctness (extraction + cite-key join always consume the raw blob). The lost data is a single trivial trailing marker token (e.g. "[4]", a few chars) while the full reference bodies are preserved, and the precondition (a bibliography blob ending on a bare marker with zero following text) is pathological — the 765-paper corpus survey found 0 such losses (over-split, the opposite mode, was the only observed issue at 0.16%). The defect is technically real and breaks the stated invariant, but its real-world impact is cosmetic and vanishingly rare.

</details>

---

## ⚪ 已反驳（不作为缺陷）

对抗复核阶段反驳了以下 finding（风格偏好 / 已在别处处理 / 已被测试覆盖 / 无法复现路径）：

- **Finding 'incoming supports' validation is unreachable: every Finding lives in the evidence section, and evidence Findings are explicitly exempted** (`section_pipeline.py:4981-4987`, schema-contracts) — REFUTED on three grounds, all verified against code and tests.

1) The check is reachable and tested, NOT dead code. section_pipeline.py:4981-4987 fires for a Finding registered under a non-evidence section: unit_sections is populated only from section units (4912-4918) gated on a string section_type, so a Finding appended to the problem section gets unit_sections.get(uid)=="problem" != "evidence", and if it has no incoming supports edge, line 4987 appends "Finding {uid} lacks an incoming argumentative (supports) relation". tests/test_section_pipeline.py:1265-1272 (test_finding_without_supports_outside_evidence_flagged) does exactly this — appends m_finding("fnd:stray") to the problem section and asserts any(i contains "fnd:stray" AND "argumentative"). grep shows the word "argumentative" appears in only one validator message in the entire module (line 4987), and the per-section type check (4941-4945) emits a different message lacking "argumentative", so the test pins the 4987 branch specifically. The finding's claim "No test exercises 'lacks an incoming argumentative'" is factually false. I ran both tests via unittest: PASS.

2) The exemption of evidence Findings is intentional and load-bearing, not an inverted/wrong gate. Under blob-primary-evidence (the DEFAULT), assemble_extraction migrates Measure--supports-->Finding edges into finding_ids mounts and removes them from relations. test_migrates_measure_finding_edges_to_finding_ids (lines 939-960) asserts assertNotIn(("mea:abl","supports","fnd:abl"), triples) AND validate_section_ir(ext)==[]. Thus on the default path evidence Findings legitimately have NO incoming supports edge. The finding's proposed "fix" (drop the evidence exemption / require supports on evidence Findings) would make this test and every default extraction fail validation — i.e. the fix is the actual regression. I ran this test: PASS.

3) The finding itself concedes the per-section type check independently rejects misplaced Findings, but that check yields a distinct message; the argumentative check is a deliberate, narrowed safety net for non-evidence Findings, which is reachable, correct, and covered.
- **normalize_census_nodes duplicate-id suffixing can steal a later node's legitimately-distinct id, silently relabeling it** (`section_pipeline.py:1516-1531`, census-stageA) — The mechanical relabeling the finding describes is real and I reproduced it exactly (empirically and by tracing section_pipeline.py:1516-1531): for nodes [mth:x (A), mth:x (B), mth:x_2 (C)] the dedup loop iterates in input order, B is renamed to mth:x_2 (because used_ids only holds A's id at that point, not C's later original id), and C is then pushed to mth:x_2_2. Uniqueness IS preserved (verified: unique==True, no collision, no dropped node). The collision check at line 1527 (`while new_id in used_ids`) only compares against ids accumulated so far, as quoted.\n\nHowever, the finding's load-bearing consequence claim — \"any downstream reference to the original mth:x_2 now resolves to B rather than C\" — is REFUTED by the actual pipeline. The relation and content stages do NOT carry forward pre-normalization census ids. In both code paths (production/worker.py:134-148 and section_pipeline.py:4491-4511) the raw census (census_result / raw_census) is normalized once, the raw object is then discarded, and only the normalized census flows into build_node_registry (worker.py:146 / section_pipeline.py:4497). build_node_registry (section_pipeline.py:1681-1693) emits each node's POST-normalization node_id alongside its own name/gloss/role. The LLM relation/content passes are re-prompted with this normalized registry, so they only ever see B's id (mth:x_2) and C's id (mth:x_2_2) as distinct, unambiguous, correctly-labeled entries. There is no stale reference to an \"original mth:x_2\" anywhere to be misrouted; the model attaches edges to the ids it is shown. The renamed ids ARE the canonical ids; nothing pre-existing points at them.\n\nSupporting evidence the design is intentional: _sanitize_unit_ids (section_pipeline.py:2111-2139) — which runs LATER at assembly when references DO exist — deliberately seeds its `used` set up front AND remaps every reference, the exact pattern the finding proposes. The developers applied it precisely where references exist and omitted it in normalize_census_nodes where (Stage A) no downstream references exist yet. The finding also self-admits the trigger requires malformed model input (duplicate ids + a pre-existing _n).\n\nNet: the relabel is cosmetically non-minimal but lossless and harmless — uniqueness holds, no node lost, no broken/misrouted reference. There is a genuine test gap (test_normalize_dedups_node_ids and test_normalize_sanitized_slugs_stay_unique at tests/test_section_pipeline.py:256-262/245-254 do not cover the suffix-steals-a-distinct-later-id case), but a test gap for behavior that yields a correct result is not a reportable defect. Not a real, actionable bug.
- **_normalize_cite_key fallback paths retain punctuation, so distinct surface forms of the same year-less key fail to join (and disagree with the author-year path's stripping)** (`section_pipeline.py:3882-3892`, blob-references) — The code asymmetry is real and accurately quoted: at section_pipeline.py:3882/3890/3892 the fallback normalizes via `re.sub(r"[\[\]\s]+", "", stripped).lower()` (strips only brackets/whitespace), while the author-year path at line 3891 strips all non-alphanumerics via `re.sub(r"[^a-z0-9]", "", authors[0].lower())`. I reproduced the claimed inequalities: `_normalize_cite_key('VGG.')=='vgg.'` != `_normalize_cite_key('VGG')=='vgg'`, and `_normalize_cite_key('Devlin et al.')=='devlinetal.'` != `_normalize_cite_key('Devlin et al')=='devlinetal'`. So the construct exists.

But the defect does not genuinely occur or matter, so is_real=false. I probed all real production corpora (243 papers, 3968 census cite_keys + 7059 reference ids = 11,027 markers). Categorizing each by which branch the normalizer takes: census = 2757 numeric + 1211 author-year + 0 year-less-fallback; refs = 4342 numeric + 2717 author-year + 0 year-less-fallback. There are ZERO year-less fallback keys in the entire corpus, and ZERO keys (census or reference) that normalize to a value containing any residual punctuation. The hypothesized bare named-architecture keys (VGG/AlexNet/BERT/GNMT/ResNet) never appear year-less — they are always cited as numbered or author-year refs. Thus the punctuation-retaining fallback branch the finding indicts is effectively dead on the real workload; the asymmetry cannot lose a join because no real key reaches it carrying punctuation.

The failure also requires a doubly-rare condition: two surface forms of the same reference must BOTH be year-less AND differ only by punctuation. Additionally the finding's 'disagrees with the author-year path' framing is misleading — each key is routed through exactly one branch, so a single key never yields two results; and the only plausible cross-branch case ('Devlin et al.' -> 'devlinetal.' vs 'Devlin et al., 2018' -> 'devlin2018') is NOT fixed by the proposed fix either (stems differ regardless). The existing test test_normalize_cite_key_forms covers the year-less path only via punctuation-free 'AlexNet'->'alexnet', so there is a test gap, but the gap covers a code path with no demonstrable real-data impact. This is a true-but-latent cosmetic inconsistency with no grounded data-loss path.
- **save_json uses a fixed .tmp sibling name; unused tempfile import signals a lost uniqueness guarantee** (`production/outputs.py:32-37`, orchestration) — I read production/outputs.py:32-37 and traced every call site of save_json. The reported defect (a concurrent same-target write race causing silent data loss) does NOT occur on any real code path, and the finding itself concedes this: "This is safe for the current call sites because every concurrent write within a paper targets a distinct filename."

Verification of the concurrency model:
- production/runner.py:101-113: each paper runs in its own coroutine keyed by a unique paper_id, so each writes into its own paper_dir (production/outputs.py:14 `paper_dir = output_dir / paper_id`). No two coroutines share a paper_dir.
- production/worker.py:140-142,153-156,185-193,214: all paper-level save_json calls (01_census, 02_metadata, 03_references, 04_relations, 06_extraction, 07_validation, status.json) execute sequentially within one process_paper coroutine — never concurrently with each other.
- The only concurrent saves are the three content sections via asyncio.gather (worker.py:424-431) over SECTION_ORDER = ["problem","method","evidence"] (section_pipeline.py:110). These write 05_sections/{section_type}.json with distinct stems, so they never collide on the .tmp name.
- I also verified with_suffix produces distinct .tmp names for every distinct target (01_census.tmp, 02_metadata.tmp, etc.), so there is no cross-target .tmp collision either. Path.rename within the same directory is an atomic os.rename, so the atomicity guarantee the function claims actually holds.

The reported race is therefore a pure hypothetical ("any future reuse"), which the task instructions explicitly exclude ("hypotheticals you cannot ground in code").

The only factually-true sub-claims are minor and not the reported defect: (1) `import tempfile` at line 6 is genuinely unused (confirmed via grep — only the import line matches), but that is a dead-import lint nit, not a concurrency/data-loss bug, and the narrative that it "signals a lost uniqueness guarantee" is unverifiable speculation about prior history; (2) a failed write_text leaves an orphan .tmp (no try/finally), but this causes no data loss or wrong output — the paper is marked failed and a retry simply overwrites the .tmp; it is cosmetic. Neither rises to a real, actionable correctness defect. The reported severity (low, concurrency, data loss) does not materialize.

---

## 优先级建议

- **立即修**：#1（静默整篇失败——正好打在 FG-5 针对的 analysis/finding-root 论文上，既是正确性也是召回回归）、#3（损坏面向 agent 的数值字段）。
- **尽快修**：#2（score-row setup_id 静默丢失）、#4（retrofit 把已有 0.10 语料翻成 invalid）。
- **按威胁模型评估**：HTML 注入（若渲染产物会对外分发/服务，而非仅本地可信输入查看）。
- **低优先级**：可作为一次批量清扫（prettifier never-worse-than-raw、schema-generator 漂移、遥测/计数核对）。
