# section-ir-0.9 — 字段与 Schema 参考

> 本文是 [`section-ir-0.9-fields-and-schema.md`](section-ir-0.9-fields-and-schema.md) 的中文版。代码标识符、字段名、枚举值、类型名与 schema 片段保留英文(它们是代码里的字面量)。若两版有出入,以英文版与代码为准。

这是当前抽取 IR(`section-ir-0.9`)的**字段级参考**:每个 unit 类型、其字段、受控词表、关系矩阵,以及各阶段的 JSON schema。它描述的是*数据长什么样*。

关于*为什么这样设计*(两层 taxonomy 的动机、Entity⊎Setting 合并、移除 `measured_on`),见 [`section-ir-0.9-redesign.md`](section-ir-0.9-redesign.md);流水线整体叙述见项目 `CLAUDE.md`。

**Source of truth(权威来源):** `section_pipeline.py` 里的常量(`UNIT_TYPES`、`ALLOWED_FIELDS_BY_TYPE`、`ROLE_VOCAB_BY_TYPE`、`RELATION_MATRIX` 等)和 `schemas/` 里的 JSON schema——后者由 `tools/generate_section_schemas.py` 从这些常量生成。本文是手写的*描述性*散文;若与代码冲突,以代码为准。

---

## 1. 抽取信封(envelope)

一份完成的抽取是一个 JSON 对象,恰好有四个顶层键:

```jsonc
{
  "document":        { … },        // 单个 Document unit(论文本身)
  "sections":        [ … ],        // problem / method / evidence,各自带 units[]
  "relations":       [ … ],        // 唯一的全局边列表
  "extraction_notes": { … }        // ir_version、input_mode、覆盖率、修复记录
}
```

- **`document`** —— 一个 `Document` unit(见 §4.1)。
- **`sections`** —— 三个段,顺序为 `SECTION_ORDER` = `["problem", "method", "evidence"]`。每段为 `{section_type, anchor_id, covers_entries[], units[]}`。`units[]` 是扁平化后的单元列表(装配阶段把原始 typed arrays 扁平进来);`covers_entries[]` 是回溯到 census 节点的确定性轨迹,由装配计算——模型从不回显它。
- **`relations`** —— *唯一*的全局边列表。段不再带 `links`;每条边都住在这里,可解析到**任意**段中定义的 unit(§5)。
- **`extraction_notes`** —— `{ir_version: "section-ir-0.9", input_mode: "node_census_pipeline", uncovered_items[], uncertain_assignments[], …}`。`ir_version` 在此处校验,**不在** Document 上。

### 标识符约定

每个 unit id 匹配 `^[a-z][a-z0-9_]*:[a-z0-9_]+$` —— 类型前缀 + 冒号 + slug:

| 类型 | 前缀 | | 类型 | 前缀 |
|---|---|---|---|---|
| Document | `doc:` | | ExperimentSetup | `exp:` |
| Problem | `prb:` | | Measure | `mea:` |
| Method | `mth:` | | Finding | `fnd:` |

每个 id **恰好定义一次**。当某段物化一个 census 节点时,census 的 `node_id` 被**原样**复用为该 unit 的 id(故 `node_id == unit_id`,引用链可直通)。跨单元引用一律是 **`relations[]` 里的边**,而非 unit 字段——唯二的单元内引用是 `Measure.setup_ids[]` 和逐行标量 `scores[].system_id` / `scores[].setup_id`。

已退役的 0.8 前缀 `ent:`/`set:`/`met:`/`clm:`/`ctx:` 在入口被归一为 0.9 形式,不再产出。

### Provenance(出处)约定

每个 unit、每条 relation 都带 `provenance: string[]` —— 顶层段标记列表,匹配 `^§(?:\d+|[A-Z]+)$`,即 `§4`(正文数字段)或 `§C`(字母附录)。细粒度标记在装配阶段折叠到顶层父级(`§4.3 → §4`、`§C.1 → §C`)。表/图引用(`§Table 3`)**不是**合法 provenance。`Finding` 与 `Measure` 的 provenance 必须**非空**。

---

## 2. 两层 taxonomy:`type` + `role`

每个 unit 携带两条分类轴:

- **`type`** —— 一个小而学科中立的范围,锚定于经验论文的解剖结构(科学方法):*Identify a Problem → Design an Experiment → Collect Results → Construct a Conclusion*。这 6 个 type 在各 AI/ML 子领域里都一样。
- **`role`** —— 挂在*单元上*的 AI/ML 专属差异轴。它统一了旧时分散的 `entity_class`/`setting_kind`/`claim_kind`/`doc_role` 字段,并把 census 的论证角色上抬到 Method。换学科只需换 role 词表,绝不动 `type` 集合。

`Problem` 与 `Measure` **不带** `role`(Problem 是单一主干;Measure 是均匀的)。

| 科学方法阶段 | `type` | `role` 词表 |
|---|---|---|
| Identify a Problem | **Problem** | — |
| Design an Experiment(器械) | **Method** | `contribution` · `component` · `builds_on` · `compared_against` |
| Design an Experiment(材料 + 条件) | **ExperimentSetup** | substrate(基质):`dataset` · `benchmark` · `task` —— config(配置):`data_split` · `inference_protocol` · `training_config` · `ensembling` · `population` |
| Collect Results | **Measure** | — |
| Construct a Conclusion | **Finding** | `descriptive` · `mechanistic` · `comparative` · `modeling` · `ablation_finding` · `failure_mode` |
| 论文本身 | **Document** | `research_article` · `review` · `meta_analysis` · `methodology` · `benchmark_survey` |

`FORBIDDEN_UNIT_TYPES` 拒收退役名 `Entity`、`Setting`、`Metric`、`Claim`(以及更早的 `RoleBinding`/`Relation`/`MethodArtifact`/`SystemModel`/`Proposition`/`Category`/`Provenance`),好让过期的 prompt 或模型输出**响亮地失败**。

---

## 3. 每个 unit 从哪来(census 发现 vs 内容出生)

| `type`(+role) | 发现于 | 物化于 |
|---|---|---|
| Method(所有 role) | node census(A) | method 段(C) |
| ExperimentSetup —— substrate(`dataset`/`benchmark`/`task`) | node census(A) | evidence 段(C) |
| ExperimentSetup —— config(`data_split`/…) | —(出生) | evidence 段(C) |
| Measure | node census(A) | evidence 段(C) |
| Problem | —(出生) | problem 段(C) |
| Finding | —(出生) | evidence 段(C) |
| Document | metadata + census | 装配 |

对 census 物化的单元(Method、substrate ExperimentSetup),census 已经定了 `role`,所以装配的 `_assign_roles_from_census` 权威地盖章,而非信任内容模型回显。出生单元(config ExperimentSetup、Finding)自行书写其 `role`。

---

## 4. Unit 类型参考

下面的字段表中,**R** = 必填(required),**O** = 可选(optional,不支持时整字段省略——绝不臆造)。各类型权威的字段白名单是 `ALLOWED_FIELDS_BY_TYPE`;必填/可选的切分见 schema 生成器里的 `OPTIONAL_FIELDS_BY_TYPE`。

### 4.1 Document

论文本身。每份抽取一个。

| 字段 | R/O | 说明 |
|---|---|---|
| `id` | R | `doc:…` |
| `type` | R | `"Document"` |
| `doc_id` | R | 稳定的文档标识 |
| `title` | R | 论文标题 |
| `role` | R | `DOCUMENT_ROLES`(默认 `research_article`) |
| `thesis` | R | 一句话贡献,装配时从 census `spine_summary.central_contribution` 提上来 |
| `provenance` | O | |

### 4.2 Problem

论文要解决的那个研究问题——**单一主干**(替代了旧的多标签 `Context`)。在 problem 段出生;书写一条指向 contribution 的 `motivates` 边。

| 字段 | R/O | 说明 |
|---|---|---|
| `id` | R | `prb:…` |
| `type` | R | `"Problem"` |
| `description` | R | 一两句点明未解的问题/未满足的需求;背景揉进散文里 |
| `provenance` | R | |

**不带** `role`。

### 4.3 Method

技术器械——贡献、其组件、它所基于的先前工作,以及它对比的每个基线。

| 字段 | R/O | 说明 |
|---|---|---|
| `id` | R | `mth:…` |
| `type` | R | `"Method"` |
| `role` | R | `METHOD_ROLES` —— 论证功能(`contribution`/`component`/`builds_on`/`compared_against`) |
| `name` | R | |
| `description` | R | |
| `implementation_notes` | R | |
| `method_kind` | O | 结构属性,与 `role` 正交:`algorithm` · `model_architecture` · `training_strategy` · `objective_function` |
| `inputs` | O | `string[]` |
| `outputs` | O | `string[]` |
| `formulas` | O | `[{name, expression, symbols[]}]` |
| `objective_function` | O | `{expression, description, symbols[]}` |
| `provenance` | R | |

**恰好一个** Method 的 `role: contribution`(文档根);若无任何节点标记,`normalize_census_nodes` 把第一个 must-method 提升为 contribution,并把多余的降为 `component`。组合关系是 `part_of` 边,而非 `components` 字段。

**`formulas[]` 条目** —— `{name (R), expression (R, 非空), symbols[] (R)}`。
**`objective_function`** —— `{expression (R, 非空), description (R), symbols[] (R)}`。
**`symbols[]` 条目** —— `{symbol (R, 非空), description (R, 非空)}`,逐个注解公式里的一个符号;当表达式不引入符号时该数组可为空。

**基线**(政策:全量捕获):每个被对比的系统都是一个 `compared_against` Method unit(含黑盒/仅给分的基线),带一条指向 contribution 的 `compares_to` 边,并作为相关 Measure 的 `scores[]` 里的一行出现。基线**绝不**是 ExperimentSetup。

### 4.4 ExperimentSetup

0.9 的合并类型(旧 `Entity ⊎ Setting`)。一个 type、按 `role` 分两半:**substrate(基质)**半——你在什么上跑(census 发现、外部、可引用),与**configuration(配置)**半——在什么条件下跑(论文局部、出生、仅当它实际界定某 Measure 时才物化)。

| 字段 | R/O | 说明 |
|---|---|---|
| `id` | R | `exp:…` |
| `type` | R | `"ExperimentSetup"` |
| `role` | R | `EXPERIMENT_SETUP_ROLES`(substrate ∪ config——见下) |
| `name` | R | 数据集名、split 标签 |
| `description` | O | 散文 |
| `provenance` | R | |

`role` ∈ substrate `{dataset, benchmark, task}` ∪ config `{data_split, inference_protocol, training_config, ensembling, population}`。

文献引用标记(`cite_keys`)住在 **census 节点**上,而非 unit 上——引用对账通过 `node_id` 连接,故 unit 保持干净。**不**界定任何 Measure 的配置(硬件、全局超参)按设计不捕获。

### 4.5 Measure

一项报告的性能度量。census 节点;在 evidence 段物化。

| 字段 | R/O | 说明 |
|---|---|---|
| `id` | R | `mea:…` |
| `type` | R | `"Measure"` |
| `name` | R | |
| `unit` | R | 如 `"BLEU"`、`"F1"`、`"%"` |
| `scores` | R | 非空;每个系统**每个 split** 一行(§4.5.1) |
| `setup_ids` | R | 界定本 measure 的 ExperimentSetup(可为 `[]`——如消融 measure) |
| `comparison_direction` | O | `higher_is_better` · `lower_is_better` · `target` · `unspecified` |
| `provenance` | R | |

**不带** `role`。measure→method 的连接是 `evaluates` 边(只指向它度量的 contribution/component,**绝不**指向基线)。measure→dataset 的连接**不是**全局边(`measured_on` 在 0.9 移除)——它是每个评分行的 `setup_id`。`setup_ids[]`(非空时)必须指向段内的 ExperimentSetup unit。

#### 4.5.1 `scores[]` 行

每行为 `{variant, value, variance, system_id, setup_id}`(五字段全必填;当无 unit 表示时,`system_id` 与 `setup_id` 可为空字符串):

| 字段 | 说明 |
|---|---|
| `variant` | 论文对本行系统的标签 |
| `value` | 报告的数值(字符串) |
| `variance` | 误差/标准差/置信区间,或 `""` |
| `system_id` | 本行所报告的 **Method** unit(contribution 变体*或*基线)。非空时须全局解析到一个 Method。它把这一行变成结构化对比。 |
| `setup_id` | 本行测量所处的**段内 ExperimentSetup**。非空时须解析到段内 ExperimentSetup。让一个 measure 能横跨多个 split(同一 BLEU measure 下的 EN-DE + EN-FR 行),而不把某个 split 列压成单一数值。 |

### 4.6 Finding

从证据得出的结论。在 evidence 段出生。**头条贡献发现**也住这里(没有单独的 `claim` 段):它带一条指向 contribution method 的 `about` 边,装配再据此合成回到 Problem 的闭合 `resolves` 边。

| 字段 | R/O | 说明 |
|---|---|---|
| `id` | R | `fnd:…` |
| `type` | R | `"Finding"` |
| `role` | R | `FINDING_ROLES` —— `descriptive` · `mechanistic` · `comparative` · `modeling` · `ablation_finding` · `failure_mode` |
| `statement` | R | |
| `provenance` | R | |

没有 `target_ids` 字段——finding 是关于什么的,由 `about` 边表达。单调的 `polarity`/`novelty`/`epistemic_status` 字段与 `causal`/`correlational` 角色在 AI/ML 范围化清理中被移除。

---

## 5. 关系(全局)

`relations[]` 是单一顶层列表;每条边是 `{source_id, relation, target_id, provenance[]}`,可解析到任意处定义的 unit。类型矩阵是 `RELATION_MATRIX`(7 条关系):

| relation | source → target | 由谁书写 |
|---|---|---|
| `part_of` | {Method, ExperimentSetup} → {Method, ExperimentSetup} | relation pass(B) |
| `compares_to` | {Method, ExperimentSetup, Measure} → 同上 | relation pass(B) |
| `evaluates` | Measure → Method | relation pass(B) |
| `about` | Finding → {Method, ExperimentSetup, Measure} | content —— evidence(C) |
| `supports` | {Measure, Finding} → Finding | content —— evidence(C) |
| `motivates` | Problem → {Method, ExperimentSetup} | content —— problem(C) |
| `resolves` | Finding → Problem | 装配(合成) |

- **阶段 B**(`STAGE_B_RELATIONS`)在全节点集上掌管结构性的节点↔节点边:`part_of`、`compares_to`、`evaluates`。
- **阶段 C** 各段书写需要出生单元的边:evidence → `about`/`supports`;problem → `motivates`(从出生的 Problem 指向一个*census*节点——后者在每段的 registry 中都可见,故无需前向引用)。
- **`resolves`**(`SYNTHESIZED_RELATIONS`)是发现弧的收笔;它连接两个出生于*不同*并行段的单元,故任何段都无法书写它。装配的 `_assign_resolves` 从 contribution 节点的连接确定性地推导:`Problem --motivates--> [contribution] <--about-- Finding` ⇒ `Finding --resolves--> Problem`。

发现弧闭合:`Problem --motivates--> Method(contribution) … Finding --about--> Method(contribution)`,再加 `Finding --resolves--> Problem`。contribution 的头条句子也被提上 `Document.thesis`。

---

## 6. 各阶段 schema

流水线是三个 LLM 阶段加确定性装配。每个阶段在 `schemas/` 下有自己的 schema,由 `tools/generate_section_schemas.py` 从 `section_pipeline.py` 常量生成(切勿手改 JSON;用 `python tools/generate_section_schemas.py` 重新生成)。

### 6.1 阶段 A —— node census(`schemas/node-census-output.schema.json`)

一次全文调用,产出脊柱摘要和一份**无关系**的扁平节点列表:

```jsonc
{
  "spine_summary": {
    "central_contribution": "string",   // → 提上 Document.thesis
    "argument_flow":        "string"
  },
  "nodes": [
    {
      "node_id":      "mth:… | exp:… | mea:…",   // 原样复用为 unit id
      "role":         "contribution | component | builds_on | compared_against | dataset | benchmark | task | metric",
      "name":         "string",
      "gloss":        "string",
      "source_scope": ["§N", …],
      "cite_keys":    ["31", …],   // 文中文献标记;contribution/components/tasks/measures 为 []
      "salience":     "must | should"
    }
  ]
}
```

节点的粗粒度 `type` 和 `node_id` 前缀**由 `role` 派生**(`ROLE_TO_TYPE`):四个 Method 角色 → `mth:`,三个 substrate 角色 → `exp:`,`metric` → `mea:`。census 只承诺单一 `role` 轴;`normalize_census_nodes` 派生 `type`、重写前缀、去重,并确保恰好一个 `contribution`。`cite_keys` 是引用链接(`reconcile_reference_units`)的确定性连接键。

### 6.2 阶段 B —— relation pass(`schemas/relation-pass-output.schema.json`)

一次调用,接收全文加完整的扁平节点列表;只产出结构性边:

```jsonc
{
  "relations": [
    { "source_id": "…", "relation": "part_of | compares_to | evaluates",
      "target_id": "…", "provenance": ["§N", …] }
  ]
}
```

### 6.3 阶段 C —— content fill(`schemas/section-{problem,method,evidence}.schema.json`)

三段并行运行。每段返回 `{ "section": { … } }`。原始响应把单元分组到 **typed arrays**(装配把它们扁平进 `section.units[]`):

| 段 | typed arrays | 书写的 `relations[]`(enum) |
|---|---|---|
| `problem` | `problems[]` | `motivates` |
| `method` | `methods[]` | —(无) |
| `evidence` | `measures[]`、`experiment_setups[]`、`findings[]` | `about`、`supports` |

每个段对象是 `{section_type, anchor_id, <typed arrays>, relations[]?}`。`resolves` 在**任何**阶段-C enum 中都不出现(它是合成的)。`covers_entries[]` **不在** schema 里——由装配推导。

共享的用户 prompt 前缀(论文 / `spine_summary` / `node_registry` / 阶段-B `relations`)位于每段 `section_focus` 之前,故论文正文停留在跨段 prompt 缓存里。每段 focus 模块(`prompts/section-extraction/section-modules/{problem,method,evidence}.md`)是作为 `section_focus` 注入的自洽段契约。

---

## 7. Schema 生成与模型兼容

Schema 从常量生成—— `python tools/generate_section_schemas.py` 重新生成全部五份(每段 + census + relation pass)。结构化输出的强制方式是**随模型自适应**的(`_structured_output_mode` 依据模型名判断):

- **`json_schema` 模式**(非 DeepSeek,如 Gemini/OpenAI 兼容代理):schema 通过 `response_format` 以 `strict: True` 发送,解码受 schema 约束;prompt 不变。
- **`json_object` 模式**(**默认**—— `deepseek*`):`response_format` 为 `{"type": "json_object"}`,且*同一份* schema 经 `schema_to_prompt_spec` 渲染进 prompt,作为 OUTPUT FORMAT CONTRACT(键、必填/可选、enum、id 模式)。该契约由 schema 派生,故永不漂移。它对四个单发调用追加到 system prompt,对内容段折进 `section_focus`(让跨段缓存前缀逐字节不变)。

默认模型是 **`deepseek-v4-pro`**,关闭推理/thinking 运行(在 transport 里通过 `extra_body={"thinking": {"type": "disabled"}}` 注入,门控到 `deepseek*`)。

---

## 8. 校验契约(摘要)

`section_pipeline.py` 里的 `validate_section_ir()` 是运行期契约。除 schema 形状外,它还强制:

- 顶层键恰好为 `document`/`sections`/`relations`/`extraction_notes`;`extraction_notes.ir_version == "section-ir-0.9"`、`input_mode == "node_census_pipeline"`。
- 每个 unit 的 `type` ∈ `UNIT_TYPES`;不得在 `FORBIDDEN_UNIT_TYPES` 内;字段 ⊆ `ALLOWED_FIELDS_BY_TYPE[type]`;`role`(对有该轴的类型)∈ `ROLE_VOCAB_BY_TYPE[type]`。
- 每个 unit id 匹配 `ID_RE` 且恰好定义一次。
- `Finding` 与 `Measure` 的 provenance 非空;每个 provenance 标记匹配 `PROVENANCE_SOURCE_RE`。
- 每条 relation 的 `relation` 在 `RELATION_MATRIX` 中,端点类型受允许,且解析到已定义的 unit。
- `Measure.scores` 非空;非空 `scores[].system_id` 解析到一个 Method;非空 `scores[].setup_id` 解析到段内 ExperimentSetup;`setup_ids`(非空时)指向段内 ExperimentSetup。

装配会先做有损但安全的修复,记入 `extraction_notes.uncertain_assignments`(控制字符剥除、role 盖章、ExperimentSetup 去重、id 去重、空段丢弃、provenance 标记归一、anchor 修复、悬挂评分引用置空、关系列表清理、丢弃指向基线的 `evaluates`、`covers_entries` 重算)。覆盖率以 census 的 `must` 节点为基准衡量;未物化的 must 节点会出现在 `extraction_notes.uncovered_items`。

> 注:除上表所列,装配还包含针对模型输出小毛病的确定性加固(同样记入 `uncertain_assignments`):`_sanitize_unit_ids` 把出生单元 id 的 slug 归一进 `ID_RE` 字符集并改写所有引用;`_drop_empty_scores_measures` 丢弃零评分行的 Measure;`_clean_method_equations` 丢弃 `expression` 为空的 `objective_function`/`formulas[]` 残桩。

---

## 附录 —— 速查

**Unit 类型(6):** `Document`、`Problem`、`Method`、`ExperimentSetup`、`Measure`、`Finding`。

**Id 前缀:** `doc:` `prb:` `mth:` `exp:` `mea:` `fnd:`。

**Role 词表:**
- Document —— `research_article` `review` `meta_analysis` `methodology` `benchmark_survey`
- Method —— `contribution` `component` `builds_on` `compared_against`
- ExperimentSetup —— `dataset` `benchmark` `task` `data_split` `inference_protocol` `training_config` `ensembling` `population`
- Finding —— `descriptive` `mechanistic` `comparative` `modeling` `ablation_finding` `failure_mode`
- Problem、Measure —— *(无)*

**其他 enum:** `method_kind`(可选)—— `algorithm` `model_architecture` `training_strategy` `objective_function`;`comparison_direction` —— `higher_is_better` `lower_is_better` `target` `unspecified`;`salience`(census)—— `must` `should`。

**关系(7):** `part_of` `compares_to` `evaluates` `about` `supports` `motivates` `resolves`。阶段 B:`part_of`/`compares_to`/`evaluates`。阶段 C:`about`/`supports`(evidence)、`motivates`(problem)。合成:`resolves`。
