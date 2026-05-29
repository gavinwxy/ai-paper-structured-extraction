# section-ir-0.9 抽取框架 —— 下游开发者指南

> **读者对象:** 消费本抽取流水线产出的下游开发者(检索、图谱构建、问答、可视化、二次分析)。
>
> **本文回答三件事:** 抽取**产出**了哪些东西(文件与字段从哪来)、产出的**结构**是什么、它如何**组织**成一张可遍历的图,以及你该如何**消费**它。
>
> **代码与字段名保留英文**(它们是 `section_pipeline.py` 里的字面量与 schema 键)。中文是描述性散文;**冲突时以代码与 schema 为准**。

## 本文在文档体系中的位置

| 文档 | 讲什么 |
|---|---|
| `CLAUDE.md` | 流水线的整体叙述(三阶段如何运行) |
| `docs/section-ir-0.9-redesign.md` | **为什么**这样设计(两层 taxonomy 的动机、类型合并、移除 `measured_on`) |
| `docs/section-ir-0.9-fields-and-schema.zh.md` | **字段字典**:每个 unit 的每个字段、受控词表、各阶段 schema(*数据长什么样*) |
| **本文** | **产出与组织**:产出哪些文件、如何拼装、如何遍历与消费(*怎么读、怎么用*) |

需要逐字段的权威定义时翻字段字典;需要建立心智模型、知道怎么把产出接进下游时读本文。**唯一权威来源**始终是 `section_pipeline.py` 里的常量(`UNIT_TYPES`、`ALLOWED_FIELDS_BY_TYPE`、`ROLE_VOCAB_BY_TYPE`、`RELATION_MATRIX`)与 `schemas/` 下由 `tools/generate_section_schemas.py` 生成的 JSON schema。

---

## 1. 一句话总览

本框架把一篇科研论文抽取成一条**科学发现的主线(discovery throughline)**:

```
problem  ──▶  method  ──▶  evidence
(研究问题)    (技术方法)    (证据 + 结论)
```

抽取结果不是自由文本,而是一组**带类型的单元(typed units)** 加一张**全局关系图(global relation graph)**,统称 **section-IR 0.9**。下游拿到的是一个结构化 JSON,可以像查图一样查它:"贡献方法是什么"、"对比了哪些基线、各自多少分"、"哪条证据支撑了核心结论"、"这个结论回答了哪个问题"。

每篇论文产出的**规范主产物**是一个 `*_extraction.json`(装配后的 section-IR)。其余文件(census / relations / 各 section 原始输出)是流水线的**中间产物**,用于追溯与调试。

---

## 2. 核心心智模型(读懂结构必备的 4 条)

在看任何字段之前,先建立这 4 条心智模型,后面一切都从它们推导:

**① 一切皆 unit。** 论文被切成 6 种带类型的 unit:`Document`、`Problem`、`Method`、`ExperimentSetup`、`Measure`、`Finding`。每个 unit 有全局唯一的 `id`(带类型前缀,如 `mth:`/`mea:`/`fnd:`)。

**② 关系是全局的、单独成表的。** unit 之间的所有连接都不写在 unit 内部,而是集中在顶层 `relations[]` 里,每条边是 `{source_id, relation, target_id, provenance}`。**想知道 A 和 B 怎么连,永远去查 `relations[]`,而不是去 unit 字段里找。**(唯一的例外是 `Measure` 内部的 `setup_ids` 与 `scores[].system_id`/`scores[].setup_id`,见 §6。)

**③ 每个 unit 有两条分类轴。** 一条粗粒度 `type`(学科中立,锚定科学方法的四个阶段),一条细粒度 `role`(AI/ML 专属差异)。例如一个 `Method` 的 `role` 区分它是 `contribution`(本文贡献)、`component`(组件)、`builds_on`(基于的前作)还是 `compared_against`(对比基线)。

**④ 结构沿"发现主线"排列。** units 归到 3 个 section(`problem`/`method`/`evidence`),edges 把它们串成一条闭合的论证弧:问题 → 它驱动的方法 → 衡量方法的指标 → 指标支撑的结论 → 结论回答问题。

一张图概括:

```
  ┌─────────┐  motivates   ┌──────────────┐
  │ Problem │ ───────────▶ │  Method      │
  └─────────┘              │ (contribution)│◀── part_of ── components
       ▲                   └──────────────┘◀── compares_to ── baselines
       │                          ▲  ▲
       │ resolves                 │  │ evaluates
       │                  about │  │
       │                   ┌────┴──┴─────┐         ┌──────────────────┐
       └─────────────────  │   Finding   │◀────────│     Measure       │
                           │ (headline)  │ supports│ scores[] / setup  │
                           └─────────────┘         └──────────────────┘
                                                          │ setup_id
                                                          ▼
                                                   ┌──────────────┐
                                                   │ExperimentSetup│
                                                   │(dataset/split)│
                                                   └──────────────┘
```

---

## 3. 产出:流水线为每篇论文生成哪些文件

抽取是**三阶段** LLM 流水线(`node census → relation pass → content fill`)外加 Python 装配。批处理路径(`production/`)为每篇论文落盘一个目录,文件如下:

| 文件 | 产自 | 内容 | 下游是否常用 |
|---|---|---|---|
| `01_census.json` | 阶段 A(node census) | `spine_summary` + 扁平 `nodes[]`(每个承重节点,**无关系**) | 中间产物 / 追溯 |
| `02_metadata.json` | 单次辅助调用 | `title` / `authors[]` / `resources[]` | 配套元数据 |
| `03_references.json` | 单次辅助调用 + reconcile | 参考文献条目,每条带 `relation`(角色/立场/显著性 + `provides_unit_ids`) | 配套,做引用图时用 |
| `04_relations.json` | 阶段 B(relation pass) | 全局结构边的子集(`part_of`/`compares_to`/`evaluates`) | 中间产物 |
| `05_sections/{problem,method,evidence}.json` | 阶段 C(content fill) | 每段的**原始** typed-array 输出(装配前) | 中间产物 / 调试 |
| **`06_extraction.json`** | **Python 装配** | **装配后的 section-IR 0.9(规范主产物)** | **✅ 下游主要消费这个** |
| `07_validation.json` | `validate_section_ir()` | 校验问题列表(干净抽取应为 0) | 质量门禁 |
| `extraction.html` | `tools/render_extraction.py` | 人读的可视化 | 人工核对 |
| `status.json` | 批处理 worker | 状态、耗时、warnings(含引用链接日志) | 运维 |

> 库入口 `run_pipeline()`(`section_pipeline.py`)落盘的文件名略有不同(`{id}_census.json`、`{id}_extraction.json`、`{id}_metadata.json`、`{id}_references.json`,外加把全部结果打包的 `{id}_pipeline.json`),内容语义一致。

**下游接入只需认准三个文件:** `06_extraction.json`(主体)、`02_metadata.json`(题录)、`03_references.json`(引文图)。其余可忽略,除非要追溯某字段是哪一阶段产生的。

---

## 4. 抽取信封:`06_extraction.json` 的顶层结构

一份完成的抽取恰好有**四个顶层键**(多一个少一个都会校验失败):

```jsonc
{
  "document":         { … },     // 单个 Document unit(论文本身)
  "sections":         [ … ],     // 恰好三段:problem / method / evidence
  "relations":        [ … ],     // 唯一的全局边列表
  "extraction_notes": { … }      // 版本、覆盖率、修复记录
}
```

- **`document`** —— 一个 `Document` unit。`thesis` 字段是一句话核心贡献(装配时从 census 的 `spine_summary.central_contribution` 提上来)。
- **`sections`** —— 顺序固定为 `["problem", "method", "evidence"]`。每段形如 `{section_type, anchor_id, covers_entries[], units[]}`:
  - `section_type` —— `"problem"` / `"method"` / `"evidence"`。
  - `anchor_id` —— 本段的代表性 unit id(problem 段指向那个 Problem、method 段指向 contribution、evidence 段指向头号 Measure)。
  - `units[]` —— 本段所有 unit 的**扁平**列表(装配阶段把原始 typed array 拍平进来)。
  - `covers_entries[]` —— 本段物化了哪些 census 节点(确定性回溯轨迹,装配计算,模型不回显)。
- **`relations`** —— 唯一全局边列表;每条边可解析到**任意段**中定义的 unit。
- **`extraction_notes`** —— `{ir_version: "section-ir-0.9", input_mode: "node_census_pipeline", uncovered_items[], uncertain_assignments[], plan_coverage{must_covered,must_total}, …}`。**版本号在这里校验,不在 Document 上。**

> ⚠️ 版本判别:下游务必检查 `extraction_notes.ir_version == "section-ir-0.9"`。仓库里仍可能残留 0.7 的旧输出(其类型为 `Context`/`Claim`/`Entity`/`Setting`/`Metric`,且带已废弃的 `measured_on` 边)——不要把它当 0.9 解析。

---

## 5. 组织形式:units 归段,edges 走全局

这是本框架最容易踩坑、也最关键的组织约定:

### 5.1 units 按 section 归属,但 id 全局唯一

每个 unit 只在**一个** section 的 `units[]` 里定义一次。归属规则:

| section | 装哪些 unit |
|---|---|
| `problem` | 那一个 `Problem`(单一主干) |
| `method` | 所有 `Method`(贡献、组件、前作、基线) |
| `evidence` | 所有 `ExperimentSetup` + `Measure` + `Finding` |

`Document` 是顶层 `document`,不在任何 section 里。

### 5.2 edges 全局,跨段自由连

`relations[]` 是**唯一**的边列表,边的两端可以位于不同 section(例如 `Measure`(evidence 段)`-evaluates->` `Method`(method 段))。这正是把它做成全局表的原因:三个 section 是**并行**抽取的,跨段连接无法在任何单个 section 内完成,所以集中到全局。

**下游推论:** 要回答"X 关联到什么",别遍历 unit 字段,而是 `relations.filter(r => r.source_id===X || r.target_id===X)`。

### 5.3 原始 typed-array vs 装配后的 `units[]`

阶段 C 每段返回的是**按类型分组的数组**而非扁平 `units[]`:problem 段返回 `problems[]`,method 段返回 `methods[]`,evidence 段返回 `measures[]`/`experiment_setups[]`/`findings[]`。装配阶段把它们拍平成各段的 `units[]`。

**下游只面对装配后的 `06_extraction.json`,看到的就是扁平 `units[]`。** typed-array 形态只出现在中间产物 `05_sections/*.json` 里。

### 5.4 每个 unit 从哪来(产生溯源)

| unit | 阶段 A census 发现 | 阶段 C 内容出生 | 物化于段 |
|---|:--:|:--:|---|
| `Method`(全部 role) | ✅ | | method |
| `ExperimentSetup` —— substrate(`dataset`/`benchmark`/`task`) | ✅ | | evidence |
| `ExperimentSetup` —— config(`data_split`/`inference_protocol`/…) | | ✅ | evidence |
| `Measure` | ✅ | | evidence |
| `Problem` | | ✅ | problem |
| `Finding` | | ✅ | evidence |
| `Document` | census + metadata | | 顶层 |

census 物化的 unit(Method、substrate ExperimentSetup)其 `role` 由 census 权威盖章(装配 `_assign_roles_from_census`),内容出生的 unit 自己书写 `role`。`Problem`/`Measure` 不带 `role`。

---

## 6. 量化结果如何编码:`Measure.scores[]`

这是下游最常需要重建的结构——一张"系统 × 数据集/切分 → 分数"的结果表。0.9 用 `Measure` 上的 `scores[]` 行来编码,**一行一个(系统 × 切分)的数据点**:

```jsonc
{
  "id": "mea:mean_iou",
  "type": "Measure",
  "name": "Mean IoU",
  "unit": "%",
  "comparison_direction": "higher_is_better",
  "setup_ids": ["exp:cityscapes", "exp:synthetic_street_view_dataset", "exp:semantic_segmentation"],
  "scores": [
    { "variant": "DeepLab-v2 (ResNet-101)",            "value": "70.4", "variance": "", "system_id": "mth:deeplab_v2_resnet101",        "setup_id": "exp:cityscapes" },
    { "variant": "PSPNet",                              "value": "78.4", "variance": "", "system_id": "mth:pspnet",                       "setup_id": "exp:cityscapes" },
    { "variant": "Ours (coarse pre-training + fine-tuning)", "value": "78.0", "variance": "", "system_id": "mth:convnet_semantic_segmentation", "setup_id": "exp:cityscapes" }
  ],
  "provenance": ["§5"]
}
```

每行 `{variant, value, variance, system_id, setup_id}` 的读法:

- `variant` —— 论文里这一行用的标签(原文措辞)。
- `value` / `variance` —— **都是字符串**(保留原文格式,如 `"78.0"`、`"±0.3"`;无方差则空串)。下游需要数值时自行解析。
- `system_id` —— 指向产生这个数的 **Method unit**(贡献的某个变体,或某个基线)。空串表示没有对应 unit。**这把一行分数变成了结构化对比**:本文方法和基线的分数同表并列,各自指回自己的 Method。
- `setup_id` —— 指向这一行所在的**段内 ExperimentSetup**(数据集/切分)。这是 0.9 里 Measure 绑定到数据的方式(替代了被移除的 `measured_on` 边)。当一个 measure 横跨多个切分(如 EN-DE + EN-FR)时,靠它把每行钉到各自的切分,而不会被压成"每系统一个数"。

**基线全量捕获(2026-05-26 起):** 论文对比的**每个**系统都是一个 `compared_against` 的 Method unit,并在相关 Measure 的 `scores[]` 里有一行(`variant` 写系统名,`system_id` 指回该基线 Method)。所以对比同时被**结构化**(`compares_to` 边)与**量化**(score 行)捕获。

> **下游重建结果表的配方:** 对某个 `Measure`,按 `setup_id` 分组(列=切分),每组内按 `system_id` 取行(行=系统),`value` 填格。`evaluates` 边告诉你这个 measure 主要衡量的是哪个 Method(只指向 contribution/component,**绝不指向基线**)。

---

## 7. 关系图:7 种边及其语义

`relations[]` 里每条边的合法 (源类型 → 目标类型) 由 `RELATION_MATRIX` 约束。7 种关系:

| relation | 源 → 目标 | 含义 | 谁写的 |
|---|---|---|---|
| `part_of` | {Method, ExperimentSetup} → {Method, ExperimentSetup} | 组件属于整体 | 阶段 B |
| `compares_to` | {Method, ExperimentSetup, Measure} → 同 | 对比关系 | 阶段 B |
| `evaluates` | Measure → Method | 指标衡量某方法 | 阶段 B |
| `about` | Finding → {Method, ExperimentSetup, Measure} | 结论是关于谁的 | 阶段 C(evidence) |
| `supports` | {Measure, Finding} → Finding | 证据支撑结论 | 阶段 C(evidence) |
| `motivates` | Problem → {Method, ExperimentSetup} | 问题驱动方法 | 阶段 C(problem) |
| `resolves` | Finding → Problem | 结论回答问题 | 装配合成 |

**发现弧(discovery arc)** 由其中四条边闭合,这是消费时最值得遍历的路径:

```
Problem ──motivates──▶ [contribution Method] ◀──about── [headline Finding] ──resolves──▶ Problem
```

- `motivates`:发现弧的第一箭,由 problem 段从那个 born Problem 指向 census 的 contribution。
- `resolves`:闭合的最后一箭,头号 Finding 指回 Problem。它连接的两个 unit 出生在**不同的并行段**,所以没有任何段能写它——由装配 `_assign_resolves` 从 `Problem --motivates--> [contribution] <--about-- Finding` 这个三角确定性地合成。

> 校验保证:`relations[]` 里每条边的两端都能解析到某个已定义 unit,且类型符合矩阵;装配会丢弃悬空/越权/重复的边。所以下游可以信任边的两端 id 都存在。

---

## 8. 引用链接:参考文献如何接回 unit

`03_references.json` 的每条参考文献带一个 `relation` 块:

```jsonc
{
  "id": "31",
  "title": "Mask R-CNN", "authors": [...], "venue": "...", "year": 2017,
  "relation": {
    "roles": ["baseline"],          // background/motivation/uses_method/uses_data/extends/baseline/contrast/future_work/related
    "stance": "neutral",            // supportive/neutral/critical
    "salience": "central",          // central/peripheral
    "provides_name": "Mask R-CNN",
    "provides_unit_ids": ["mth:mask_rcnn"]   // ← reconcile 填充:这条引用对应哪些抽取出的 unit
  }
}
```

`provides_unit_ids` 是引用与抽取图的**连接键**,由 `reconcile_reference_units` 在内容填充后填充:先用 census 节点的 `cite_keys`(论文自己的引文标记,最稳健,能扛住名字不一致)精确匹配,再退化到 `provides_name` ↔ unit 名唯一匹配。`status.json` 的 warnings 会记录每条链接是经 `cite_key` 还是 `provides_name` 命中的。

**下游做引用图时:** 一条 reference 经 `provides_unit_ids` 直接落到具体的 Method/ExperimentSetup unit,于是"本文用了哪些被引方法做基线/构建块"成了可查询的。`provides_unit_ids` 为空表示这条引用没有对应的抽取 unit(纯背景引用)。

---

## 9. provenance、id 与覆盖率:可信与可追溯

- **provenance(出处):** 每个 unit 和每条边都带 `provenance[]`,是一组 `§N` 顶层小节标记(如 `["§4", "§5"]`)。装配会把细粒度子节标记折叠到顶层父节(`§4.3`→`§4`,附录 `§C.1`→`§C`)。`Finding` 与 `Measure` **必须**非空。下游可用它把任意断言定位回论文小节。
- **id 约定:** `doc:` / `prb:` / `mth:` / `exp:` / `mea:` / `fnd:`。census 节点的 `node_id` 被**原样复用**为物化后 unit 的 id(`node_id == unit_id`),所以从 census 到最终 unit 到引用链接是同一把 key 贯穿。
- **覆盖率:** `extraction_notes.plan_coverage = {must_covered, must_total}` 报告 census 标为 `must` 的承重节点有多少被真正物化;未覆盖的进 `uncovered_items[]`。`uncertain_assignments[]` 记录装配做过的有损但安全的修复。下游可据此给抽取打质量分。

---

## 10. 完整实例(真实 0.9 输出)

以论文《On the Importance of Label Quality for Semantic Segmentation》为例,看一条完整发现弧如何落到结构里。

**Document**
```jsonc
{ "id": "doc:on_the_importance_of_label_qua", "type": "Document", "role": "research_article",
  "title": "On the Importance of Label Quality for Semantic Segmentation",
  "thesis": "训练用更大的粗标注数据可匹配甚至超过更小的精标注数据……(从 census 提上来的一句话贡献)" }
```

**problem 段**(1 个 Problem)
```jsonc
{ "id": "prb:label_quality_vs_performance", "type": "Problem",
  "description": "为语义分割生产精确的像素级标注既费时又昂贵;标注质量与模型性能的关系尚不清楚。" }
```

**method 段**(贡献 + 2 组件 + 1 前作 + 2 基线)
```
mth:convnet_semantic_segmentation   role=contribution      ConvNet for semantic segmentation
mth:label_coarsening_pipeline       role=component         Label coarsening pipeline
mth:coarse_pretraining_fine_tuning  role=component         Coarse pre-training and fine-tuning
mth:deeplab_v2                      role=builds_on         DeepLab-v2
mth:pspnet                          role=compared_against  PSPNet
mth:deeplab_v2_resnet101            role=compared_against  DeepLab-v2 (ResNet-101)
```

**evidence 段**(3 ExperimentSetup + 1 Measure + 3 Finding)
```
exp:synthetic_street_view_dataset   role=dataset           Synthetic street-view dataset
exp:cityscapes                      role=dataset           Cityscapes
exp:semantic_segmentation           role=task              Semantic segmentation
mea:mean_iou                        (Measure)              Mean IoU(scores[] 见 §6)
fnd:label_quality_vs_time           role=comparative       性能主要取决于总标注时间而非标注质量
fnd:coarse_pretraining_benefit      role=comparative       粗预训练 + 少量精调可达到/超过全精标注
fnd:architecture_generality         role=comparative       该结论在不同架构间成立
```

**relations[]**(发现弧用 ★ 标出)
```
mth:label_coarsening_pipeline       part_of      mth:convnet_semantic_segmentation
mth:coarse_pretraining_fine_tuning  part_of      mth:convnet_semantic_segmentation
mth:deeplab_v2                      part_of      mth:convnet_semantic_segmentation
mth:convnet_semantic_segmentation   compares_to  mth:pspnet
mth:convnet_semantic_segmentation   compares_to  mth:deeplab_v2_resnet101
mea:mean_iou                        evaluates    mth:convnet_semantic_segmentation
★ prb:label_quality_vs_performance  motivates    mth:convnet_semantic_segmentation
★ fnd:label_quality_vs_time         about        mth:convnet_semantic_segmentation
  fnd:coarse_pretraining_benefit    about        mth:coarse_pretraining_fine_tuning
★ fnd:label_quality_vs_time         resolves     prb:label_quality_vs_performance
★ fnd:architecture_generality       resolves     prb:label_quality_vs_performance
```

读出来的故事:**问题**(标注质量 vs 性能)→ `motivates` → **贡献方法**(ConvNet,由粗标注流水线 + 粗预训练精调两个组件构成,基于 DeepLab-v2)→ 用 **Mean IoU** 在 Cityscapes 上 `evaluates`、与 PSPNet/DeepLab-v2 同表对比 → 头号 **Finding**(性能取决于标注时间而非质量)→ `resolves` → 回答了**问题**。闭环。

---

## 11. 下游消费配方(可直接照抄的遍历)

设 `ex = JSON.parse(06_extraction.json)`,`units` 为各段 `units[]` 的并集,`rels = ex.relations`。

| 你想要 | 怎么取 |
|---|---|
| 一句话贡献 | `ex.document.thesis` |
| 研究问题 | `problem` 段里唯一的 `Problem.description` |
| 贡献方法 | `units` 中 `type==='Method' && role==='contribution'`(保证恰好一个) |
| 方法的组件 | `rels` 中 `relation==='part_of' && target_id===<contribution>` 的 `source_id` |
| 对比的基线 | `role==='compared_against'` 的 Method,或 `compares_to` 边的目标 |
| 某指标衡量谁 | `rels` 中 `relation==='evaluates' && source_id===<measure>` 的 `target_id` |
| 重建结果表 | 见 §6:按 `Measure.scores[]` 的 `setup_id`(列)× `system_id`(行)摊开 |
| 头号结论 | `Finding` 中带 `resolves` 边的那条(或 `about` 指向 contribution 的那条) |
| 支撑某结论的证据 | `rels` 中 `relation==='supports' && target_id===<finding>` 的 `source_id`(Measure/Finding) |
| 完整发现弧 | `motivates → [contribution] ← about ← Finding → resolves → Problem` |
| 引用接回的方法 | `references[].relation.provides_unit_ids` |
| 定位回原文 | 任意 unit/边的 `provenance[]`(`§N` 标记) |

### 防御性消费(请务必处理)

- **可选字段可能整字段缺失。** `Method` 只有 `name`/`method_kind`(其实 `method_kind` 也是可选)/`description`/`implementation_notes` 较稳;`inputs`/`outputs`/`formulas`/`objective_function` 不支持时**整字段省略**(框架的原则是"不臆造,宁缺")。读之前先判存在。
- **`role` 不是每个类型都有。** `Problem` 和 `Measure` 没有 `role`,读了会得到 `null`/缺失。
- **数值是字符串。** `scores[].value`/`variance` 是字符串,需要算数自己解析。
- **空段会被丢弃。** 装配的 `_drop_empty_sections` 会移除没有 unit 的段——不要假设三段恒在(但典型论文三段齐全)。
- **先验版本,再解析。** 检查 `extraction_notes.ir_version === "section-ir-0.9"`;遇到 `FORBIDDEN_UNIT_TYPES`(`Entity`/`Setting`/`Metric`/`Claim`/…)说明拿到的是旧版或脏数据。
- **edge 端点保证存在。** 校验已丢弃悬空边,所以 `source_id`/`target_id` 必能在 `units` 里查到——但**反过来不成立**(unit 可以没有任何边)。

---

## 12. 稳定性与版本契约

- **IR 版本:** `section-ir-0.9`(在 `extraction_notes.ir_version`)。`input_mode` 恒为 `node_census_pipeline`。
- **6 个 unit 类型 / 7 种关系 是封闭集合**(`UNIT_TYPES` / `RELATION_MATRIX`)。退役名进 `FORBIDDEN_UNIT_TYPES`,出现即"响亮失败"。
- **受控词表**(`ROLE_VOCAB_BY_TYPE`、`METHOD_KINDS`、`COMPARISON_DIRECTIONS`、引用的 `roles`/`stance`/`salience`)由 schema 约束,换学科只换 role 词表、不动 type 集合。
- **schema 是机器可读契约。** `schemas/*.schema.json` 由 `tools/generate_section_schemas.py` 从 `section_pipeline.py` 的常量生成——**绝不要手改 JSON**。下游若要做严格校验,直接拿这些 schema 跑 `06_extraction.json`(以及 census/relation pass 的中间产物各有对应 schema)。
- **运行时权威校验** 是 `validate_section_ir()`;`07_validation.json` 为 0 即通过。

---

## 13. 关联文档与代码

- 整体流水线叙述、模型兼容(DeepSeek json_object 模式)、测试方法:`CLAUDE.md`
- 设计动机(为什么两层 taxonomy / 类型合并 / 移除 `measured_on`):`docs/section-ir-0.9-redesign.md`
- 逐字段权威字典 + 各阶段 schema:`docs/section-ir-0.9-fields-and-schema.zh.md`(英文版 `.md`)
- 实现入口与权威常量:`section_pipeline.py`(`run_pipeline` / `validate_section_ir` / `RELATION_MATRIX` / `ALLOWED_FIELDS_BY_TYPE` / `ROLE_VOCAB_BY_TYPE`)
- 渲染为 HTML:`python tools/render_extraction.py <extraction.json>`
