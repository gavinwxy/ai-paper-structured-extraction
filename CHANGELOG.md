# 更新日志（section-ir 抽取框架）

本文件整理 `section-ir` 论文抽取框架从 **0.10** 到 **0.13** 的主要改动。
当前 `IR_VERSION = section-ir-0.13`，`ACCEPTED_IR_VERSIONS = {0.12, 0.13}`（见 `section_pipeline.py:158`）。

版本主线分支：`planning-stage-redesign-deepseek-light`（0.12+），
0.10 在 `planning-stage-redesign-deepseek-heavy-fix` 上落地。

格式约定：每个版本列出主题、关键改动与对应 commit；带 A/B 实测数字的结论尽量给出量化结果。

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
