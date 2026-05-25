# 修改计划：method + experiment 设计改进

- **状态**：✅ 已执行（2026-05-25 全量落地 A–F，71 项单测通过）
- **拟定日期**：2026-05-25
- **执行说明**：
  - 全部 6 项（A/B/C/D/E/F）均已实现，schema 已重生成。
  - **E 的实现收窄**：仅当 `subject_id` 解析不到任何单元（真悬空跨节引用）时才回退 root；指向"存在但类型错误"的引用留给校验器报告，不静默改写——避免误伤 `_dedup_entities` 的 subject_id 改写语义（见 `test_entity_dedup_rewrites_subject_id_references`）。这与计划中"悬空回退"的本意一致。
  - **顺带一致性修整**（计划清单外、但同属 D 目标）：`AGENTS.md`、`README.md` 的"allowed link relations / Metric 约束"也同步去掉 `occurs_under`、补 `evaluated_on`。
  - **未执行（按计划本就排除）**：LLM 冒烟测试需外部 API/网络与计费，留作手动验证：`.venv/bin/python tests/test_section_extraction.py --papers 4 5`。
- **范围**：联合改进 `method` 与 `experiment` 两节的信息完整度与组织合理性，共 6 个问题（A–F，G 并入 A）。
- **触发背景**：将 method/experiment 当作一个接缝来读后发现，论文评测事实是「方法 × 数据集 × 指标」三元组，但当前只有「方法 × 指标」这条边结构化（`Metric.subject_id`），数据集被降级为 Condition 散文；另有死关系 `occurs_under`、`subject_id` 退化/无兜底、method 结构关系异构、objective 三义性等问题。

## 决策基线（已与用户确认）

- **D = 最小**：删除死关系 `occurs_under`，消除 planning 的 split-brain；`method` 节保持单一 `Method` 类型，方法级操作约束仍留在 `implementation_notes`。
- **C = 文档化**：`feeds` 保持 `inputs/outputs` 描述性承载，把「非一等链接」这一决定写进文档。
- **F = 仅统一 objective**：不加 `variants[]`，用一条决策规则消除 objective 表示的三义性。

## 关键实现事实（动手前须知）

- Schema 源头是 `tools/generate_section_schemas.py` + `section_pipeline.py` 常量。`schemas/section-*.schema.json` 是**生成产物**，改常量后必须运行 `python tools/generate_section_schemas.py` 重生成，**不要**手改 JSON。
- 链接 enum 由 `list(LINK_MATRIX)` 生成（generator 约 :344）；从 `LINK_MATRIX` 删除即从 5 个 schema 自动移除。
- dedup 的 `_rewrite_unit_references`（约 :363）遍历 `REFERENCE_LIST_FIELDS`；新引用字段加入该元组即自动跟随 ID 改写。
- `assemble_extraction`（约 :1389）已持有 `plan`，repair 序列在 :1411–1418；可安全新增装配步。
- `_drop_invalid_links`（:706-711）对未知 relation 按「invalid relation」丢弃兜底。
- 行号为撰写时快照，执行时以实际为准。

---

## 改动清单（按问题）

### A · `Metric.evaluated_on`：补全「方法 × 数据集 × 指标」三元组 [P0]

新增可选字段 `evaluated_on: [ent:…]`，引用本节 dataset/benchmark Entity，让 Entity 不再是孤儿，数据集身份从 Condition 散文升为结构化引用。

| 文件 | 位置 | 改动 |
|---|---|---|
| `tools/generate_section_schemas.py` | `OPTIONAL_FIELDS_BY_TYPE`（:48）；Metric props（:293-302） | `Metric` 可选集加 `"evaluated_on"`；属性加 `"evaluated_on": string_array_schema("Local dataset/benchmark Entity IDs this metric was measured on; omit when not localizable")` |
| `section_pipeline.py` | `ALLOWED_FIELDS_BY_TYPE["Metric"]`（:193-204） | 加 `"evaluated_on"` |
| `section_pipeline.py` | `REFERENCE_LIST_FIELDS`（:207） | 加 `"evaluated_on"` → dedup 自动改写 ID |
| `section_pipeline.py` | `_canonicalize_section_id_aliases`（:315 硬编码元组） | 加 `evaluated_on`（或改用 `REFERENCE_LIST_FIELDS`） |
| `section_pipeline.py` | `_validate_unit_fields` Metric 分支（:1951-2013，context_ids 块后） | 仅当存在时校验：必须是 list；每个 id 解析到**本节本地** Entity 且 `entity_class ∈ {dataset, benchmark}`；否则记 issue |
| `prompts/section-extraction/section-modules/experiment.md` | 字段表（:12）、Entity（:9,:25-26）、worked example（:117-133） | 字段表加 `evaluated_on`；新增说明项（引用本地 dataset/benchmark Entity）；示例 metric 加 `"evaluated_on": ["ent:imagenet"]` |
| `prompts/section-extraction/section-modules/analysis.md` | Metric 字段（:21-25） | 轻量提及 `evaluated_on` 可选（analysis 数据集罕见） |
| `docs/section-ir-design.md` | measurement 段（:139） | 注明 Metric 用 `evaluated_on` 结构化连接数据集 |
| `CLAUDE.md` | Metric 规则那条 | 补 `evaluated_on` 为可选数据集连接 |

**顺带修 G**：planning 的 `ent:` 计划项从此有真实落点，不再被 `_reconcile_covers_entries` 剪成 uncovered 噪声。

### D · 删除死关系 `occurs_under` + 消除 split-brain [P0]

`occurs_under`（源 ∈ {Method, Claim}，目标 ∈ {Context, Condition}）在 5 节划分下无任何一节能同时容纳合法源/目标，是诱导废输出的死表面（真实佐证：`tests/section-extraction-outputs/.../experiment_symbolic_system_analysis.json:116-123` 模型自发写出非法 `cnd --occurs_under--> ent`）。

| 文件 | 位置 | 改动 |
|---|---|---|
| `section_pipeline.py` | `LINK_MATRIX`（:150） | 删除 `occurs_under` 整条 → 生成器 enum 自动移除；残留链接由 `_drop_invalid_links` 兜底丢弃 |
| `tools/generate_section_schemas.py` | `LINK_RELATION_HINTS`（:323-329） | `context`→`"supports"`、`claim`→`"supports"`、`experiment`→`"compares_to"`（去掉 occurs_under） |
| `prompts/section-extraction/section-modules/experiment.md` | 反例（:38-41） | 重写，不再引用 occurs_under；改为「数据集用 `evaluated_on`/Entity 表达、指标作用域用 `context_ids` 表达、不要为此造链接」 |
| `prompts/section-extraction/planning-pass.md` | `cnd:` 定义（:86） | 收窄为「**作用于某条上报指标**的评测设置/数据划分/超参」；不 scope 指标的训练/实现配置改入 method `implementation_notes`；删除/改写 `cnd:optimizer_config` 例子 |
| `docs/section-ir-design.md` | 链接矩阵表（:136） | 删 occurs_under 行 |
| `CLAUDE.md` | 「Link Relations」 | allowed 列表去掉 `occurs_under`（剩 `supports, part_of, compares_to`） |

> `context.md`/`claim.md` 无需改（仓库 grep 确认不含 occurs_under）。逐节核实：删除不损失任何**可构造**能力。

### B · `subject_id` 对齐 `evaluates`（不再无脑默认 root）[P1]
### E · `subject_id` 悬空时回退 root（跨节鲁棒性）[P1]

B、E 合入**一个新装配步** `_reconcile_metric_subjects(sections, plan)`。

| 文件 | 位置 | 改动 |
|---|---|---|
| `section_pipeline.py` | 新函数 + `assemble_extraction`（:1413 后、:1418 前调用） | 从 plan 构建 `met-item → evaluates target` 映射与 root method id。每个 experiment Metric：① 计划项有 `evaluates` 且 target 在全局 unit_index → 设 `subject_id` 为该 target（变更记 `uncertain_assignments`）；② 否则若 `subject_id` 悬空 → 回退 root（记日志）。镜像 anchor 修复 |
| `prompts/section-extraction/section-modules/experiment.md` | :16 | 「default to root」→「优先 `evaluates` 目标；无 evaluates 关系时才退 root」 |
| `prompts/section-extraction/section-extraction-pass.md`（共享核心） | :112 | 同义改写为「优先 section_plan 的 `evaluates` 目标，否则 root」。**保持共享核心跨节字节一致**（仍属共享核心文本，不破坏缓存） |
| `docs/section-ir-design.md` | Assembly Repairs（:169-177） | 新增该修复步条目 |
| `CLAUDE.md` | assembly repairs 那条 | 补 `_reconcile_metric_subjects` |

映射细节：Metric → 计划项经 `covers_entries` / 复用的 `item_id` 对应；取 plan 内 `met:` 项的 `evaluates.target_id`；root id 取 `build_id_registry` 中 `role: "root"` 的 item_id。无法精确映射时退 root（可接受）。

### C · `feeds` 数据流：显式文档化（无 schema/代码改动）[P2]

| 文件 | 位置 | 改动 |
|---|---|---|
| `prompts/section-extraction/section-modules/method.md` | 「Using plan relations」（:28-39） | 明确声明：方法间数据流仅由 `inputs/outputs` 字符串**描述性**承载、非可重建链接；method 节结构化链接只有 `part_of`（组合）与 `compares_to`（替代）。消除「半链接半字符串」歧义 |
| `docs/section-ir-design.md` | method 链接段 | 一句话记录此设计决定 |

### F · objective 表示统一（仅加决策规则）[P2]

| 文件 | 位置 | 改动 |
|---|---|---|
| `prompts/section-extraction/section-modules/method.md` | objective_function（:15）、method_kind（:11） | 加单一路由规则：① 方法的损失/优化目标 → 该 Method 的 `objective_function` **字段**（不另建单元）；② 训练**过程**（调度/课程）→ `method_kind: training_strategy`；③ `method_kind: objective_function` 仅留给「损失本身就是贡献」的独立 Method |

> 可选后续（本次不做）：把 `method_kind: objective_function` 从 enum 移除，进一步收敛——属 schema 改动，需另行确认。

---

## 执行顺序

1. **源头常量/生成器**：`section_pipeline.py` 常量（`LINK_MATRIX`、`ALLOWED_FIELDS_BY_TYPE`、`REFERENCE_LIST_FIELDS`）+ 生成器（`OPTIONAL_FIELDS_BY_TYPE`、Metric props、`LINK_RELATION_HINTS`）→ 运行 `python tools/generate_section_schemas.py` 重生成 5 个 schema。
2. **校验 + 装配**：`evaluated_on` 校验、`evaluated_on` 别名规范化、`_reconcile_metric_subjects`（B+E）接入。
3. **提示词/文档**：experiment.md、method.md、analysis.md、planning-pass.md、共享核心、design doc、CLAUDE.md。
4. **测试 + 验证**（见下）。

## 测试

- 既有 `_drop_invalid_links` 测试（`tests/test_section_pipeline.py:819-832`）**仍通过**（warning 仍含 "occurs_under"）；仅更新 :820 过期注释。
- 新增：
  - `evaluated_on` 校验（合法 / 指向非本地 / 指向非 dataset Entity）；
  - dedup 合并数据集时 `evaluated_on` 跟随改写；
  - `_reconcile_metric_subjects`：B（按 evaluates 校正）与 E（悬空回退 root）；
  - 断言 `occurs_under` 不在 `LINK_MATRIX` 且不在任一生成 schema 的 relation enum。
- 运行 `.venv/bin/python -m unittest tests.test_section_pipeline`。
- LLM 冒烟测试（需 API/网络，建议手动跑确认 `evaluated_on` 实际被填充）：
  `.venv/bin/python tests/test_section_extraction.py --papers 4 5`

## 风险与兼容性

- `evaluated_on` 纯增量可选字段 → 向后兼容（旧产物缺它无碍）。
- 删 `occurs_under`：active 路径本就丢弃它，无可构造能力损失（已逐节核实）；旧产物里的 occurs_under 链接重跑时按现有逻辑丢弃。
- `_reconcile_metric_subjects` 会改写部分 `subject_id`（即 B 的修复目的），全部记入 `uncertain_assignments`，可审计。
- 共享核心改写保持跨节字节一致，不伤 prompt 缓存。

## 可选的最小落地路径

若只先验证 P0：仅做执行顺序第 1–2 阶段中与 **A + D** 相关的部分（`evaluated_on` 字段链路 + `occurs_under` 删除 + 相应 schema 重生成与校验），暂缓 B/E/C/F。
