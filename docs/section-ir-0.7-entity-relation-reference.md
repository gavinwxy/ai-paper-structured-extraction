# section-ir-0.7 实体与关系参考

本文档梳理当前抽取框架(**section-ir-0.7**)中的全部**实体类型**、**节点角色**、**字段契约**、**受控词表**与**关系定义**,作为查阅用的速查参考。

> 权威来源是 `section_pipeline.py` 中的常量(`UNIT_TYPES`、`NODE_ROLES`、`ROLE_TO_TYPE`、`RELATION_MATRIX`、`ALLOWED_FIELDS_BY_TYPE` 等)与 schema 生成器 `tools/generate_section_schemas.py`(`STAGE_C_RELATIONS_BY_SECTION`、`OPTIONAL_FIELDS_BY_TYPE` 等)。schema JSON 由这些常量生成,请勿手改 —— 用 `python tools/generate_section_schemas.py` 重新生成。本文档若与代码冲突,以代码为准。
>
> 设计动机与演进见 `docs/section-ir-0.7-redesign.md`(0.7 完整规格)与 `docs/section-ir-design.md`(0.6 遗留)。

抽取流水线是**三阶段**(`node census → relation pass → content fill`),论证主线为:

```
context and gap → claim → method → evidence
```

---

## 一、实体(Unit Types)

共 7 种,按**来源**分两类:census 节点在 A 阶段被打 `role` 标签,其 `type` 由 `role` 派生;`Context`/`Setting`/`Claim` 在 C 阶段内容填充时新生。

| 类型 | 来源 | 说明 | id 前缀 |
|---|---|---|---|
| `Document` | 元数据 | 文档根节点 | `doc:` |
| `Method` | **census 节点**(A) | 方法 / 系统 / 模块 | `mth:` |
| `Entity` | **census 节点**(A) | 数据 / 问题底物(数据集、基准、任务) | `ent:` |
| `Metric` | **census 节点**(A) | 报告的性能指标 | `met:` |
| `Context` | 新生(C) | 论证前提 | `ctx:` |
| `Setting` | 新生(C) | 操作性约束(指标的作用域) | `set:` |
| `Claim` | 新生(C) | 论断 | `clm:` |

要点:

- census 节点的 `node_id` 被**原样复用**为最终 unit id —— 某 section 物化该节点时,id 不变。
- census 只承诺一个轴(`role`):coarse `type`、Entity class、文档根都由 `role` 派生,不再有旧的 `type`/`entity_class`/`is_root` 三套半重叠字段。
- 每个 unit id 在全文档**只定义一次**;跨单元引用一律走 `relations[]` 边,而非 unit 字段。
- 被禁用的历史类型(`FORBIDDEN_UNIT_TYPES`):`RoleBinding`、`Relation`、`MethodArtifact`、`SystemModel`、`Proposition`、`Category`、`Provenance`。

---

## 二、Census 节点角色(role,8 个 / 4 个搜索簇)

A 阶段(`prompts/section-extraction/node-census.md`)每个节点只打**一个** `role`,coarse `type` 与 Entity class 全部由它派生。指导原则:"追踪方法的一生"(trace the method's life)。

| 搜索簇 | role | → type | 含义 |
|---|---|---|---|
| **the_method**(我的) | `contribution` | Method | 论文唯一主方法(文档根,有且仅一个) |
| | `component` | Method | 贡献的子模块 |
| **prior_art**(他人的) | `builds_on` | Method | 被扩展的已有方法 |
| | `compared_against` | Method | 作为基线对比的方法(含黑盒、仅有分数的基线) |
| **testbed**(数据) | `dataset` | Entity | 训练 / 评测数据 |
| | `benchmark` | Entity | 标准化数据集 + 协议 |
| | `task` | Entity | 被解决 / 评测的问题 |
| **yardsticks**(指标) | `metric` | Metric | 报告的性能度量 |

`ROLE_TO_TYPE` 映射:`contribution`/`component`/`builds_on`/`compared_against` → `Method`;`dataset`/`benchmark`/`task` → `Entity`(role 名即 entity_class);`metric` → `Metric`。

两条作用域规则:

- **命名模型一律是 Method**(`builds_on` / `compared_against`),绝不是 testbed 节点。
- **器械不是节点**:硬件与打分模型(如 CLIP)丢弃,打分模型写进指标的 gloss。

其他节点字段:

- `salience ∈ {must, should}` —— 覆盖率按 `must` 节点衡量;未物化的 must 节点会出现在 `extraction_notes.uncovered_items`。
- `cite_keys` —— prior_art / testbed 节点携带的引文标记(如 `["31"]`),是引用回链(`reconcile_reference_units`)的确定性连接键;contribution、component、task、metric 为 `[]`。
- 基线策略(2026-05-26 反转):每个对比系统都是一个 `compared_against` Method 节点,物化为轻量 Method 单元,带 `compares_to` 边指向贡献,其数值是相关 Metric 的一行 `scores[]`(`variant` 命名该系统)。基线**绝不**是 Entity。
- `normalize_census_nodes` 由 `role` 派生 `type`、重打 id 前缀、去重,并保证恰好一个 `contribution`(无则提升首个 must-method,多余的降为 `component`)。

---

## 三、各实体的字段契约(`ALLOWED_FIELDS_BY_TYPE`)

所有类型都隐含 `id` + `type`。下表列出业务字段(✓必填 / ○选填)。选填字段缺省时**整键省略**,不得伪造。

| 类型 | 必填字段 | 选填字段 |
|---|---|---|
| `Document` | `doc_id`, `title`, `doc_role`, `provenance` | — |
| `Entity` | `name`, `entity_class`, `provenance` | — |
| `Method` | `name`, `method_kind`, `description`, `implementation_notes`, `provenance` | `inputs[]`, `outputs[]`, `formulas[]`, `objective_function` |
| `Claim` | `statement`, `claim_kind`, `provenance` | — |
| `Context` | `context_kind`, `description`, `provenance` | — |
| `Setting` | `setting_kind`, `description`, `provenance` | — |
| `Metric` | `name`, `unit`, `scores[]`, `setting_ids`, `provenance` | `comparison_direction` |

(`OPTIONAL_FIELDS_BY_TYPE`:`Method` 的 `inputs`/`outputs`/`formulas`/`objective_function` 与 `Metric` 的 `comparison_direction` 为选填,其余字段必填。)

### 关键嵌套结构

- **`Metric.scores[]`** —— 每个系统 × 每个 split 一行,每行必填 `{variant, value, variance, system_id, setting_id}`:
  - `variant`:论文给的标签;
  - `system_id`:指向该行所报告的 **Method 单元**(贡献变体或基线;无对应节点时为 `""`),把数值行变成结构化对比;非空时必须全局解析到一个 Method;
  - `setting_id`:指向该行测量所在的**本地 Setting**(无则 `""`);非空时必须解析到 section 本地 Setting。
  - 一个指标横跨多个 split 时(如同一 BLEU 下的 EN-DE + EN-FR 行),靠 `setting_id` 区分,避免把分列折叠成单值。
- **`Metric.setting_ids`** —— 0.7 中唯一保留的"引用列表"unit 字段,指向 section 本地 Setting(可空:消融指标无,可部署指标通常被一个 Setting 限定)。
- **`Method.formulas[]`** —— 每项 `{name, expression, symbols[]}`;`symbols[]` 每项 `{symbol, description}` 注解公式中一个 token,可为空。出现时 `expression`、每个 `symbol`/`description` 必须非空。
- **`Method.objective_function`** —— `{expression, description, symbols[]}`,出现时 `expression` 必须非空。

### Provenance

- provenance 是扁平的 `§N` 顶层位置标记列表(`source_kind` 已于 2026-05-26 移除;装配端 `_normalize_provenance_markers` 把 `§N.M` 收敛为 `§N`)。
- 每个 `Claim` 与 `Metric` 必须有**非空** provenance。

### 已移除的字段(避免误用)

- `Metric`:`subject_id`、`evaluated_on`(→ 全局 `evaluates`/`measured_on` 边)、`value_type`(单调,恒为 scalar)。
- `Method`:`components`(→ 全局 `part_of` 边)。
- `Claim`:`target_ids`(→ 全局 `about` 边)、`polarity`、`novelty`、`epistemic_status`(单调)。
- `Entity`:`model` 类(命名模型现归 Method)、`hardware` 类(器械,非节点)。

---

## 四、受控词表(scoped to AI/ML)

词表已**收窄到 AI/ML 文献**(类型清理时剪掉了在语料上从不触发的取值)。

| 字段 | 取值 |
|---|---|
| `claim_kind`(6) | `descriptive`, `mechanistic`, `comparative`, `modeling`, `ablation_finding`, `failure_mode` |
| `context_kind`(5) | `background`, `gap`, `motivation`, `challenge`, `assumption` |
| `setting_kind`(5) | `data_split`, `inference_protocol`, `training_config`, `ensembling`, `population` |
| `entity_class`(3) | `dataset`, `benchmark`, `task` |
| `method_kind`(4) | `algorithm`, `model_architecture`, `training_strategy`, `objective_function` |
| `comparison_direction`(4) | `higher_is_better`, `lower_is_better`, `target`, `unspecified` |
| `doc_role`(5) | `research_article`, `review`, `meta_analysis`, `methodology`, `benchmark_survey` |
| `salience`(2,census 节点) | `must`, `should` |

### Context vs. Setting(易混淆)

- `Context`(论证前提):`context_kind ∈ {background, gap, motivation, challenge, assumption}`,字段 `{context_kind, description}`。
- `Setting`(操作约束):`setting_kind ∈ {data_split, inference_protocol, training_config, ensembling, population}`,字段 `{setting_kind, description}` —— 一句话点明限定某指标的具体设置。
  - 2026-05-27 重新引入 `setting_kind`:旧的 `condition_kind` 单调(恒为 `evaluation_setup`),但 Settings 实际异质 —— `training_config`/`ensembling` 与 `data_split` 不可互换,集成数与单模型数也不是公平的同侪。`data_split` Setting 同时是多 split 指标的 `scores[].setting_id` 的落点。

### 清理掉的单调字段汇总

Metric `value_type`、Claim `novelty`/`epistemic_status`/`polarity`、`claim_kind` 的 `causal`/`correlational`、`entity_class` 的 `model`/`hardware`、`method_kind` 的 `protocol`/`software_system`、provenance 的 `source_kind`、Setting 旧的 `condition_kind`。

---

## 五、关系(`relations[]`,全局 7 种)

`relations[]` 是**唯一的顶层全局边列表**;端点可解析到任意位置定义的 unit(0.6 的 section-local 链接已废除)。每条边形如 `{source_id, relation, target_id, provenance}`。类型矩阵定义于 `section_pipeline.py` 的 `RELATION_MATRIX`,是运行时契约。

| 关系 | source → target | 授权阶段 | 语义 |
|---|---|---|---|
| `part_of` | {Method, Entity} → {Method, Entity} | **B 关系遍** | 组成 / 隶属 |
| `compares_to` | {Method, Entity, Metric} → 同集 | **B 关系遍** | 对比 |
| `evaluates` | Metric → Method | **B 关系遍** | 指标度量哪个方法(只指向贡献 / 组件,**绝不**指向基线) |
| `measured_on` | Metric → Entity(dataset / benchmark) | **B 关系遍** | 指标在哪个数据上测 |
| `about` | Claim → {Method, Entity, Metric} | **C 内容**(claim / evidence) | 论断关于什么 |
| `supports` | {Metric, Claim} → Claim | **C 内容**(claim / evidence) | 支持某论断 |
| `motivates` | Context → {Method, Entity} | **C 内容**(context) | 前提(gap)驱动它所证成的贡献 |

### 按阶段 / section 的产权

- **结构边** `part_of` / `compares_to` / `evaluates` / `measured_on`(`STAGE_B_RELATIONS`)由 **B 关系遍**(`prompts/section-extraction/relation-pass.md`)在**完整节点集**视野下一次性建立 —— 跨 section 组合、指标-主体绑定都无需前向引用,也无需 reconcile 补丁。
- **内容边** `about` / `supports` / `motivates`(`STAGE_C_RELATIONS`)由 C 阶段内容填充建立,因为它们的端点含 C 阶段新生的 unit。按 section 授权的子集(`STAGE_C_RELATIONS_BY_SECTION`):
  - `context` → 仅 `motivates`
  - `claim` / `evidence` → `about`、`supports`
- `motivates`(2026-05-27 新增)从**新生 Context** 指向 **census 节点**(每个 section 的 `node_registry` 都可见),因此能在并行分节下存活 —— 这点不同于旧的 `occurs_under`(它指向另一个新生 unit,无法跨 section)。

### 关系相关约束

- 指标 → 方法的链接是 `evaluates`(只指向所度量的贡献 / 组件);指标 → 数据集的链接是 `measured_on`。装配端 `_drop_baseline_evaluates` 会删除指向 `compared_against` 基线的 `evaluates` 边(census 驱动),以保住指标的主要主体可恢复。
- 装配会合并 B 阶段边与各内容 section 的 `relations[]` 为单一全局列表,再做安全修复(`_dedup_relations` / `_drop_dangling_relations` / `_drop_invalid_relations`),并记录到 `extraction_notes.uncertain_assignments`。

---

## 六、三阶段产权速览

| 阶段 | 提示词 | 产出 | 谁创建实体 / 边 |
|---|---|---|---|
| **A 节点普查** | `node-census.md` | `spine_summary` + 扁平 `nodes[]`(**无关系**) | 创建 Method / Entity / Metric 节点 |
| **B 关系遍** | `relation-pass.md` | 全局结构边 | `part_of` / `compares_to` / `evaluates` / `measured_on` |
| **C 内容填充**(4 节并行) | `section-extraction-pass.md` + 各 section 模块 | 物化 census 节点 + 新生 Context / Setting / Claim | `about` / `supports` / `motivates` |

各 section 物化的 census 节点类型(`SECTION_MATERIALIZED_NODE_TYPES`):`method` → `Method`;`evidence` → `Metric` + `Entity`;`context`/`claim` 不物化 census 节点(其 unit 全为新生)。各 section 允许的 unit 类型(`SECTION_ALLOWED_UNIT_TYPES`):`context`→`Context`;`claim`→`Claim`;`method`→`Method`;`evidence`→`{Metric, Setting, Claim, Entity}`。

顶层键固定为 `document`、`sections`、`relations`、`extraction_notes`。`covers_entries[]`(section 回溯到所物化 census 节点的痕迹)由装配端确定性派生(census `node_id` ∩ section unit id),模型**不回显**。

IR 版本:`section-ir-0.7`;`extraction_notes.input_mode = node_census_pipeline`。
