# 更新日志（section-ir 抽取框架）

本文件整理 `section-ir` 论文抽取框架从 **0.10** 起的主要改动。
当前 `IR_VERSION = section-ir-0.15`，`ACCEPTED_IR_VERSIONS = {0.12, 0.13, 0.14, 0.15}`（见 `section_pipeline.py`）。

版本主线分支：`planning-stage-redesign-deepseek-light`（0.12+），
0.10 在 `planning-stage-redesign-deepseek-heavy-fix` 上落地。

格式约定：每个版本列出主题、关键改动与对应 commit；带 A/B 实测数字的结论尽量给出量化结果。

---

## section-ir-0.15 — 内/外抽取轴解耦：census 纯内部 + 外部方法 re-inject

**日期**：2026-06-16　**分支**：`planning-stage-redesign-deepseek-light-heavy-trim`　**未提交**

把内部内容与外部关系**真正解耦**：census 在 LLM 层只抽本文内部的东西，外部先行方法由专门环节
负责，再**确定性 re-inject 回节点集**，使图谱（对比 / 血缘骨架、引用 join、score-row 锚点、跨论文
index）完整保留。详见 `docs/extraction-axis.md`。

> **推翻 2026-06-16 早先"否决纯内部"的结论**：当时担心纯内部 census 会割断 references→unit join、
> 清空 stage-B 外部边、丢 baseline score-row 锚点——这些担心**靠新增的 re-injection 层全部补回**。
> LLM 不再抽外部方法节点，但代码从外部环节把它们重新造出来并合并进 census，下游看到的节点集与
> 0.14 等价。用户明确接受"有信息损失也没关系"，并选择把 baseline/血缘搬到外部、让外部链接更聚焦
> "方法之间的关系"。早先一并落地的 **references apparatus 例外**（纯优化器/采样/打分模型/硬件/
> 工具库引用当背景 SKIP，与 census "apparatus is not a node" 对齐）保留有效。

### 精炼后的边界（按图谱角色，不按出处）
- **内部（census 直接产）**：contribution / component / problem / metric / finding **+ 完整测试床**
  （dataset / benchmark / task / theoretical_setting / structural_class）。评测数据集 / benchmark
  **算内部**（图谱核心可查询关系 + score-row `setup_id` 锚点）。
- **外部（re-inject）**：只有先行 / 对比的**方法**——`builds_on`（血缘）、`compared_against`（baseline）。

### Increment 1 — census 纯内部 + references 来源 re-inject
- `IR_VERSION = section-ir-0.15`；`ACCEPTED_IR_VERSIONS = {0.12, 0.13, 0.14, 0.15}`。
- census `node_role` enum 收缩为 `INTERNAL_NODE_ROLES`；`normalize_census_nodes` 丢弃漏抽的外部角色；
  `node-census.md` 改为四簇、删 prior_art 簇。
- `materialize_external_methods(references, census)`：`validate_census` 后、`build_node_registry`
  前，从 references 的 `builds_on` / `compares_to` 条目铸造外部 `mth:` 节点 re-inject。

### Increment 2 — 专用 external-methods 散文 pass + 回投
- **为何**：references 引文/表格锚定，对散文血缘（"we build on / extend X"）天然欠召回；其
  schema 要求 `{id, authors, title, venue, year}` 且禁编造，**结构上**装不下散文里点名却无干净引文行
  的血缘。Increment 1 实测 `builds_on` 边 −64%（vs 0.14）。
- **新 pass**：`prompts/external-methods-extraction.md` + `schemas/external-methods-output.schema.json`
  + `run_external_methods_extraction` / worker `_run_external_methods`（Phase-1 并行，冷缓存，默认开，
  `--no-external-methods` 退回 Increment-1）。输出 `{name, relation, cite_key, evidence}`；`evidence`
  是硬门控，`builds_on` 必须能引"本文方法作主语 + 血缘动词 + 该方法作宾语"的句子。
- **合并** `materialize_external_methods(references, census, external_methods)`：两源单次确定性并集
  排序、按 name 去重 + **cite_key 桥接**（"ResNet"[8] ≡ "Residual Network"[8]）、`builds_on` 升级
  `compared_against`、撞内部节点内部优先。
- **回投 references 层**（关键正确性 fix）：只由散文 pass 找到的外部方法合成最小 references 条目
  （`title = name`）追加进 `references`，否则它们对 `reconcile_reference_units` 和跨论文
  `build_entity_index`（按 `references[].title` 聚类、跳过空 title）隐形——有边却无法跨语料 join。

### 实测（20 篇配对 A/B，control=Inc1 vs treat=Inc2，同代码仅 `--no-external-methods` 之差）
- 20/20 valid 两臂。外部方法节点 **160→197（+23%）**，distinct 160→196（≈无重复膨胀）。
- `builds_on` 边（post-bf）**28→41（+46%）**，`compares_to` **152→189（+24%）**，外部边预算 **+28%**。
- **回归门全绿或更好**：testbed 89→89、setup_id 91→90、`part_of` 94→91（无噪声爆炸）；回投 fix 让
  refs 链接率 **56%→66%**、system_id **87%→96%**（pass-only 外部方法现在能 join + 索引）。
- `builds_on` 精度盲审（30 条 pass 发射，3-judge 多数）：**87% 真外部方法链接，13% 纯噪声**；严格血缘
  47%、另 33% 真依赖但更该标 `uses`（base-model/backbone）、7% 该标 `compared_against`。
- 设计经 4-lens 红队评审（GO_WITH_CHANGES）：回投 fix、并集去重、evidence 硬门控、精度盲审皆按其建议落地。

### Increment 2.1 — pass 也产 `uses`（base-model / backbone 分流）
精度盲审揭示 builds_on 的 33% 其实是"采用 backbone / base-model"的 `uses`，被过度归到 builds_on。
新增**第三个再注入外部方法角色 `uses`**（re-inject-only：`NODE_ROLES`/`EXTERNAL_NODE_ROLES`/
`ROLE_TO_TYPE→Method`/`ROLE_CLUSTER→prior_art`/`METHOD_ROLE_ORDER`，schema 重生）；external-methods
prompt + schema 加 `uses`（builds_on=改写/扩展，uses=原样依赖 backbone/base-model，compared_against=
baseline；数据集/apparatus 仍排除）；relation-pass 让 `uses` 先行节点也**逐节点出边**；references 的
`uses` 仍不铸造节点（指向 census 测试床 / apparatus）——只有散文 pass 的 `uses` 铸造方法节点。

**实测（同 20 篇，Inc2 无-uses → Inc2.1 有-uses）**：20/20 valid。pass builds_on 30→23、`uses` 0→42；
外部方法节点 197→227（+15%，distinct 196→220）；Stage-B 边 builds_on 39→28、`uses` 0→39、compares_to
156→161；方法关系边预算（bo+us+ct, post-bf）317→328（+3%）。回归门：testbed / system_id(96→97%) /
setup_id(90%) 稳；score-row 总数波动（−141 集中在 2 篇大表论文 020/200 的 evidence 抽取非确定性，填充率
不降，非 2.1 退化）；refs 链接绝对值 289→294（不丢，占比因 +69 条 uses 回投条目而稀释）。
**精度**：builds_on 严格血缘 **47%→57%**（base-model 离开 builds_on）；新 `uses` 层 ~95% 为真building
block（base-model/backbone/复用算法 SIFT/RANSAC/TSDF/Louvain…，无数据集/优化器泄漏）。残留 builds_on
噪声（survey-actor: DETR/Kennedy；baseline: BiLSTM；少量仍漏的 base-model）是另一类，2.1 不针对它。

测试：520 项 unittest 绿（新增跨源合并 / 回投 / gate / `uses` 角色 / 跨源 rank 用例）。
4 篇冒烟 + Inc1↔Inc2↔Inc2.1 共 3×20 篇 A/B 全程零崩溃。

---

## 维护 — 移除 no-blob 旧路径（blob-only 瘦身）

**日期**：2026-06-15　**分支**：`planning-stage-redesign-deepseek-light-heavy-trim`

blob-primary evidence 与 blob-primary references 自 0.12 起已是生产唯一模式（默认开启），
其 `--no-blob-primary-*` 退出分支已无实际用途。本次删除两条 legacy/no-blob 路径，blob 成为无条件行为。
**纯瘦身、行为等价**（生产历来以 blob=True 运行），无 IR 版本变更。

### 删除
- CLI：`--blob-primary-evidence` / `--no-blob-primary-evidence` / `--blob-primary-references` /
  `--no-blob-primary-references` 四个开关；`Config.blob_primary_evidence` / `Config.blob_primary_references` 字段。
- `section_pipeline.py`：`strip_blob_evidence_schema()` 及其 `BLOB_EVIDENCE_FIELDS` / `LEGACY_*_DESCRIPTION` 常量
  （legacy 0.11 evidence schema 派生）；`load_references_schema_for_mode()` 的运行时改写逻辑。
- prompt：legacy `references-extraction.md`（全量转写）与 `evidence.md`（全量转写）删除。
- 函数 `assemble_extraction` / `run_references_extraction` / `extract_single_content_section_sync` /
  `run_content_extraction_sync` / `run_pipeline` 上的 `blob_primary_*` 参数。

### 重命名 / 内联
- blob prompt 去掉 `-blob` 后缀成为唯一规范名：`references-extraction-blob.md` → `references-extraction.md`，
  `section-modules/evidence-blob.md` → `evidence.md`；`load_section_module` 随之去掉特判，直接 `{section_type}.md`。
- references blob 契约**烘焙进 schema 文件** `references-output.schema.json`（与 evidence schema 既已 blob-flavored 对称），
  `load_references_schema_for_mode()` → 无参 `load_references_schema()` 纯加载器。

### 保留（按设计，向后兼容已产出的语料）
- `build_output_manifest()` 仍保留 `blob_primary_*` 形参与条件契约文案（`build_agent_index` 跨语料描述用，
  语料可能含 0.11 旧产物）；渲染器 / 索引侧读取 `extraction_notes.blob_primary_references` 等标记的逻辑不变。
- 装配层始终写入 `extraction_notes["blob_primary_references"] = True` 标记。

测试：496 项全绿（删除/改写/简化覆盖 no-blob 旧路径的用例）。

---

## 0.14 — 公式统一：objective_function 并入 formulas[]

**日期**：2026-06-12

消除 Method 单元上的本体冗余：独立的 `objective_function` 字段与 `formulas[]` 在语义上重叠
（语料扫描：398 个带目标函数的 Method 单元中 **110 个（27.6%）同一表达式被转写两次**，涉及 68 篇），
且单槽位设计无法表达多目标方法（GAN 对抗目标、多任务损失）。

### Schema / prompt
- `objective_function` 字段删除；优化目标改为 `formulas[]` 中带 `"role": "objective"` 标签的条目，
  其"优化什么"的一句话说明 `description` 只允许出现在 objective 条目上（不回吐 0.12 lean-formulas 的成本战果）。
- `FORMULA_ROLES = {"objective"}`（sparse 单值枚举，后续可 E1 式追加）。
- method.md 新增**公式归属规则**：公式属于定义它的单元；组合方法的父单元只保留组合目标
  （如 `L = L^A + αL^R`），不重抄子单元的分量 loss（治理跨单元重复，旧语料中 24 例）。
- `method_kind: objective_function`（结构类别枚举值）不受影响，保留。

### 装配层确定性修复（`_clean_method_equations` 扩展）
- 遗留 `objective_function` 载荷自动迁移为 `role="objective"` 的 formulas 条目（幂等）；
- 同一单元内归一化表达式相同的公式去重，objective 标签/description 合并到存活条目；
- 非法 role 值丢弃（lossy-but-safe，记录 warning），校验层同时设防（双保险）。
- baseline 禁字段表简化为 `inputs/outputs/formulas`（迁移先行，formulas 禁令即覆盖目标函数）。

### Retrofit
- 新增 `tools/retrofit_objective_function.py`（沿 `relink_references.py` 模式）：对已有产物原地重放迁移，
  `--dry-run/--render/--validate`；0.12/0.13 产物迁移后重新打 0.14 版本戳（结构上即满足 0.14 契约），
  更老版本只迁移字段不动版本号。幂等已验证（二次运行 0 变化）。
- 实测：wave2_demo 2 篇（6 迁移/5 合并/0 校验问题）；cvpr_seg_50_v0.12 dry-run 50 篇
  （100 迁移/37 合并/0 校验问题）。`ab_*` 对照目录有意不动（保护 A/B 记录）。

### 渲染
- `render_formulas` 将 objective 条目单列 "Objective" 分组（含 description）；
  `render_objective` 保留用于未 retrofit 的旧语料。

### 20 篇基准 A/B（基线 = HEAD/0.13 于 git worktree，treatment 跑 3 轮迭代收敛）
- 迭代过程：v1 暴露"同胞共享目标全丢"（083 三个变体的交叉熵）与 description 泄漏（125，8 处）；
  v2 修同胞规则 + 确定性 desc-strip 后泄漏归零，但暴露根因——**旧 objective_function 字段本身是
  "搜寻训练目标"的诱导槽位**，删字段后简短陈述的标准损失（CE、L1+SSIM）漏转写；
  v3 在 formulas 规则中恢复显式搜寻指令（"actively hunt… A missing objective must mean the
  paper states none, not that it was overlooked"）。
- v3 终态 vs 基线：20/20 valid（双臂）；单元内重复转写 6→0；跨单元重复 27→21；公式总数 127→138；
  tagged objective 28 vs 基线"真方程"OF 21（基线 33 个 OF 中 12 个为退化条目：裸符号头、prose、
  平凡和——0.14 在去除这些的同时净增真目标覆盖）；083 三同胞交叉熵恢复且各自携带；
  017 单单元双 objective（多目标表达力，0.13 单槽位不可能）；014 的 L_diffusion 正确归位到
  builds_on 单元。desc 泄漏 0（装配层强制）。
- 已知残留（1/20，跨轮不稳定）：200_ECCV Analytic-Splatting 的简短 L1+SSIM 训练损失未被转写，
  且渲染方程 C(u) 间歇性被误标为 objective；表达式集合差中其余"丢失"经逐条核查均为记号变体
  （√/sqrt、ᾱ/\bar α）或基线退化条目，非真实丢失。

### 装配层追加（A/B 驱动）
- `_clean_method_equations` 增加 description 契约强制：非 objective 条目的 description 确定性剥离
  （lossy-but-safe，记 warning）——守住 0.12 lean-formulas 的成本战果不被模型逐条目 prose 侵蚀。

---

## 0.13 — Agent 可检索性（agent-readiness / RF-01…22）

**日期**：2026-06-11 ｜ **主线提交**：`38c9662`、`ef54c11`、`b9e718a`、`c3de371`

把抽取产物从"结构正确"推进到"对下游 Agent 的 QA / 摘要任务可检索、可寻址"。
RF-01…22 全量实现，分三波落地；A/B 干净，CVPR-seg 同域 50 篇 12/12，444 个测试通过。

### Wave 1 — emit 修复（`38c9662`，RF-01..05/10/19/22）
- 元数据回填（metadata backfill）。
- 数值字段 `value_num`：分数/指标值结构化为可比较数字。
- 保真度（fidelity）始终开启，不再依赖可选开关。
- 输出 manifest，便于下游枚举与定位。

### 语料级检索工件（`ef54c11`，RF-06/09/10/13/20/21）
- 新增 `tools/build_agent_index.py`：在语料级别构建检索工件（corpus-level retrieval artifacts）。
- 支持对已有产物的回填（retrofit）。

### Wave 2 — 节点与跨度索引（`b9e718a`，RF-07/08/09/11）
- 新增 Problem 节点（`prb:` 前缀，RF-08）：census 把研究问题规划为可召回节点（`section_pipeline.py:169`）。
- facets / blob-lift / `span_index`：把正文跨度索引化，便于精确取证。
- 新增脚本化评测 `agent_eval`（`tools/agent_eval.py`）。
- 版本号正式升至 `section-ir-0.13`。

### A/B 确认的回归修复（`c3de371`）
- metric identity（指标身份）、always-emit findings（始终产出 finding）、references 边界、ref-edge 守卫。

> 仍延后：RF-14..18；dataset-name 规范化；ros_ai-0.10 产物的版本门控回填。

---

## 0.12 — 成本攻坚 + blob-primary + 精简公式 + 审计

**日期**：2026-06-09 → 2026-06-10 ｜ **版本号 bump**：`625b81c`

围绕"完成端（completion）token 成本"做系统优化：把可由代码确定性切分的大块（结果表、参考文献、公式符号表）从 LLM 完成端剥离，改为代码切片 + LLM 只转写图相关行。
版本级冷启动 A/B：**$0.0953 → $0.0744 ≈ −22% $/篇（z=2.56），completion −37%**（见 `ab-cost-test-0.11-to-0.12-cold.md`）。

### 成本基础设施
- 每个 pass 的 token 遥测（`8741961`）。
- 精简 references 的 doi/url，捕获原始表格，截断即快速失败（`a399462`）。
- 分数保真校验器（score-fidelity verifier）：把转写的分数与源表交叉核对（`0a18716`）。
- token 成本/缓存报告工具 + 内容缓存预热（P3，opt-in）（`398e6a0`），随后**默认开启**，新增 `--no-warm-content-cache` 退出开关（`849112d`）。

### Blob-primary evidence（结果证据）
- 代码按 `[§N]` 标记切分结果 `<table>`，LLM 只转写 contribution 行，baseline 留在 verbatim blob 中（`5e6d17e`）。
- **默认开启**，`--no-blob-primary-evidence` 退出（`d723470`）。
- A/B：默认翻转验证 **−11.2%（$0.0334→$0.0296/篇）**，evidence 完成端 **−37.5%**，20/20 valid，0 丢失。

### Blob-primary references（参考文献）
- references 的同款思路：代码整体切出 verbatim 参考文献列表，LLM 只转写图相关引用（约 37%），背景引用留在 blob（渲染器两者都显示）（`da3b3d7`）。
- **默认开启**，`--no-blob-primary-references` 退出（`84ad6a6`）。
- 热缓存 A/B：references **$0.132→$0.050（−62%）**，completion 148K→55K，总成本 −12.2%，20/20 valid，**0 链接丢失**（链接保留 95%，reference 边 +20%）。

### Lean formulas（精简公式）
- 从 `formulas[]` / `objective_function` 中移除逐符号 `{symbol, description}` 词表（约占 method 输出 25%，87% 是无图消费者的散文）（`08f9b7d`）。
- A/B（method 隔离）：method completion **−30.9%**，总成本 **−6.9%**；公式本身保留（formulas 114→133，表达式齐全），0 符号泄漏。
- 注意：`tools/generate_section_schemas.py` 相对已提交的 evidence schema 是**陈旧**的（会覆盖它）；请通过 `python -m production` 运行。

### 显示层参考文献美化器
- 规则化、渲染时、绝不劣于原始的参考文献切分器（`tools/reference_formatter.py` → `render_extraction.py`）；LLM 仍只看原始 blob（`f522b2b`）。
- 765 篇上 96% 正确切分 / 0.16% 过切分，经 4 轮 review。

### 审计与回归修复
- section-ir-0.12 框架审计：5-agent 审计 + 全部修复（finding_ids 重写缺口、refs-blob 切片、prettifier 文本丢失、generator 覆盖、opt-out schema 契约、render HTML 审计、同步路径分叉等）（`f4e492e`）。
- 提示词审计 Q1+Q3：消除陈旧契约冲突、机械化弱模型规则、削减冗余；A/B 在 20 篇基准上 17 更好/1 混合/1 更差，score rows +41% verified，−10.2% prompt token（`8ccf1fa`）。
- 模型 A/B（pro vs flash）：100 篇 A/B 显示 deepseek-v4-flash 便宜 −53/−68%、快 2×，但质量明显更差（valid 90 vs 100/100），**保留 pro 为默认**（见 `model-ab-pro-vs-flash-2026-06-10.md`）。

---

## 0.11 — references 角色与 unit-graph 边统一

**日期**：2026-06-08 ｜ **版本号 bump**：`afd5a22`

把"参考文献引用关系"与"unit-graph 结构边"统一到同一套词表，消除两条管线的语义分叉。

- 规范化 author-year 引用键（cite key），用于 reference↔unit join（`26c6883`）。
  - 修复了 author-year cite-key join bug：join 率 **45% → 95.5%**（`_normalize_cite_key` + `tools/relink_references.py`）。
- 把 references 关系词表简化为 4 个合并类（`6bc7730`）。
- references 角色与 unit-graph 边统一，版本号升至 `section-ir-0.11`（`afd5a22`）。
  - 一篇引用的"引用角色"即其 unit-graph 边（FG-12，`section_pipeline.py:419`）。
- README 与代码对齐（`1100b67`）。

> 经验性结论：Stage-A census 的 cite_keys 与独立的 references pass 是**互补而非冗余**（仅 26% 重叠），故两者都保留。

---

## 0.10 — 字段设计泛化修复（FG-1…FG-12）

**日期**：2026-06-02 ｜ **版本号 bump**：`54279a2`

针对 0.9 的"CV 单一文化"偏差做泛化：8 venue / 764 篇评测发现 38 处确认 gap（0 真正阻断项）。
本版按审计 roadmap 全量实现 FG-1…FG-12，全部在真实论文上触发；新增为**加性（additive, E1）**，不破坏既有产物。
全语料 0.10 重跑：765 篇 → 764/765 完成，mop-up 后 **764/764 valid**（052_KDD 是唯一 >32K 输出上限异常）；157 单测通过。

### 审计与计划
- 字段设计泛化审计 + 逐问题测试语料（`9a07469`）。
- section-ir-0.10 泛化修复计划（`d6fb8fe`）。

### 核心实现（`54279a2`）
- FG-1：贡献可以是 benchmark/dataset（不再被强制 coerce 为 Method）→ `contribution_resource`。
- FG-2/3：理论类型 `method_kind` / `Finding.role` / `value_kind` / `assumes`；派生 `Document.role`（genre，`section_pipeline.py:1756`）。
- FG-4/6：新增 `builds_on` / `uses` 边。
- FG-9：`opponent_id` / `judge_id` / `objective_class`。
- FG-11：Finding 量化 payload（`headline_result` 等结构化字段，`section_pipeline.py:321`）。
- FG-12：reference 回填到 unit-graph 边。
- census 修复 `co_contribution`（FG-7，Pass 1）。

### Mop-up（落地后修复）
- FG-5 hollow-Method：把分析型论文 root 在 `contribution_finding` 上（`640745f`）。
- provenance：接受 float refs、合并 ranged/IEEE 标记（`7c509cd`）。
- 装配阶段裁掉 `Measure.setup_ids[]` 中的悬挂条目（`965b698`）。
- 修复更多良性 provenance / 可选枚举瑕疵（`fc59211`）。

### 前置下游字段升级（0.9 末，0.10 前夜）
- 在 unit 上打 `cite_keys`，持久化 reference 链接，metadata 增加 year/venue（`65b3713`）。
- 针对 json_object（DeepSeek）模式硬化 census/relation 校验（`98a15c1`）。

> 文档：刷新 README 至 section-ir-0.10、移除陈旧 plans/issues（`37c5ab1`）；私有化开发文档（`62792b8`）。

---

## 附：版本对照速查

| 版本 | 日期 | 一句话主题 | 默认行为变化 |
|------|------|-----------|-------------|
| 0.13 | 06-11 | Agent 可检索性（RF-01…22） | 元数据回填、Problem 节点、span_index、保真度常开 |
| 0.12 | 06-09→10 | 成本攻坚 + blob-primary | 缓存预热、blob-primary evidence/references、精简公式全部默认开启（−22% $/篇 冷启动） |
| 0.11 | 06-08 | references 角色 ≡ unit-graph 边 | cite-key join 45%→95.5% |
| 0.10 | 06-02 | 字段设计泛化 FG-1…FG-12 | 加性新增，贡献可为 benchmark/dataset、新增 builds_on/uses 等 |

默认抽取模型：`deepseek-v4-pro`（thinking-off），优于 flash（见 0.12 模型 A/B）。
