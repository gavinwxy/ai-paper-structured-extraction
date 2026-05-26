# 修改计划：planning-stage 重设计 → section-ir-0.7（nodes → edges → content）

- **状态**：✅ 已实施（#1–#7 全部完成），单篇 live smoke 通过（validation PASSED，part_of 链/evaluates/measured_on 复活，evidence 合并生效）；37 个单测通过。**#8（50 篇 before/after 召回 A/B）未跑——用户 2026-05-26 暂停**。尚未提交。分支 `planning-stage-redesign`。
- **拟定日期**：2026-05-26
- **完整契约规格**：见 `docs/section-ir-0.7-redesign.md`（IR 形态、关系矩阵、三阶段契约、装配/校验细则）。**本文件只管"怎么改、改哪里、什么顺序"**，规格细节不重复，动手前先读那份 doc。
- **范围**：把 0.6 的「planning + 并行 section 抽取」两阶段，重写为 **三阶段** `node census → relation pass → content fill`，并把 experiment+analysis 合并为 `evidence` 段、把所有论证/结构边提升为**顶层全局 `relations[]`**。跨 `section_pipeline.py`(2628) + `tools/generate_section_schemas.py`(438) + `tests/test_section_pipeline.py`(1984) + prompts + `tools/render_extraction.py`(892)。
- **触发背景**：0.6 三个痛点同源——「信息不全时被迫承诺」：① planner 边枚举边内联声明 relations（前向引用）；② link 全 section-local，validator 对跨节 link 硬失败（`section_pipeline.py:2498`），导致 method 分段切断 `part_of`、消融 Metric `subject_id` 错挂，需 `_reconcile_*` 拐杖；③ experiment/analysis 边界按表格行裁决，却由两个互相看不见的并行调用各跑一遍同一张表。

## 决策基线（已与用户确认）

- **首要指标 = 原始召回**：节点数 + 关系数（同模型 before/after）。
- **IR 形态 = Option B**：保留 `context/claim/method/evidence` 四个 section 做组织/渲染，但 **links 提升为顶层全局 `relations[]`**（不再 section-local）。不走"完全扁平 node-centric"（避免重写 renderer 全量）。
- **合并段命名 = `evidence`**（experiment + analysis 合并）。
- **节点普查 = 保持 salience 纪律**：只抓有论证承载力的节点，baseline 仍不建模；召回提升来自"该抓的都抓 + 关系 pass 全局视野 + 合并"，不是放水。
- **（我替用户定的、利于召回的默认，可推翻）**：
  - 字段边全部升格为全局边：`subject_id→evaluates`、`evaluated_on→measured_on`（复活死边）、`target_ids→about`、`part_of/components→part_of`、`supports/compares_to` 同名。**唯一保留为字段**的是 `Metric.context_ids`（指向本段 Condition 的局部 scoping）。
  - **删除三个 reconcile 拐杖**：`_reconcile_method_components` / `_reconcile_metric_subjects` / `_reconcile_analysis_metric_subjects`——stage B 全局视野直接顶替，memory 两痛点结构性消失。
  - content 阶段**允许补漏** census 漏掉的节点（就地补单元 + 连边），利于召回。
  - 关系名新引入 `about`（Claim→节点）与 `measured_on`（Metric→数据集 Entity）——若要改名在此拦。

## 本 session 已完成（勿重复）

- ✅ `docs/section-ir-0.7-redesign.md`：完整规格蓝本。
- ✅ `tools/count_extraction.py`：节点/关系计数器（**注意**：现按 0.6 形态数 section-local `links` + 字段边；0.7 落地后需改为数顶层 `relations[]`）。
- ✅ 任务列表 #1–#8（#1 写 doc 已完成；#2–#8 待执行，见下「执行顺序」）。
- ⛔ 代码、schema、prompts、测试、renderer **均未动**。

## 基线度量（before，零成本，已测）

`tools/count_extraction.py` 跑现有磁盘批次（同 50 篇 NeurIPS）：

| 批次（模型固定） | 节点/篇 | 关系/篇（links+字段边） |
|---|---|---|
| gemini-3-flash-nothinking **常规** (n=47) | **23.8** | **19.3** |
| gemini-3-flash-nothinking **decoupled** (n=48) | 21.9 | 17.6 |
| deepseek-v4-flash (n=34) | 33.8 | 33.9 |

三个发现（执行/度量时须记住）：
1. 之前那次未提交的 "decoupled" 跑分**更低**（节点 −8%、关系 −9%）——解耦非自动胜利，执行方式定成败。
2. **模型是混淆变量**（deepseek 比 gemini +42% 节点 / +76% 关系）——before/after **必须锁同一模型**（gemini-3-flash-nothinking）。
3. `evaluated_on` 在所有批次**恒为 0**（死边）；关系由字段边主导（target_ids 337 / subject_id 184 / context_ids 141），显式 link 仅 ~5/篇。
4. 护栏：原始计数会奖励过度切分（gemini 切碎 method → Method 节点多但 part_of 断）。after 须同时报 validity 通过率 + 碎片化/去重率，区分真召回与灌水。

## 关键实现事实（动手前须知；行号为撰写时快照，执行以实际为准）

- **Schema 是生成物**：源头 = `section_pipeline.py` 常量 + `tools/generate_section_schemas.py`。改常量后跑 `python tools/generate_section_schemas.py` 重生成，**不要手改** `schemas/*.json`。
- **`section_pipeline.py` 关键坐标**：
  - 常量区 :27–207 —— `SECTION_SCHEMA_FILES`:27、`SECTION_TYPES`:43、`PLANNED/PLANLESS`:44-45、`SECTION_ORDER`:46、`SECTION_ALLOWED_UNIT_TYPES`:47、`SECTION_PREFERRED_ANCHOR_TYPE`:58、`PLAN_RELATIONS_BY_SECTION`:65、`PLAN_ITEM_PREFIXES_BY_SECTION`:69、`TYPED_ARRAY_KEYS`:73、`LINK_MATRIX`:147、`UNIT_ID_PREFIX_BY_TYPE`:153、`ALLOWED_FIELDS_BY_TYPE`:162、`ALLOWED_SECTION_FIELDS`:206、`REFERENCE_LIST_FIELDS`:207。
  - 装配 `assemble_extraction`:1554（repair 链 :1574–1585，已持有 `plan`）。reconciles：`_reconcile_method_components`:528、`_reconcile_metric_subjects`:798、`_reconcile_analysis_metric_subjects`:882、`_drop_invalid_links`:677、`_repair_section_anchors`:727、`_dedup_entities`:389、`_dedup_unit_ids`:462、`_normalize_provenance_markers`:634、`_reconcile_covers_entries`:767、`_flatten_typed_arrays`:279。
  - 规划/抽取：`run_planning`:1693、`normalize_planning_item_ids`:1155、`build_planless_stubs`:1263、`expand_section_plans`:1303、`build_id_registry`:1346、`render_section_user_prompt`:1425、`extract_single_section_sync`:1817、`run_parallel_extraction_sync`:1883、`run_pipeline`:1965。
  - 校验：`validate_section_ir`:2336、`_validate_unit_fields`:2121（Metric 分支 :2214–2295、context_ids 极性翻转 :2241–2270）、`_validate_link`:2298、**section-local 硬失败 :2498–2502**、Claim 入边检查 :2505–2518、`_validate_plan_trace`:2553。
- **`tools/generate_section_schemas.py` 坐标**：`SECTION_TYPED_ARRAYS`:33、`ENTITY_CLASSES_BY_SECTION`:41、`OPTIONAL_FIELDS_BY_TYPE`:46、`metric_context_ids_schema`:132、`typed_unit_schemas`:278（Metric props :320）、`LINK_RELATION_HINTS`:354、`links_schema`:363、`section_schema`:384、`main`:428。
- **批量跑批入口**：`production/`（`cli.py`/`runner.py`/`worker.py`/`outputs.py`）。磁盘批次产物即出自此。0.7 改变了顶层产物形态（新增 `relations[]`），**须核查 `production/worker.py`、`production/outputs.py` 是否依赖旧形态**（如 `extraction["sections"][*]["links"]`）。
- **测试环境**：`.env` 的 `API_KEY`、`MODEL`(默认 `gemini-3-flash-preview`)、`BASE_URL`(默认 `http://35.220.164.252:3888/v1`，备用 `http://34.13.73.248:3888/v1`)。

---

## 改动清单（按任务）

### #2 · 词表/常量 + schema 生成器 [P0，源头]

| 文件 | 位置 | 改动 |
|---|---|---|
| `section_pipeline.py` | `SECTION_TYPES`:43、`SECTION_ORDER`:46 | → `{context, claim, method, evidence}`；顺序 `[context, claim, method, evidence]` |
| `section_pipeline.py` | `SECTION_ALLOWED_UNIT_TYPES`:47 | `evidence: {Metric, Condition, Claim, Entity}`；删 experiment/analysis |
| `section_pipeline.py` | `SECTION_SCHEMA_FILES`:27 | 加 `evidence`，删 experiment/analysis；新增 `node-census`/`relation-pass` schema 路径常量 |
| `section_pipeline.py` | `LINK_MATRIX`:147 → 新 `RELATION_MATRIX` | 全局矩阵（见 doc）：`part_of`{M,E}→{M,E}、`compares_to`{M,E,Met}↔同、`evaluates` Met→M、`measured_on` Met→E(dataset/benchmark)、`about` Claim→{M,E,Met}、`supports`{Met,Claim}→Claim |
| `section_pipeline.py` | `ALLOWED_FIELDS_BY_TYPE`:162 | `Metric` 删 `subject_id`/`evaluated_on`；`Claim` 删 `target_ids`；`Method` 删 `components`。`Metric` 留 `context_ids` |
| `section_pipeline.py` | `ALLOWED_SECTION_FIELDS`:206 | section 去掉 `links`（content section 改带 `relations`，见 #3） |
| `section_pipeline.py` | `REFERENCE_LIST_FIELDS`:207、`UNIT_ID_PREFIX_BY_TYPE`:153 | 同步（被删字段移出） |
| `tools/generate_section_schemas.py` | `SECTION_TYPED_ARRAYS`:33 | `{context:[contexts], claim:[claims], method:[methods], evidence:[metrics, conditions, claims, entities]}` |
| `tools/generate_section_schemas.py` | Metric props :320、`OPTIONAL_FIELDS_BY_TYPE`:46、`metric_context_ids_schema`:132 | Metric 删 `subject_id`/`evaluated_on`；删 experiment/analysis 的 context_ids 极性翻转（evidence 内 deployable 指标可有 context_ids、消融指标可空，故不设统一 minItems） |
| `tools/generate_section_schemas.py` | `links_schema`:363 → content section 的 `relations` 字段；新增 census/relation schema builder + `main`:428 输出 | content section schema 用 `relations[]`（claim 侧 `about`/`supports`，可空）替代 `links`；新增并输出 `node-census-output.schema.json`、`relation-pass-output.schema.json` |
| 运行 | — | `python tools/generate_section_schemas.py` 重生成全部 schema |

### #3 · 三段式 pipeline [P0]

| 文件 | 位置 | 改动 |
|---|---|---|
| `section_pipeline.py` | 新 `run_node_census`（仿 `run_planning`:1693） | 输出 `{spine_summary, nodes[]}`；用 node-census schema。沿用 `normalize_planning_item_ids` 的 root 回填/降级逻辑保证唯一 `is_root` |
| `section_pipeline.py` | 新 `run_relation_pass` | 入参：全文 + `nodes[]`；输出 `{relations[]}`（仅实体↔实体边：part_of/compares_to/evaluates/measured_on） |
| `section_pipeline.py` | 改 `run_parallel_extraction_sync`:1883 → content fill | 按 `context/claim/method/evidence` 并行；每调用收全文(缓存)+相关节点子集+全局 relations+spine_summary+section module。`render_section_user_prompt`:1425 相应改造（注入 nodes/relations 取代 id_registry/section_plan） |
| `section_pipeline.py` | `assemble_extraction`:1554 | ① 收集 content 各 section 的 `relations` + stage B 的 relations → 顶层全局 `relations[]`；② 新 `_dedup_relations`(按 src,rel,dst)、`_drop_dangling_relations`(端点须解析到单元)、`_drop_invalid_relations`(全局矩阵，替 `_drop_invalid_links`)；③ **删** `_reconcile_method_components`/`_reconcile_metric_subjects`/`_reconcile_analysis_metric_subjects`；④ 留 `_dedup_*`/`_normalize_provenance_markers`/`_repair_section_anchors`/`_reconcile_covers_entries`/`_drop_empty_sections` |
| `section_pipeline.py` | `run_pipeline`:1965 | 编排：并行(census + metadata + references) → relation pass → content fill → reconcile_reference_units → assemble → validate。删 `build_planless_stubs`/`validate_plan`/`expand_section_plans` 的 planning 专用链路（或改造为 census 适配） |
| `section_pipeline.py` | `build_extraction_notes`:1507、`build_document_unit`:1487 | `ir_version`→`section-ir-0.7`；`input_mode`→`node_census_pipeline`；coverage 以 census `must` 节点为分母 |

### #4 · validator → 0.7 [P0]

| 文件 | 位置 | 改动 |
|---|---|---|
| `section_pipeline.py` | `validate_section_ir`:2336 | 顶层允许键加 `relations`；遍历顶层 `relations[]` 用 `RELATION_MATRIX` 校验（关系合法 + 端点解析到任意 section 的单元 + 类型配对），**删 section-local 硬失败 :2498–2502**；`SECTION_TYPES` 校验含 evidence |
| `section_pipeline.py` | `_validate_link`:2298 → `_validate_relation` | 改为全局；移除 section-local 约束 |
| `section_pipeline.py` | `_validate_unit_fields`:2121 Metric 分支 :2214 | 删 `subject_id`/`evaluated_on` 字段校验与 context_ids 极性翻转 :2241–2270；evidence Metric 的 context_ids（若有）须指向本段 Condition。软检查（记 `uncertain_assignments` 而非失败）：结果 Metric 无 `evaluates` 入边 |
| `section_pipeline.py` | Claim 入边 :2505–2518 | 非 `established_fact` 的 Claim 若不在 `{claim, evidence}` 段，需有 `supports` 入边（全局 relations 里找） |
| `section_pipeline.py` | `_validate_plan_trace`:2553 | 改造为对 census `nodes[]` 的 trace（must 节点须落地为单元，否则进 uncovered） |

### #5 · prompts [P0]

| 文件 | 改动 |
|---|---|
| 新 `prompts/section-extraction/node-census.md` | stage A：全文找全部 Method/Entity/Metric 节点，扁平输出，带 salience/is_root，**不连关系** |
| 新 `prompts/section-extraction/relation-pass.md` | stage B：拿全部节点，输出实体↔实体全局边（part_of/compares_to/evaluates/measured_on），强调"全局视野、可跨任意 section 连边" |
| 新 `prompts/section-extraction/section-modules/evidence.md` | 吸收 `experiment.md` + `analysis.md`：deployable(Metric scores)↔diagnostic(ablation Claim+supports) 一次裁决；按实验目的(主/消融/迁移)分段；Condition+context_ids 局部 scoping；claim 的 about/supports 进 relations |
| 改 `context.md`/`claim.md`/`method.md` | 适配"节点已由 census 给出、content 只填富字段"；claim 的 about/supports 写入 relations；method 去掉 components 字段表述（part_of 现为全局边） |
| 改 `section-extraction-pass.md`（共享核心） | 新 envelope（relations 取代 section-local links）、引用全局 nodes/relations；**保持跨节字节一致以护缓存** |
| 归档 `experiment.md`/`analysis.md` | 移入 `archive/legacy-prompts/`（或删除） |
| 改 `planning-pass.md` | 归档/替换为 census+relation 两份（planning 概念被 census 取代） |
| 同步 `docs/section-ir-design.md`、`CLAUDE.md` | 待 0.7 稳定后把蓝本要点回填，并更新 section 列表/关系列表/assembly repairs 描述 |

### #6 · 测试 + smoke [P1]

- 重写 `tests/test_section_pipeline.py`(1984)：覆盖 census 输出校验、relation pass、**全局 relations 校验（取代 section-local）**、evidence 合并、`_dedup_relations`/`_drop_dangling_relations`、content 补漏 reconcile；删/改针对已删 reconcile 的旧测试。
- 适配 `tests/test_section_extraction.py`(150) smoke 到三段式。
- 跑：`.venv/bin/python -m unittest tests.test_section_pipeline`。

### #7 · renderer [P1]

- `tools/render_extraction.py`(892)：读顶层 `relations[]` 渲染；`evidence` 段取代 experiment/analysis 双色；按节点着色保留。

### #8 · 度量（after）[验收]

- 锁 `MODEL=gemini-3-flash-nothinking`，跑同 50 篇批次（`production/`）。
- 改 `tools/count_extraction.py` 数顶层 `relations[]`，比对 before/after 节点数/关系数 + 护栏(validity 通过率、碎片化率)。
- 验收目标：关系数显著上升（合并 + 边升格 + measured_on 复活），节点数温和上升，validity ≥ before，碎片化不劣化。

---

## 执行顺序

1. **#2 源头**：常量(`section_pipeline.py`) + 生成器 → 重生成 schema（含新 census/relation schema）。
2. **#3 pipeline**：三阶段函数 + 装配（全局 relations、删三 reconcile）+ `run_pipeline` 编排。
3. **#4 validator**：全局 relations 校验、去 section-local 硬失败、字段删除、IR 0.7。
4. **#5 prompts**：census/relation/evidence + 共享核心 + 三个保留模块。
5. **#6 测试**通过 → **#7 renderer** → 核查 `production/` 兼容。
6. **#8 跑批比对**召回（先确认 base URL 可达，备用 URL 见上）。

> 常量改动会**级联**穿过 pipeline/validator/1984 行单测，期间仓库处于"重写未完、测试暂红"的正常中间态，直到 #6 收尾。

## 风险与兼容性

- **破坏性**：顶层新增 `relations[]`、删 `subject_id`/`target_ids`/`evaluated_on`/`components` 字段、section 改 4 个 → **旧 0.6 产物不兼容**（属预期；不做迁移）。`production/` 消费端须同步核查。
- **缓存**：content 阶段仍共享 system 核心 + 全文，保持跨节字节一致以命中 prompt 缓存（同 0.6 纪律）。
- **召回护栏**：raw count 可能因过度切分虚高 → #8 必带 validity + 碎片化护栏，并锁模型消除混淆。
- **关系名**：新引入 `about`/`measured_on`，若用户改名，集中在 `RELATION_MATRIX` + 两份 prompt + validator。

## 可选的最小先验证路径

若想先低成本验证"合并 evidence"单点收益（不动全局关系重写）：仅做 #5 的 experiment+analysis→evidence 合并 + #2/#4 对应的 section 改动，保留 0.6 的 section-local link，用 #8 量"同表双抽率/召回"。但用户已选**一次全部修改**，此路径仅作回退预案。
