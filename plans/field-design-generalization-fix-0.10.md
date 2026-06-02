# 修改计划：字段设计泛化性修复 → section-ir-0.10

- **状态**：🟢 **决策已拍板,实施中(2026-06-01)**。FORK 全部敲定:**A2**(census 仅加 `spine_summary.headline_result` 指针,不加 Problem/Finding 节点类型)· **B=role/method_kind 扩展**(不加新一等类型;FG-2 走完整 stopgap 打包)· **C2**(派生 Document.role)· **D1**(上浮——经核已实现;D2 视占比再做)· **E1**(全程 additive,Phase 6 一次切 0.10 + 重抽 764)· **F2 先**(reference 角色回填)再 F1。**范围 = Full 0.10**(全 12 FG,全 6 阶段,收尾重抽 764)。分支 `planning-stage-redesign-deepseek-heavy-fix`。
  - **动手前对 HEAD `d6fb8fe` 核实的三点修正**:① **FG-8 比"prompt 级"更轻** —— `RELATION_MATRIX:235-236` 与 `evidence.md:79-80` 端点表均已许 `about→{Method,ExperimentSetup,Measure}`/`supports Finding→Finding`,单态纯由 worked example 偏向 Method 端点造成,改例即可、无契约改动、无需单独复核。② **FG-10 D1(上浮)已实现** —— `assemble_extraction:1859-1862` 已把 dropped-Measure 警告并入 `uncertain_assignments`,`build_extraction_notes:1394` 已把未覆盖 must-node 列入 `uncovered_items`;故 FG-10 剩余实为 D2/D3 恢复 + ~360 悬挂边(后者仍延后,见风险 6)。③ FG-1 强制是双重硬连:`ROLE_TO_TYPE['contribution']='Method'`(:119)+ `normalize_census_nodes` 提升逻辑(:1151-1162),两处都要开例外。
- **拟定日期**：2026-06-01
- **问题来源(必读)**：`issues/field-design-generalization-issues.zh.md` —— 12 条字段泛化缺口 FG-1..FG-12 的完整证据/根因/单条修复。本文件只管**「怎么改、改哪里、什么顺序、哪些要你拍板」**,不重复每条 issue 的证据。
- **关联**：内存 `genz-field-design-audit.md`(审计全貌);回归语料 `issues/test-corpus-by-issue/`(12 个 FG 文件夹,每个含 `papers/<id>.md` + `<id>.before.json`,papers/ gitignored);规格 `docs/section-ir-0.9-redesign.md`(当前 0.9 两级 type/role 契约)。
- **生成方法**:5 个 reader agent 把每条 FG 映射到精确代码触点 → 架构师综合分阶段计划 → 对抗式 critic 复核(抓出 3 处真实排序/设计错误,已折进本文件)。workflow run `wf_e30dce6e-99e`。

> ⚠️ **行号会漂移**:下文代码触点的行号取自审计当时的 HEAD(`9a07469` 一带),动手前对当前 HEAD 用符号名(函数/常量名)重新定位,别盲信行号。

---

## 一、背景与范围

section-ir-0.9 的字段设计是在 **CVPR 语义分割语料**上调出的,8 会议 / 764 篇大面积评估发现:**每一根字段轴都隐含「贡献=可训练计算产物、证据=数值榜单、指标=越高越好」的假设**。对经验方法类论文良好;对 benchmark/数据集类、理论/证明类、分析/洞察类、多目标/成对评测类(主导 ACL/NeurIPS/ICML/IJCAI/KDD)会系统性地**误 type、强行套用或静默丢失**核心内容。

**重要校准:没有真正的 blocker。** 流水线本身稳健(764/765 全过校验),所有缺口都是**表示保真度**问题,不是崩溃。

**范围**:跨 `section_pipeline.py`、`tools/generate_section_schemas.py`、`schemas/*.json`(生成产物,勿手改)、`prompts/section-extraction/{node-census,relation-pass}.md` + `section-modules/{problem,method,evidence}.md`、`tools/render_extraction.py`。最终切版 `section-ir-0.9 → 0.10` + 重抽 764。

---

## 二、核心洞察:**不要先修根**

issues 文档点名 **FG-9(census 对 Problem/Finding 失明)** 是 FG-1/FG-2/FG-5 强制套用的**上游根因**。直觉是「先修根」。**这是陷阱。**

即便 census 学会**规划**「结果即贡献」,下游类型系统(`ROLE_TO_TYPE`、`METHOD_KINDS`、`_assign_resolves`)仍会在**材化**时把它打回 `Method[algorithm]` —— 规划信号在落地处丢失。

**所以:先建下游的「家」(非 Method 贡献、理论表示、依赖边),再最后打开结果中心规划。**

> **关键路径**:`FG-3(管线) → FG-1 → FG-2 → FG-9(census) → FG-5`
> 这反转了「先修根」的本能,是整份计划的排序内核。

---

## 三、阶段路线图

| Phase | 内容(FG) | 工作量 | 为何此序 |
|---|---|---|---|
| **0** 语料卫生 + 基线 | (无 FG,使能) | S | 类型决策(FORK-B)依赖**真实**普遍度;过滤误抓文档后再测,避免为虚高数字过度工程。同时把 before.json 重新快照成可复现基线。 |
| **1** 廉价独立增量 | FG-3(管线)、FG-11、FG-8(先复核) | M | 纯 schema 超集,0.9 仍合法;互不依赖 |
| **2** 依赖边 | FG-4、FG-12 | M | FG-12 是 FG-4 现成修复路径(复用已抽 reference 角色 + cite_keys join) |
| **3** 非 Method 贡献 | FG-1(+ FG-3 派生激活) | L | 受损最大体裁;双胞胎是结构核心 |
| **4** 理论之家 + 丢失上浮 | FG-2(打包)、FG-10 D1 | L | FG-2 只加 method_kind 是陷阱 |
| **5** 结果中心规划 + Finding-as-root | FG-9(A2)、FG-5、FG-7 | XL | 最深、最依赖前序,放最后 |
| **6** 非榜单评测 + 切版 | FG-6、**0.9→0.10 + regen + 重抽 764** | L | FG-6 普遍度低;切版一次性做 |

---

## 四、各阶段细节与代码触点

### Phase 0 — 语料卫生 + 基线快照 [S]
**目标**:为后续每一条普遍度论断去风险,并锁定可复现的 per-issue 回归基线。
- 过滤误抓非 AI 文档 / 卷首页(`Title_Page`/`Preface`/非线性特征值讲义等)与目录↔内容错位(`007`/`030`/`033`/`065`)。
- 把 `issues/test-corpus-by-issue/*/*.before.json` 对**当前 0.9 HEAD** 重新快照(committed 基线可能已陈旧),冻结为 before。
- **实测各体裁(benchmark/数据集/理论/分析)去污后的真实普遍度** —— FORK-B 的类型决策依据。
- 触点:`production` `discover_papers`(非递归 flat-dir 输入,见内存 `cvpr-seg-200-batch`);新增一个小的卫生过滤器。

### Phase 1 — 廉价、纯增量、独立 [M]
**目标**:落地无需 census 改动的低风险、向后兼容修复。
- **FG-3 管线**:`build_document_unit`(`section_pipeline.py:1337-1360`,硬编码 `role` 在 `:1357`)目前写死 `'research_article'`。**本阶段只铺管线**(把 census/node_registry 线进 `build_document_unit`),**派生逻辑在 Phase 3 才激活**(因为派生信号依赖 FG-1 的 `method_kind` 值 —— 见依赖图的软循环)。`DOCUMENT_ROLES`(`:177`)目前 unused;若需 `position` 体裁在此加枚举值。
- **FG-11**:`ALLOWED_FIELDS_BY_TYPE['Finding']`(`:303-309`)只有 `{id,type,role,statement,provenance}`。加可选量化载荷 `{magnitude, direction, polarity, effect_size, scope, confidence_level}`。**两处必须同一 commit 一起改**:`ALLOWED_FIELDS_BY_TYPE['Finding']` **和** `generate_section_schemas.py` 的 `OPTIONAL_FIELDS_BY_TYPE`(`:48-52`,目前没有 `Finding` 条目),否则 regen 出的 schema 会拒绝新字段。schema 产物:`section-evidence.schema.json` Finding 对象(`~:195-241`)。
- **FG-8(先复核,勿直接当 prompt-only 完成)**:`RELATION_MATRIX`(`:231-239`,约 `:235-236`)其实**已允许** `about`→ExperimentSetup/Measure、`supports` Finding→Finding —— 缺口疑似只在 `evidence.md` 的示例偏向 Method 端点。**但 issues 文档标注 FG-8 是 critic 发现、未单独审计**:动手前必须先跑端点分布复核(analysis 论文 vs 标准方法论文的 `about`/`supports` 端点类型分布),确认是 prompt 级还是矩阵级缺口,再决定改 `evidence.md` 示例还是改矩阵。
- 测试:重抽 FG-03/FG-11/FG-08 文件夹。

### Phase 2 — 依赖边(从既有信号填) [M]
**目标**:加 `builds_on`/`uses` 边类型,并从已抽取的 reference 角色回填,拆解 `compared_against` 过载。
- **FG-4**:census 已给 Method 标 `role=builds_on`,但 `RELATION_MATRIX` 无对应边 → ~53% 被塞进 `part_of`、~37% 孤儿、模型主动写的 11 条 `builds_on` 边被 `_drop_invalid_relations` 丢弃。
  - 加 `builds_on`/`uses` 到:`RELATION_MATRIX`(`:231-239`)、`STAGE_B_RELATIONS`(`:249`)、`generate_section_schemas.py` 的 `STAGE_B_RELATION_ORDER`(`:81`,**手动列表,不自动传播,必须手改**)+ relation_pass schema 描述(`:538-542`)。
  - 改写 `prompts/section-extraction/relation-pass.md`:输出表(`:20-25`)、规则(`:33` 当前**明确教** `builds_on→part_of` 强制,须反转)。
  - ⚠️ **模型学习行为风险**:deepseek 在 0.9 语料学过 part_of 强制,反转 prompt 后可能仍 coerce。缓解:FG-12 的确定性回填不依赖模型服从,提供 builds_on/uses 边的下限。
- **FG-12**:`reconcile_reference_units` 已用 cite_keys 把 reference 连到 unit。扩展它把 reference 角色映射成单元边:`extends→builds_on`、`uses_method`/`uses_data→uses`、`baseline→compares_to`。
  - ⚠️ **未决设计点(critic 抓出)**:reference 带 `stance ∈ {neutral, supportive, critical}`,但 `compares_to` 边**目前没有 stance 字段**。要决定是否给边加 `stance` 字段(schema 改动),否则 supportive/critical 信息在回填时丢失。
- 触点另含:`_drop_invalid_relations`/`_drop_baseline_evaluates` 对扩展后矩阵重新校验。
- 测试:重抽 FG-04/FG-12 文件夹。**解锁** Phase 5 的 FG-7 `co_contribution` 边。

### Phase 3 — 非 Method 贡献(FG-1)+ Document 体裁激活 [L] — ✅ DONE (2026-06-01)
> **实现**:走的是 `contribution_resource`(新 census 角色,`ROLE_TO_TYPE→ExperimentSetup`,`CONTRIBUTION_ROLES`)而非 plan 原稿的「`METHOD_KINDS+=dataset/benchmark`」——benchmark/数据集贡献**结构上就是 ExperimentSetup**,原生挂分数、**无双胞胎可言**(消除而非合并)。`METHOD_KINDS` 只加 `resource`/`taxonomy`(非数据的资源/分类法贡献仍是 Method)。FG-3 体裁由 `_derive_document_role`(据材化贡献单元类型)派生。`normalize_census_nodes` 根逻辑改写(must-Method 优先 contribution,否则 must-ExperimentSetup→contribution_resource)。
> **验证**:FG-01 三篇 benchmark 论文(GraspNet/GRASP/WikiMixQA)全 `contribution_resource`+`benchmark_survey`+0 双胞胎;负对照三篇经验方法论文仍 `Method`+`research_article`+0 误判;0 校验问题。
**目标**:让 benchmark/数据集/资源当贡献,不被强制成 `Method[algorithm]` 也不复制成断连双胞胎。
- 现状:贡献 762/762 全是 Method;94/764 贡献名含 benchmark/dataset/taxonomy/survey 字样;9-16 篇精确同名 Method+ExperimentSetup 双胞胎无边。双胞胎是**结构强制**(benchmark 必须再获一个 ExperimentSetup 化身才能经 `setup_ids`/`scores.setup_id` 挂分数)。
- 改动:
  - `METHOD_KINDS`(`:219`)`+= {dataset, benchmark, resource, taxonomy}`(`generate_section_schemas.py` 动态 import,schema 自动传播)。
  - ⚠️ **`ROLE_TO_TYPE` 是双射(critic 抓出)**:`contribution→Method` 是 1:1。让 `contribution` 落到 ExperimentSetup 必须**要么拆角色**(`contribution_method`/`contribution_resource`)**要么加条件逻辑**,不能直接改映射。Phase 3 动手前先定这个。
  - `normalize_census_nodes`(`:1116-1119` 派生 type;`:1151-1163` contribution 提升):加例外,benchmark/dataset 贡献保持 ExperimentSetup 不被强制提升为 Method。
  - 装配:同名 Method+ExperimentSetup 双胞胎检测 → 合并或连边。
  - prompts:`method.md`(资源贡献不是算法)、`node-census.md`(资源贡献的 census 指引)。
  - **FG-3 派生在此激活**:`build_document_unit` 据贡献节点 `role`/`method_kind` 派生体裁(benchmark/dataset/taxonomy/survey ⇒ `benchmark_survey`/`review`)。
- 测试:重抽 FG-01(+ 复查 FG-03 派生已激活)。

### Phase 4 — 理论之家(FG-2)+ 静默丢失上浮(FG-10 D1) [L] — ✅ DONE (2026-06-01)
> **实现**:`FINDING_ROLES += {theorem,lemma,bound}`、`METHOD_KINDS += {theorem,lemma,bound,definition}`(method.md 抑制其 I/O/formulas/objective_function);`theoretical_setting`/`structural_class` 落 **census substrate**(NODE_ROLES/ROLE_TO_TYPE/ROLE_CLUSTER,自动入 SUBSTRATE_ROLES);`assumes`(Method→ExperimentSetup,stage-B)+ **放宽 `supports` 允许 Method 源**(proves/establishes 不加,被吸收);`scores.value_kind ∈ {numeric,symbolic,asymptotic,qualitative,curve}`(可选,省略⇒numeric);`implementation_notes` 转 schema-optional。FG-10 D1:被丢空-scores Measure 经 `_drop_empty_scores_measures(dropped_out=)` 上浮到 `uncovered_items`(validator 放宽:uncovered_items 可含非 census 的装配丢弃单元)。
> **验证**:FG-02 三篇(051 PSPACE-complete / 024 Fair Range Clustering / 013 k-Trine)——method_kind theorem/definition/bound、Finding theorem/lemma/bound、value_kind symbolic/asymptotic、`assumes`→theoretical_setting、**定理 Method 零伪造 I/O**,均 0 校验问题;负对照三篇经验论文 theory 标签全 0(无误判)。114 单测绿。
**目标**:给定理/界/定义忠实表示,并停止无声销毁自创指标贡献。
- **FG-2 必须打包(五子症状同根,只加 method_kind 是陷阱)**:
  - 🟢 **DECIDED(动手前定死的两个端点 + 一个简化,2026-06-01)**:
    - `assumes` = **Method → ExperimentSetup**(stage-B):定理-Method 假设其理论基底(theoretical_setting/structural_class)。端点最紧、两端皆 census 节点故 relation pass 可写,复用 builds_on/uses 的 stage-B 路径。Finding-源的假设(罕见)不在范围。
    - `proves`/`establishes` **不加** —— 由「放宽 `supports` 允许 Method→Finding」吸收(定理-Method `supports` 结果-Finding)。避免 critic 警告的近义边过载;「已证 vs 观测」的区分已由 `Finding.role`(theorem/lemma/bound=已证)+ supports 源类型(Method 源=形式、Measure 源=经验)承载,无信息损失。
    - theoretical_setting/structural_class 落 **census substrate**(NODE_ROLES+ROLE_TO_TYPE=ExperimentSetup+ROLE_CLUSTER=testbed,自动流入派生的 SUBSTRATE_ROLES),**不**放 config 块 —— 模型现已在 census 浮现它们(误标成 dataset/benchmark/task),最小修复是给对的角色;这也让 `assumes` 两端都是 census 节点。
  - `METHOD_KINDS`(`:241`)`+= {theorem, lemma, bound, definition}`(形式陈述/构造作为器械);`FINDING_ROLES`(`:207`)`+= {theorem, lemma, bound}`(已证结果 —— definition 非结果,不入 Finding.role)。
  - **放宽 `supports` 允许 Method→Finding**(FG-2d:定理被材化成 Method 时,招牌理论结果与证明在图上断开;同时吸收 proves)。
  - `scores` 加 `value_kind ∈ {numeric, symbolic, asymptotic, qualitative, curve}` —— 符号界(`O(n^6)`/`PSPACE-complete`)不再塞进伪榜单;`comparison_direction` 对符号结果可空(`COMPARISON_DIRECTIONS` 已有 `unspecified`,`:243`)。
  - `EXPERIMENT_SETUP_ROLES`(`:197`)经 census substrate 自动获得 `{theoretical_setting, structural_class}`(图类/博弈族/PDDL 域/分布假设 regime 不再被误标 dataset/benchmark)。
  - 放宽非实现性结果的 `implementation_notes` 必填。
  - prompts:`method.md`(`~:30` 当前指示证明用 `method_kind=algorithm`,须改)、`evidence.md`。
- **FG-10 D1(便宜、不削弱守卫的那一半)**:别再静默丢弃 —— 把每个被丢的空 scores Measure(`_drop_empty_scores_measures`,`~:1518`)和未覆盖的指标 must-node(覆盖逻辑 `~:1006`)显式上浮到 `extraction_notes.uncovered_items`。**(critic 提示:`:1518-1535` 似乎已返回 warning 在 `~:1860` 记录 —— 动手前确认 D1 是「改进可见性」还是已部分实现,以免空做。)** D2(保留+status,放宽非空 scores 校验)与 ~360 条悬挂边(跨段一致性,FG-10 另一半)**本阶段不做**,见风险 6。
- ⚠️ `FORBIDDEN_UNIT_TYPES`(`:156-168`)含 `Proposition`(0.8 退役);若**将来**走 FG-2 的新类型路径(FORK-B B3,不推荐),不可复用 `Proposition` 名且须从 FORBIDDEN 移除新名。推荐的 method_kind/role 路径完全绕开 FORBIDDEN。
- 测试:重抽 FG-02/FG-10。

### Phase 5 — 结果中心规划 + Finding-as-root [XL] — ✅ DONE (A2-scoped, 2026-06-01)
> **实现(明确边界)**:**FG-9/A2** —— `spine_summary.headline_result`(可选,census schema + validate + node-census.md)+ 装配 `build_document_unit` lift 到 **`Document.headline_result`**(新可选字段,空则省略)。**FG-5** —— `resolves` 现已经由(可能空洞的)contribution 节点闭合到 headline Finding(既有机制,L385 单测);**A2 不改 census 节点发射**,空洞-Method 仍被 census 发出 —— 真正的结构性 Finding-as-root(消除空洞 Method、Finding 当结构根)是 **A1**,本阶段**不做**(plan 自身已 sanction 条件调度)。A2 交付的是「结果一等化」(headline_result 上浮到 Document)+ arc 闭合在 finding(既有)。**FG-7** —— 加 `co_contribution`({Method,ExperimentSetup}↔同,stage-B)边 + `_assign_resolves` 沿 co_contribution **扇出 arc 根**(fixpoint)+ relation-pass.md 指引;**另修自环 bug**(`_drop_invalid_relations` 丢 source==target,影响全语料,0.9 既存)。
> **验证**:FG-05/FG-07 四篇 —— headline_result 精确命中结果中心论文(019「value learning is not the main bottleneck」/042/035)并上浮 Document;**reframe(据负对照实测)**:模型对经验方法论文也填 headline_result(ZIPA/OSP2B「one-stage outperforms two-stage」)——这是**特性非误判**(每篇都有 headline 结果,与 thesis=artifact 互补,更好地服务 FG-9「结果获得规划槽位」),遂把 schema/prompt 从「仅结果中心」重述为「论文的 headline 已确立结果,纯资源/工具发布才省略」。**co_contribution 模型 0 采纳**(census 把 co-equal 方法压成 component、normalize 降级额外 contribution —— 无 co-equality 信号,属单主干/A1 限制,已记录;边可用+单测+扇出就绪,待 A1 census 改造或模型识别)。122 单测绿,6/6 论文(含负对照)0 校验问题。
> **残留→A1(已知、已记录)**:result-centric 论文的空洞-Method coercion 仍在(headline_result 注解可见但结构未重整);co_contribution 模型采纳需 census 识别 co-equal 贡献(触碰单一-contribution 不变式)。
>
> **【后续修复 · Pass 1,2026-06-01,uncommitted】co_contribution 已修复。** 根因是 census 单根不变式(非边),遂放宽:`validate_census` `root_count != 1`→`< 1`(≥1,>1 合法);`normalize_census_nodes` 保留每个 **`must`** 根、仅降级较弱 `should` 误标(防根泛滥);`node-census.md` 加 co-equal 豁免("罕见;须真正共生可分;存疑取单根");`relation-pass.md` 兄弟变体→`compares_to`/`co_contribution` 而非 `part_of`。验证:013/035/074 全触发 `co_contribution`、假 `part_of` 消失、arc 跨共生贡献扇出、0 校验问题;过度触发 **0/6** 干净单贡献对照长第二根;129 单测绿(3 个旧单根测试改写);CLAUDE.md 同步;无 schema regen。**剩余 A1 仅 = hollow-Method(FG-5,Pass 2,未开工)。**
**目标**:停止 census 在结果中心型论文上锁死器械中心骨架,让 Finding 直接闭合 arc。
- **FG-9(FORK-A A2)**:加可选 `spine_summary.headline_result` 槽位(`validate_census` `:1172-1178` 已 inspect spine_summary);装配用它锚定 `resolves` 并派生体裁 —— **不新增 census 节点类型**。
  - 触点:`schemas/node-census-output.schema.json` spine_summary 槽位;`node-census.md`(`:33` 当前禁 Problem/Finding,放宽到允许 headline_result 注解)。
- **FG-5**:`_assign_resolves`(`:1685-1770`,contribution 查找 `:1704-1711`)目前要求贡献是 census Method/ExperimentSetup。扩展它锚到 headline Finding,`problem→finding→evidence` 成一等 arc,`resolves` 直接闭合 `Problem←Finding`。
  - ⚠️ **critic 抓出的陷阱**:A2 注解**本身不足以**启用 Finding-as-root —— 让 `_assign_resolves` 接受 Finding node_id **会触碰「census 只产 Method/ExperimentSetup/Measure」的不变式**。这是真实架构改动,不是免费搭车。需明确边界。
- **FG-7**(大部分是文档化 + 小边):`resolves` 扇形是 `_assign_resolves` 按设计产生、**语义无损**(CVPR 本身就 2-6 条/篇),**别再把它描述成「单一收尾箭头」**;加 `co_contribution`(Method↔Method)边给 ~4-5 篇 co-equal 方法论文(如 `013_ICML_2008`/`035_ICML_2025`),替代假 `part_of`;允许 arc 扇出到 co-equal 贡献。依赖 Phase 2 的边基础设施。
- 测试:重抽 FG-09/FG-05/FG-07。**若 A2 后仍有残留 hollow-Method coercion,A1(完整 census 节点类型重写)在此调度。**

### Phase 6 — 非榜单评测(FG-6)+ 切版 + 重抽 [L] — ✅ DONE (2026-06-01)
> **实现**:FG-6 —— score 行可选 `opponent_id`(→Method)/`judge_id`(→Method/ExperimentSetup)+ Measure 可选 `objective_class ∈ {primary_quality,cost_efficiency,fairness,safety,robustness}`(走 score-row 字段路线,非 pairwise_preference 子类型);validate + `_repair_score_refs` 拉黑悬挂 opponent/judge + dedup remap 覆盖新键。**切版**:`ir_version` 两处(emit `:1555` + validator `:3158`)0.9→0.10,prompt 头部同切,RELATION_MATRIX 现 11 边。renderer:新边 REL_OUT/IN/COLOR + Document `headline_result`(Result 行)+ Finding payload/objective_class 作 tag pill。CLAUDE.md 加 11-边矩阵 + 0.10 delta 块;memory 加 [[section-ir-0.10-generalization-fix]]。
> **验证(用户改写:只测 per-issue 语料,不跑 764)**:最终 19 篇跨体裁(benchmark/theory/result-centric/co-contribution/empirical/FG-12 reference-heavy)= **19/19 valid,全 section-ir-0.10,0 校验问题**;特性全触发(builds_on 64 / uses 105 / headline_result 19/19 / theory method_kind 24 / value_kind-nonnumeric 86 / opponent|judge 32 / objective_class 13 / doc.role benchmark_survey+review+research_article —— 死轴复活);co_contribution 模型 0 采纳(已记录 A1 限制)。127 单测绿(tests/ 全 gitignored,本地校验)。
**目标**:表示成对/裁判/多目标评测,然后切 0.10 并重抽。
- **FG-6**(moderate/occasional,issues 文档明确缩范围 —— 榜单 + 多 split 已干净迁移,「别动」):score 行加可选 `opponent_id`(→Method)、`judge_id`(→ExperimentSetup/Method),或加 `pairwise_preference` Measure 子类型 `{system_a_id, system_b_id, judge_id, value}`;Measure 加多目标类别轴(primary-quality/cost/fairness/safety)。
- **切版 0.9→0.10(FORK-E E1)**:Phases 1-5 全做成 additive(新枚举/新边/可选字段都是 0.9 超集),开发期版本号不动;Phase 6 一次性:
  - flip IR 版本字符串**两处**:`extraction_notes` 字面量(`section_pipeline.py:1389`)**和** validator 等值检查(`:2846`,拒绝 ≠ `'section-ir-0.9'`)—— 两处必须同切。`input_mode` 保持 `node_census_pipeline`。
  - `python tools/generate_section_schemas.py` regen 全部 schema(per-section + census + relation pass)并同 commit 提交 JSON。
  - 重抽 764(`python -m production <in> <out> --model deepseek-v4-pro`)+ renderer regen。
- 测试:全 764 重抽必须仍 **764/764 有效**,且呈现目标分布漂移(Document.role 不再单值、builds_on 边出现、theorem method_kind 触发、未覆盖 must-node 减少)。

---

## 五、依赖图

```
关键路径:  FG-3(管线) → FG-1 → FG-2 → FG-9(A2) → FG-5
并行轨:    {FG-11, FG-8}(P1)   {FG-4 → FG-12}(P2)   {FG-6}(P6)
```

- **FG-3 软循环**:FG-3 派生需 FG-1 的 `method_kind` 才有信号 → **拆成 P1 管线 + P3 激活**。
- **FG-4 阻塞 FG-12**(矩阵先有边类型才能回填)**和 FG-7 co_contribution**(P5)。
- **FG-1(P3)先于 FG-2(P4)**:都解耦贡献-类型,FG-2 复用 FG-1 引入的 `ROLE_TO_TYPE`/`METHOD_KINDS` 例外。
- **FG-10 拆分**:D1 上浮(P4,便宜)‖ proposed-metric 恢复(D2/D3)阻塞于 FG-1/FG-9 ‖ ~360 悬挂边是独立的跨段对账问题,可延后。
- **FG-9(P5)最深;FG-5 直接搭在它上**(`_assign_resolves` 锚定)。
- **FG-6(P6)独立于以上**(仅 score 行 schema),因低杠杆排最后。

---

## 六、设计岔路(⚠️ 待用户拍板,本轮未决)

每条都给了推荐,但这些是**产品/研究判断,不是机械选择**。下次 session 须先和用户敲定 A/B/E,再动 Phase 3+。

### FORK-A — FG-9 census 改造深度
- **A1** census 获得规划 Problem/Finding 节点的能力(加 `spine_summary.headline_result` + 允许 census 节点 type 为 Finding/Problem)。最忠实、修根;但 `NODE_TYPES={Method,ExperimentSetup,Measure}` 接进 `SECTION_MATERIALIZED_NODE_TYPES`/`NODE_ID_PREFIX_BY_TYPE`/`ROLE_TO_TYPE`/`normalize_census_nodes`/`validate_census`/census prompt(`:33` 明禁)/`_assign_resolves` —— **触及每个阶段,XL,最大爆炸半径**。
- **A2(推荐)** 仅加可选 `spine_summary.headline_result` 指针;装配用它锚定 resolves + 派生体裁,**不让 Problem/Finding 成 census 节点**。爆炸半径小得多,拿到 resolves 锚定 + 体裁派生的高杠杆赢面;但**不阻止** census 提名 hollow `Analysis` Method 当贡献(最差分析论文的规划期 coercion 仍在)。
- **A3** 完全延后 FG-9,先发 FG-1/2/3/4,再实测残留 coercion 是否仍 material。
- **推荐**:**A2 先做(0.10),A1 仅当 0.10 后实测仍有残留 hollow-Method coercion 才上**。理由:A2 低风险拿高杠杆,A1 是 XL 重写,其收益应**用真实残留量验证、而非假设**(且真实普遍度被语料卫生 caveat 搅浑)。
- **为何你来定**:这是最大的架构岔路 —— A1 重写规划阶段和「census-is-Method/ExpSetup/Measure-only」全管线不变式。成本(XL + 全阶段回归风险)vs 收益(一个真实普遍度被搅浑的体裁切片上的保真度)是产品/研究判断。

### FORK-B — FG-1/FG-2 新一等**类型** vs **role/method_kind 扩展**
- **B1** 纯 role/method_kind 扩展:保持 6 类型,`contribution` 可落 ExperimentSetup(FG-1)+ `METHOD_KINDS` 加理论值(FG-2)。最小改动,无 FORBIDDEN 扰动。**但对 FG-2 语义不诚实**:定理不是带 I/O 的 Method,`method_kind=theorem` 单独**不给** `proves`/`assumes` 边或符号 scores —— **已知陷阱**(消了 type error 留下 relation/payload error)。
- **B2** 仅为 FG-1 加 `Resource` 类型。⚠️ **critic 校正:这是 XL 不是 M-L** —— 动 `UNIT_TYPES`/`NODE_ID_PREFIX`/`ROLE_TO_TYPE` 条件/`SECTION_MATERIALIZED`/`RELATION_MATRIX` 全端点/schema/renderer/score-row `system_id` 机制。
- **B3** 同时为 FG-2 加 Theorem/Result + FG-1 让 contribution 落 ExperimentSetup/Resource —— 全类型系统扩展,最忠实,**最 XL**,保证切版 + 重抽。
- **推荐**:FG-1 走「`contribution` 解析到 ExperimentSetup substrate + `METHOD_KINDS` 加资源值 + 装配确定性双胞胎合并/连边」,**初期不加 Resource 类型**;FG-2 走 B1 的 method_kind/Finding.role 理论值 **外加** `proves`/`assumes` 边 + `scores.value_kind`,**明确承认是 stopgap**;真正的 Theorem 类型留待后续版本若理论切片证明持续存在。**FG-2 切勿只做 B1**(陷阱)。
- **为何你来定**:新 unit 类型是单向门(强制 FORBIDDEN 协调 + renderer + 切版 + 重抽)。benchmark/理论体裁是否值得一等类型(vs role),取决于**去污后真实占比**和下游消费者是否需要按类型查询 —— roadmap 决策。**应由 Phase 0 实测决定,而非悬着。**

### FORK-C — FG-3 Document.role 删 vs 派生
- **C1** 直接删(从 `ALLOWED_FIELDS_BY_TYPE['Document']`/`build_document_unit`/`DOCUMENT_ROLES` 移除)。trivial、诚实(止住误导消费者「体裁已捕获」);但对读 `document.role` 的消费者是 breaking,删掉未来体裁槽。
- **C2(推荐)** 从 census 派生:贡献 `role`/`method_kind ∈ {benchmark,dataset,resource,taxonomy,survey}` → `benchmark_survey`,无贡献 + 多 builds_on → `review`,否则 `research_article`。让死轴变活、解锁 FG-1 体裁分流。依赖 FG-1 的 `method_kind` 先落地(软依赖 → P1 管线 / P3 激活)。
- **C3** 由 census 直接输出 `document_genre` 字段。最准但加 census 字段 + LLM 判断轴(会漂移),C2 已覆盖高价值情形,overkill。
- **推荐 C2**,排在 FG-1 `method_kind` 之后。

### FORK-D — FG-10 空 scores Measure / 未覆盖指标 must-node
- **D1(推荐)** 仅上浮:仍丢弃但把每个丢弃 Measure / 未覆盖 must-node 推到 `extraction_notes.uncovered_items`,让丢失可见可审。最小、不削弱守卫。
- **D2** 保留空 scores Measure 带 `status='proposed'` 标志 + 按 status 放宽非空校验。恢复自创指标进图,但削弱一个目前能抓幻觉空 Measure 的守卫。
- **D3** 把 proposed-metric Measure 转成 Finding/Resource(指标即贡献)。最忠实但耦合 FG-1/FG-9。
- **推荐 D1 先做**(最高危失败模式是不可见,D1 便宜地消除不可见且不削弱守卫),D2 同版若 proposed-metric 占比 material 再做。

### FORK-E — 版本切换 + 重抽
- **E1(推荐)** 一次性 0.10:Phases 1-5 累积为 additive(开发期 0.9 字符串不动),Phase 6 切 0.10 + regen + 重抽 764。语料内部一致,只付一次重抽。**切版前把 `test-corpus-by-issue/*.before.json` 对最后一个干净 0.9 HEAD 重新快照**,使 per-issue 回归 0.9-baseline vs 0.10-fixed 干净对比。
- **E2** 增量、additive 保持 0.9,只破坏性变更才切版。省一次大重抽,但语料异质(有的有 builds_on 有的没有),回归易混。
- **E3** 每阶段切版 + 增量重抽。溯源最精确,最贵。
- **推荐 E1**。⚠️ 风险:若某 Phase 3/4/5 改动非干净 additive(删字段/放宽必填令旧消费者拒绝),「保持 0.9 到 P6」假设破裂,被迫提前切版 + 部分重抽 —— **每阶段 diff 须审 additive-only**。

### FORK-F — FG-4 builds_on/uses 边:LLM 编写(stage B) vs reference 角色确定性回填
- **F1** 加边到矩阵 + 由 relation-pass LLM 编写(反转 `relation-pass.md:33` 的 part_of 强制)。直接,但模型学过 coercion 可能不服从。
- **F2(推荐先做)** 从 reference 角色确定性回填(`reconcile_reference_units` 已有 cite_keys join):`extends→builds_on`、`uses_method/uses_data→uses`、`baseline→compares_to`。复用已验证信号、无 LLM 判断。但只覆盖被外部引用(有 cite_keys)的节点,贡献对未引用组件的内部 builds_on 不覆盖,且 stance 无处存。
- **F3** 两者都做(LLM + 确定性回填,互相对账)。最高召回,最多工作,需冲突时的优先规则。
- **推荐 F2 先**(最便宜的高精度赢面),再 F1 覆盖内部/未引用依赖。两者都需把 builds_on/uses 加进 `RELATION_MATRIX`/`STAGE_B_RELATIONS`/`STAGE_B_RELATION_ORDER`。**须决定 stance 是否上 `compares_to` 边(schema 改动)。**

---

## 七、评审(critic)抓出的、已折进计划的修正

1. **FG-3/FG-1 软循环**:FG-3 派生依赖 FG-1 `method_kind` → 拆 P1 管线 + P3 激活(已落进 Phase 1/3)。
2. **A2 ≠ 免费 FG-5**:加 `headline_result` 注解本身不启用 Finding-as-root;仍需改 `_assign_resolves` 接受 Finding node_id,**触碰 census-only-Method 不变式**(已在 Phase 5 标注)。
3. **FG-12 stance 字段未决**:`compares_to` 边目前无 stance 字段,回填前须决定是否加(已在 Phase 2 / FORK-F 标注)。
4. **`ROLE_TO_TYPE` 双射**:让 contribution 落 ExperimentSetup 须拆角色或加条件,不能直接改映射(已在 Phase 3 标注)。
5. **FORK-B B2 实为 XL**(非 M-L),已校正。
6. **FG-2 `assumes`/`proves` 端点未定**:太宽会重演 compared_against 过载,动手前定死端点(已在 Phase 4 标注)。
7. **FG-8 须先复核**(critic 发现、未单独审计):动手前跑端点分布复核(已在 Phase 1 标注)。
8. **FG-11 两处同 commit**:`ALLOWED_FIELDS_BY_TYPE` + `OPTIONAL_FIELDS_BY_TYPE` 一起改,否则 regen schema 拒绝新字段(已在 Phase 1 标注)。

---

## 八、向后兼容 / 版本策略

- **Schema 全部由 `section_pipeline.py` 常量经 `python tools/generate_section_schemas.py` 生成,勿手改 JSON**。`generate_section_schemas.py` import `METHOD_KINDS` 并用 `STAGE_B_RELATION_ORDER` —— 扩 `METHOD_KINDS`/`RELATION_MATRIX`/`FINDING_ROLES` regen 时自动传播,**例外**:`STAGE_B_RELATION_ORDER`(`:81`,手改)和 `OPTIONAL_FIELDS_BY_TYPE`(`:48-52`,FG-11 须加 Finding)。每次改常量后 regen 并**同 commit** 提交 JSON。
- **IR 版本字符串硬编码两处**:`section_pipeline.py:1389`(extraction_notes 字面量)+ `:2846`(validator 等值检查)。两处必须同切,否则 validator 拒绝新输出。E1 下两处保持 0.9 到 Phase 6 再同切 0.10。
- **已抽语料**(`_200_papers_v2` 的 200、`ros_ai_8x100_v0.9` 的 764):E1 下到 Phase 6 切版前仍是合法 0.9;切后为 legacy(0.10 validator 拒其 ir_version)。**不做回迁,只在 0.10 一次性重抽 764**。
- **`FORBIDDEN_UNIT_TYPES`**:含退役 `Proposition`/`Entity`/`Setting`/`Metric`/`Claim`。推荐路径(method_kind/role,不加新类型)完全绕开;若走 B3 须避免名碰撞 + 从 FORBIDDEN 移除新名。
- **Renderer**(`tools/render_extraction.py`):新可选字段/新边类型若 renderer 忽略未知字段则无害渲染;新体裁(benchmark 贡献、定理)应在 Phase 6 小幅呈现。

---

## 九、测试策略

`issues/test-corpus-by-issue/` 专为 per-issue 回归而建:12 个 `FG-NN_*/` 文件夹,各含 `papers/<id>.md`(gitignored 源,重抽输入)+ `<id>.before.json`(当前 0.9 输出作 pre-fix 基线)+ `MANIFEST.md`(选篇 + 命中证据 + 每 issue 的 jq 配方)。

- **Phase 0**:对当前 0.9 HEAD **重新快照**每个 `*.before.json`(committed 基线可能陈旧),并对每个 FG 文件夹跑语料卫生过滤(剔 `Title_Page`/`Preface`/`007`/`030`/`033`/`065`)。记录每 FG 的 MANIFEST jq 基线指标。
- **每阶段后**:只重抽受影响 FG 文件夹(P1→FG-03/11/08;P2→FG-04/12;P3→FG-01[+复查 FG-03];P4→FG-02/10;P5→FG-09/05/07;P6→FG-06 + 全 764)。
- **per-issue 通过判据(MANIFEST jq)**:如 FG-03「选中篇 Document.role 不再 100% research_article」;FG-01「benchmark/数据集贡献不再 method_kind=algorithm 且无断连同名 ExperimentSetup 双胞胎」;FG-04「builds_on 边出现、part_of-coercion 计数下降」;FG-11「comparative Finding 带 magnitude/direction」。
- **交叉回归守卫(关键)**:每阶段后**也重抽未针对的 FG 文件夹**,确认 before/after 指标不变 —— 最大风险是修一个体裁退化了经验-CV 主流(如 FG-1 的 `ROLE_TO_TYPE` 例外误让正常方法变 ExperimentSetup)。12 文件夹构成体裁覆盖矩阵,任何 FG 指标变差 = blocker。
- **常规**:每阶段后跑 `.venv/bin/python -m unittest tests.test_section_pipeline` + smoke test(`tests/test_section_extraction.py`)。`_assign_resolves`/twin-merge/`_drop_empty_scores_measures` 有专门单测须保持绿。
- **最终门(Phase 6)**:全 764 重抽仍 **764/764 有效**(pipeline-never-crashes 不变式)+ 呈现目标分布漂移。

---

## 十、风险

1. **排序陷阱**:先修 FG-9(因它是「根」)会逼着在 FG-1/FG-2 类型之家落地后**二次重写** `_assign_resolves`/`normalize_census_nodes`。反之 FG-2 只做 `method_kind=theorem` 是陷阱(证明仍无法证明)——FG-2 必须 method_kind + Finding.role + proves/assumes 边 + value_kind 一起发或不发。
2. **模型学习行为**:relation-pass 现教 builds_on→part_of 强制,反转后 deepseek 可能仍 coerce。缓解:FG-12 确定性回填不依赖模型服从,提供边的下限。
3. **守卫削弱(FG-10 D2)**:放宽非空 scores Measure 校验有重新放进幻觉空 Measure 的风险。D1 避开;D2 须紧 status-gated 而非一刀切。
4. **跨体裁回归**:每个 FG-1/FG-2 的 `ROLE_TO_TYPE`/`METHOD_KINDS` 例外有误伤经验-CV 主流的风险。审计校准明说榜单 + 多 split 迁移干净,不可退化 —— 12 文件夹交叉回归守卫是防线。
5. **普遍度虚高(语料卫生)**:误抓非 AI 文档 + 目录↔内容错位虚高了 no-Measure/退化 Measure 计数(它们支撑 FG-1/FG-6/FG-10 范围)。为真实占比小的体裁建一等类型(B2/B3)是过度工程 —— **Phase 0 卫生过滤必须先于任何新类型决策**。
6. **静默丢失第二半**:FG-10 的 ~360 条悬挂跨段边(并行三段一致性,是内存 `method-segmentation-severs-part-of` 的推广)**不在** D1/D2 Measure 工作内,是独立、更难的跨段对账,本计划**标记但延后** —— 别让它藏进 FG-10 的「完成」里。
7. **切版成本**:E1 把一次全 764 重抽批到 Phase 6;若某 Phase 3/4/5 改动非干净 additive,「保持 0.9 到 P6」破裂,被迫提前切版 + 部分重抽 —— 每阶段 diff 须审 additive-only。
8. **FG-8 未验证**:issues 文档标 FG-8 是 critic 发现非 finder 审计;prompt-only 修复假设矩阵已许端点(已确认 `RELATION_MATRIX:235-236`),但推荐的复核(analysis vs method 论文的 about/supports 端点分布)必须先跑,以防真实缺口在矩阵级而非 prompt 级。

---

## 十一、下一步(决策落定后)

1. 用户敲定 **FORK-A(改造深度 A1/A2/A3)**、**FORK-B(类型 vs role)**、**FORK-E(版本/重抽)** —— 这三个 gate 全局。FORK-C/D/F 已有强推荐(C2 派生 / D1 上浮 / F2 reference 回填优先),无异议即按推荐走。
2. 跑 **Phase 0**(语料卫生 + 真实普遍度实测 + before.json 重快照)—— 它**校准 FORK-B**,且给每阶段可复现基线。
3. 按 Phase 1 → 6 推进,每阶段:改代码/常量 → regen schema(若动常量)→ 重抽受影响 FG + 交叉回归 + 单测 + smoke → 确认 per-issue 判据。
4. Phase 6 切 0.10 + 全 764 重抽 + 更新 `docs/`(新增 0.10 规格 delta)+ 内存 `genz-field-design-audit.md` 标记「修复进行中/已完成」。

> 完整的 42 条结构化审计结果在 workflow 任务 `wn1zctf2h`;本次计划生成在 `wf_e30dce6e-99e`。
