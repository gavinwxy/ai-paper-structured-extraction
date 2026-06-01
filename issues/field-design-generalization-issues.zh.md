# 字段设计泛化性问题汇总(section-ir-0.9)

**评估语料:** `production-outputs/ros_ai_8x100_v0.9`(764/765 篇有效,8 会议:AAAI/ACL/CVPR/ICLR/ICML/IJCAI/KDD/NeurIPS,各 ~100 篇)
**模型:** `deepseek-v4-pro`(thinking-off) · **日期:** 2026-06-01
**方法:** 全 764 篇确定性退化探针(`tests/_genz_probe*.py`,gitignored)+ 11 个 agent 定性审计(每条结论对真实文件对抗式验证)+ 完备性 critic(workflow 任务 `wn1zctf2h`)。
**关联:** 内存 `genz-field-design-audit.md`;不同于 `current-extraction-issues.md`(后者是单批次的 schema 有效性 / 抽取召回问题,本文件是**跨体裁的字段表示能力**问题)。

---

## 总体结论

框架的字段设计在 CVPR 语义分割语料上调出,**每一根字段轴都隐含「贡献=可训练计算产物、证据=数值榜单、指标=越高越好」的假设**。对占多数的经验方法类论文良好;但对 benchmark/数据集类、理论/证明类、分析/洞察类、多目标/成对评测类论文(主导 ACL/NeurIPS/ICML/IJCAI/KDD)会**系统性地误 type、强行套用或静默丢失**核心内容。

重要校准:**没有真正的 blocker**。流水线本身稳健(764/765 全部通过校验),所有问题都是**表示保真度**缺陷(误 type、碎片化、丢失),不是流水线故障。审计中最初标为 blocker 的 3 条均被对抗验证下调为 major。

经审计:**42 条候选 → 38 条确认为真实字段设计缺口**(其余 4 条被验证否决或归因于语料卫生)。

---

## 问题汇总表

| ID | 问题 | 出错字段 | 严重度 | 普遍度 | 验证状态 |
|---|---|---|---|---|---|
| FG-1 | 贡献必须是 Method → benchmark/数据集/资源类被误塞进 `Method[algorithm]` 并复制成无连接的 ExperimentSetup 双胞胎 | `ROLE_TO_TYPE[contribution]=Method` + `method_kind` 无 resource 值 | **major** | common(~40+ 纯资源篇) | confirmed |
| FG-2 | 理论/证明类无家可归:定理/界/定义→`Method[algorithm]`+伪造 I/O;符号界→Measure 伪榜单;证明无法证明 | 缺 Theorem/Result 类型 + `method_kind`/`Finding.role` 无定理值 + `scores.value` 无类型 + 关系矩阵无 proves/assumes | **major** | 理论切片内 common,全语料 occasional | confirmed |
| FG-3 | `Document.role` 完全死轴:764/764 全是 `research_article` | `Document.role`(硬编码字面量) | **major** | pervasive(100%) | confirmed |
| FG-4 | 关系矩阵缺依赖边:`builds_on` 无对应边(~53% 塞进 part_of 假包含、~37% 孤儿);`compared_against` 混淆"跑过的baseline"与"相关工作引用" | 关系矩阵缺 builds_on/uses;Method.role=builds_on 与边集脱节 | **major** | pervasive | confirmed |
| FG-5 | 分析/机理类论文的贡献本身是 Finding,却被迫提名工具或空洞"Analysis" Method 当主干 | 单 Method contribution 主干;Finding 不能当 arc 根 | **major** | 该体裁内 common | confirmed |
| FG-6 | scores 行模型对非榜单评测不适配:成对/胜率对手塌进 variant 串;无 judge 轴;无多目标轴 | `scores.system_id`(单值)+ 无 judge/opponent 轴 + Measure 无多目标类别 | moderate | occasional(增长) | confirmed(范围收窄) |
| FG-7 | single-trunk/single-arc 骨架副作用:`resolves` 退化成扇形;多个 co-equal 方法只能靠 part_of 假包含 | 单 Problem/单 contribution 基数 + 装配合成 resolves | minor–moderate | resolves 扇形 pervasive 但**语义无损** | confirmed(强版本被否决) |
| FG-8 | 边语义近乎单态:`about` 几乎只能 Finding→Method;`supports` 几乎只能 Measure→Finding,无多步论证链 | `about`/`supports` 的端点类型矩阵过窄 | **major** | pervasive | critic(未单独审,需复核) |
| FG-9 | census 结构上对 Problem/Finding 失明(只规划 Method/ExperimentSetup/Measure)→ 结果中心型论文在 typing 之前就被锁成器械中心骨架 | census `type` 轴 + `spine_summary` 只有 central_contribution | **major** | pervasive(架构级) | critic(根因) |
| FG-10 | 静默丢失(比强制套用更危险):空 scores 的 Measure 被丢、自创指标 must-node 未覆盖、并行填充产生悬挂边被丢 | `validate_section_ir` 要求 Measure 非空 scores;并行三段填充一致性 | **major** | pervasive(只在 extraction_notes 留痕) | critic + 探针确认 |
| FG-11 | Finding 无量化载荷:只有 `{statement, role}`,正向/零结果在结构上无法区分,且不连到支撑它的具体 score 行 | `Finding` 字段集 + `supports` 非行级 | moderate | pervasive | critic |
| FG-12 | reference 关系词表更丰富却被搁置:references 带 `roles{extends,contrast,uses_method,...}`+`stance`,从不回填到单元边 | reference `relation.roles` 与 `RELATION_MATRIX` 互不调和 | moderate | pervasive | critic(FG-4 的修复路径) |

附:`Measure.unit`(指标名 vs 物理量纲混用)与 `objective_function`(~5% 填充,近死轴)是同一种"词表拟合 CV 频率"病的次要表现。

---

## A. 核心结构性问题(详)

### FG-1 — 贡献必须是 Method,benchmark/数据集/资源类被误表示

**严重度:** major · **普遍度:** common

**现象:** 当论文的真实贡献是一个 benchmark/数据集/atlas/分类法时,它被强制 type 成 `Method`(常带 `method_kind=algorithm`),并且常被**第二次**材化成一个同名 ExperimentSetup,两个单元之间没有任何关系边——招牌成果碎成两半。

**根因:** `ROLE_TO_TYPE['contribution']='Method'` 把文档根硬连到 Method 类型;`METHOD_KINDS` 没有 `dataset/benchmark/resource/taxonomy` 值,所以非算法产物落到 catch-all `algorithm`;同时 Measure 的 `setup_ids`/`scores.setup_id` 只能指向 section-local 的 ExperimentSetup,所以一个 benchmark **必须**再获得一个 ExperimentSetup 化身才能挂分数——双胞胎是结构强制的。

**证据:** 贡献 762/762 全是 Method(0 个 ExperimentSetup 贡献);贡献 `method_kind` 分布 425 algorithm / 213 model_architecture / 70 training_strategy / 11 objective_function / 43 null;94/764 贡献-Method 的名字/描述含 benchmark|dataset|taxonomy|survey|corpus 字样;9–16 篇贡献-Method 的精确名同时是一个 ExperimentSetup。典型:`GraspNet-1Billion`(数据集)→ `algorithm`;`Chart-HQA` 同时是 Method(contribution)和 ExperimentSetup(benchmark)且无连接边;`Z-Brain atlas`(资源)→ `algorithm`。

**修复:** 让 `contribution` 角色可落在 ExperimentSetup(dataset/benchmark)或新增 Resource 类型上,把"贡献"(论证角色)与"Method"(类型)解耦;最小化:`method_kind` 增 `{dataset,benchmark,resource,taxonomy}` 并在贡献是资源时抑制算法形字段(inputs/outputs/objective_function),且给双胞胎加一条连接边或抑制重复材化。

### FG-3 — `Document.role` 完全死轴

**严重度:** major · **普遍度:** pervasive

**现象:** 764/764 篇全部 `research_article`;`review/benchmark_survey/meta_analysis/methodology` 四个枚举值结构上不可达,即使在纯 benchmark/综述/position 论文上也不触发。

**根因:** `Document.role` 在 `build_document`(`section_pipeline.py:1357` 附近)被写成硬编码字面量 `research_article`,census 从不对文档体裁分类——模型根本没机会赋值。

**修复:** 要么由 census 从 `spine_summary` 派生体裁(贡献是 benchmark/dataset/taxonomy/survey ⇒ benchmark_survey/review),要么直接删掉这个枚举(目前纯误导消费者"体裁已捕获")。与 FG-1 联动:体裁一旦能 fire,benchmark 论文可在文档层被标记并走非 Method 贡献路径。position/opinion 体裁还需新增一个角色值。

### FG-5 — Finding 不能当 arc 根

**严重度:** major(该体裁内) · **普遍度:** common(机理/分析/经验研究类)

**现象:** 当贡献本身是一个科学发现(机理可解释性、"X 真的是瓶颈吗"、经验分析)时,discovery arc 强制要有一个 Method 主干,于是模型提名一个次要工具、或一个空洞的"Analysis" Method,真正的结论被降格成叶子 Finding,`resolves` 闭到工具上而非闭到发现上。

**修复:** 允许 Finding(或专门的 Result 类型)直接当 arc 的 contribution/主干,让 `problem→finding→evidence` 成为一等 arc 形态,`resolves` 可直接闭合 Problem←Finding 而不强求中间 Method。

---

## B. 理论/非经验内容(详)

### FG-2 — 理论/证明类无家可归

**严重度:** major · **普遍度:** 理论切片内 common(NeurIPS/ICML/IJCAI 理论占该会 ~8–28%),全语料 occasional · **graceful degradation,非崩溃**

五个并发子症状,同一根因(没有理论原生表示):

- **(a) 定理/定义/引理 → `Method[algorithm]`**,并被伪造 `inputs[]/outputs[]/implementation_notes`(对静态命题语义错误)。`Proposition` 类型在 `FORBIDDEN_UNIT_TYPES` 里(因在 CV 语料从不 fire 被剪掉);`method.md:30` 明确指示证明用 `method_kind=algorithm`。
- **(b) 符号界 → Measure 伪榜单**:`scores.value` 是无类型字符串,塞进 `O(n^6)`/`PSPACE-complete`/`2/Δ log T`;`variance` 普遍为空;`comparison_direction` 被迫给方向(模型不用 `unspecified` 逃生阀:0/7)。
- **(c) `Finding.role` 无定理值**:被证明的定理散落到 comparative/mechanistic/ablation/`modeling`(modeling 成了形式结果的最近匹配),丢失"已证 vs 观察到"的认识论区分。
- **(d) `supports` 禁止 Method→Finding**:当定理被材化成 Method 时,招牌理论结果与它的证明在图上断开(被验证为"证明无法证明")。
- **(e) ExperimentSetup substrate 角色 `{dataset,benchmark,task}` 无理论基底槽位**:图类/博弈族/PDDL 规划域/构造实例/分布假设regime 被误标为 dataset/benchmark/task。

**证据:** `002_NeurIPS` 把定理材化成 Method 带伪造 I/O;`087_IJCAI` 68 个 compared_against 只有 1 个带 score 行(baseline 政策对理论失效,捕获了几十个无分数的书目定理);符号界值串出现于 ~8% 理论会议论文(23/300,保守下界)。

**修复:** 新增 Theorem/Result 一等类型(或 `method_kind`/`Finding.role` 增 `{theorem,lemma,definition,bound}`);`scores` 增 `value_kind ∈ {numeric,symbolic,asymptotic,qualitative,curve}` 让 value 可持表达式、`comparison_direction` 可空;新增 `proves`/`establishes`(Method→Finding)与 `assumes` 关系;对非实现性结果放宽 `implementation_notes` 必填;substrate 角色增 `theoretical_setting/structural_class`,可选 `assumptions` 字段。

---

## C. 关系与论证图(详)

### FG-4 — 关系矩阵缺依赖边 + `compared_against` 语义过载

**严重度:** major · **普遍度:** pervasive

**现象:** census 已给 Method 标了 `builds_on` 角色,但**关系矩阵里没有对应的边**——这些外部先验依赖 ~53% 被塞进 `part_of`(谎称是子部件)、~37% 成图上孤儿、~7% 塞进 `compares_to`;模型甚至主动尝试写 `builds_on` 边 11 次,全被 `_drop_invalid_relations` 丢弃。另外 `compared_against` 把"真正跑过、有分数的 baseline"与"只是相关工作里被提到的引用"混为一谈:28%(1747/6187)的 compared_against 单元无任何 score 行,16.3%(121/741)的论文零个有分数的 compared_against(ACL 高达 24%,position/综述类如某 95 个无分数)。

**修复:** 新增 `builds_on`/`uses` 边(Method/ExperimentSetup → Method,stage B 编写),与 `part_of`(内部组合)、`compares_to`(竞争)区分——直接复用 census 已有的 `builds_on` 角色作为源集。把 `compared_against` 拆成 `evaluated_baseline`(出现在 score 行)vs `related_work`(定位引用,无数),或把 compared_against 的材化 gate 到真有 Measure 分数的系统。

### FG-8 — 边语义近乎单态

**严重度:** major · **普遍度:** pervasive · **状态:** critic 发现,**未被 finders 单独审计,建议复核**

**现象:** `about` 边几乎只走 Finding→Method(60 篇样本:479×),→ExperimentSetup 仅 3×、→Measure 仅 2×;`supports` 几乎只走 Measure→Finding(286×),Finding→Finding 仅 8×。⇒ 关于数据偏差/指标退化/某现象(而非某产物)的发现无处可挂,只能强行挂 Finding→Method;多步论证("观察 A,故结论 B")塌成一袋无推导结构的兄弟 Finding。**节点分类被审了,承载论证的边语义没被审。**

**复核入口:** 对 `analysis`/`benchmark` 论文 vs 标准方法论文,统计 `about`/`supports` 端点类型分布;对照 `RELATION_MATRIX` 与 `STAGE_C_RELATIONS_BY_SECTION`。

**修复(候选):** 扩展 `about`/`supports` 的端点类型矩阵(允许 Finding→ExperimentSetup/Measure、Finding→Finding 推导链)。

### FG-12 — reference 关系词表更丰富却被搁置(FG-4 的现成修复路径)

**严重度:** moderate · **普遍度:** pervasive

**现象:** `03_references.json` 的 `relation.roles ∈ {background, related, uses_method, baseline, uses_data, motivation, contrast, extends, future_work}` + `stance ∈ {neutral, supportive, critical}`(80 篇样本:background 1196 / uses_method 574 / baseline 344 / contrast 79 / extends 28 / critical 84)**比单元图的 Method.role 与边集丰富得多**,但两套词表互不调和——模型能识别出 extends/contrast/critical,却无处在核心图里记录。`reconcile_reference_units` 已用 cite_keys 把 reference 连到 unit,但**不把 reference 角色传播到单元边上**。

**修复:** 把 reference 角色回填为单元边(extends→builds_on、uses_method→uses、contrast/critical→带 stance 的 compares_to),即用现有信号补 FG-4 的依赖边,而非另造词表。

---

## D. 证据 / 度量模型(详)

### FG-6 — scores 行模型对非榜单评测不适配

**严重度:** moderate · **普遍度:** occasional(但在生成/对齐/人评中增长)

**现象:** 一个 score 行只有单个 `(system_id, setup_id)`,所以:**成对/胜率**比较(A-vs-B 的胜率)的对手塌进自由文本 `variant`(`042`:对手在 variant 里、value="win rate" 无数);**裁判轴**缺失——LLM-as-judge / 人评的裁判身份只能塞进 variant,即使裁判已被材化成一个 `inference_protocol` ExperimentSetup,score 行也引用不到它;**多目标**——精度 vs 开销/公平/安全的权衡读起来全是单调正向证据(`001_KDD YaART` 的"Side-by-side human preference" Measure 16 行,`YaART 2.3B RL` 出现 8 次对阵不同对手,无任何字段区分是哪一次成对比较)。

**修复:** score 行增可选 `opponent_id`(→Method)与 `judge_id`(→ExperimentSetup/Method),或加 `pairwise_preference` Measure 子类型 `{system_a_id, system_b_id, judge_id, value}`;给 Measure 加多目标类别轴(primary-quality / cost-efficiency / fairness / safety)以表达 axes 之间的张力。

> **校准(确实泛化得好,别动):** 榜单式比较(每系统绝对分 + `compares_to`)与多语种/多 split(逐行 `setup_id` + `data_split`,ZIPA 24 行 / TUMLU 96 行,列不被压成一个数)都迁移得很干净。FG-6 只在"被测量本身是两系统关系/带裁判/多目标"时才 fire。

### FG-11 — Finding 无量化载荷

**严重度:** moderate · **普遍度:** pervasive

**现象:** Finding 只有 `{statement, role}`,没有效应量/方向/置信/范围字段。comparative finding 把幅度藏进散文("Cappy 360M 在 11 个任务上胜过大几个数量级的 LLM");零/负结果与正结果除了一个"not"字外结构完全相同;且 Finding 不连到支撑它的具体 score 行(`supports` 是 Measure→Finding 的粗粒度,非行级)。⇒ 下游无法查询"效应量 > X 的发现"或"负结果"。

**修复:** Finding 增可选结构化载荷(magnitude/direction/polarity/effect_size/scope/confidence);把 `supports` 做成行级(指向具体 score 行)或增一条 Finding↔score 的引用。

---

## E. 架构层(详)

### FG-9 — census 结构上对 Problem/Finding 失明(上游根因)

**严重度:** major · **普遍度:** pervasive(架构级)

**现象:** census(stage A,全局视角的规划)的 `type` 轴只产出 Method/ExperimentSetup/Measure,**从不规划 Problem 与 Finding**(120 篇:1800 Method / 828 ExperimentSetup / 378 Measure;contribution 119/120 恰好一次);`spine_summary` 只有 `central_contribution`+`argument_flow`,没有"结果"的槽位。所以对分析/机理/理论类(招牌成果是 Finding/定理)的论文,**规划阶段已把骨架预先锁成器械中心**——这是 FG-1/FG-2/FG-5 强制套用的上游根因。即使补再多类型,一个不能规划"结果即贡献"的 census 仍会继续 coerce。

**修复:** 让 census 能把 contribution 节点规划为 Problem/Finding/Result(而不仅 Method/ExperimentSetup/Measure);`spine_summary` 增"headline result"槽位。

### FG-10 — 静默丢失(比强制套用更危险)

**严重度:** major · **普遍度:** pervasive(只在 `extraction_notes` 留痕)

**现象:** 强制套用(定理→Method)可见且可恢复;**丢失**则把贡献直接销毁:

- **311 个空 scores 的 Measure 被装配丢弃** + **167 个未覆盖 must-node**(多数是 `mea:` 论文自创指标:information_centrality_index、adaptive_f_beta、neighborhood_fairness…)⇒ **指标/评测贡献类论文的招牌指标既被误 type 又被丢掉**。
- **~360 条悬挂边被丢**(276 dangling evaluates / 70 supports / 15 about)+ 50 条 section anchor 被重置:并行三段填充(problem/method/evidence 仅共享 census registry)经常产生指向兄弟段未材化单元的边。这是内存 `method-segmentation-severs-part-of` 的推广(从 part_of 推广到 evaluates/supports/about),且 off-CV 更高(uncertain_assignments:ICML 369 / ACL 295 / ICLR 287 每 100 篇)。

**修复:** 别再静默丢弃空 scores 的 Measure(改为标记为 proposed-metric 或转成带载荷的 Finding/Result);把未覆盖的指标 must-node 显式上浮;审查并行段架构能否保持共享单元集一致(或在装配前做跨段引用对账)。

### FG-7 — single-trunk/single-arc 骨架副作用

**严重度:** minor–moderate · **普遍度:** resolves 扇形 pervasive 但**语义无损** · **状态:** 强版本被对抗验证否决

**现象与校准:** `resolves` 均值 3.43、最多 14、75% 篇 >1、749/749 全指向同一个 Problem。但验证表明这是 `_assign_resolves`(`section_pipeline.py:1748-1770`)**按设计**"每个 about-contribution 的 Finding 一条"产生的,连 CVPR 调参语料本身就 2–6 条/篇——**不是泛化回退、且语义无损**;single-Problem 在 763/764 篇成立,多贡献也常经 contribution/component 层级无损表示。**真正残留的窄缺口**:① arc 闭合只认单一 contribution 节点,所以一个被正确 `motivates` 的 benchmark 协同贡献拿不到 `resolves`(`041` 演示);② 缺一条 Method↔Method 的"co-contribution/alternative"边,两个 co-equal 方法只能靠 `part_of` 假包含(~4–5 篇确认,如 `013_ICML_2008`、`035_ICML_2025`)。

**修复:** 文档/校验别再把 resolves 描述成"单一收尾箭头"(或合成时只取 headline finding);允许少量 co-equal contribution(跨 Method/ExperimentSetup)并让 arc 扇出;新增 Method↔Method 的 alternative/co-contribution 边以替代假 part_of。

---

## 根因(贯穿主线)

1. **经验-CV 单一文化烙进每根轴**:`method_kind=algorithm` catch-all、`Measure.value` 标量、`comparison_direction`、`inputs/outputs`、`Document.role` 都默认"计算产物+经验标量",贡献一旦是定理/数据集/分类法/发现/智能体/多目标权衡就降级为伪造、死轴或丢失。
2. **死轴与过载是同一种病**:`Document.role`(100% 单值)、`objective_function`(~5% 填充)是死的;`Measure.unit`(指标名 vs 物理量纲)、`scores.variant`(对手+裁判+split 全塞进去)是过载的——词表拟合了 CV 频率而非更广文献的判别结构。
3. **节点分类被审、边语义(FG-8)与规划架构(FG-9)没被审**——最深的失败恰在这两处。
4. **强制套用 vs 静默丢失**是两种失败模式,审计天然偏重可见的前者;后者(FG-10)才会让知识图谱**无声地缺掉招牌成果**。
5. **single-trunk/single-arc 骨架 × 并行三段填充** = 一族缺口的结构生成器 + 跨段不一致(悬挂边、resolves 扇形、part_of 断裂)。

---

## 语料卫生警示(信任普遍度数字前必须处理)

相当一部分"论文"是**误抓的非 AI 文档或卷首页**:`Title_Page`、`Preface`、2010《African Journal of Psychiatry》调查、亚里士多德《论哲学》评注、一本美国史书、科学新闻摘要、非线性特征值讲义;并存在**目录名↔内容错位**(`007` 目录=X-WebAgentBench→内容=ST-WebAgentBench;`030`=ZAPBench→Z-Brain atlas;`033`=iNaturalist→心肺音;`065`…)。这**虚高了若干普遍度估计**(尤其 no-Measure / 退化 Measure),并使部分被引 paper_id 只能视作近似(结论因匹配抽取内容而成立,但 id 不可靠)。这是**独立于字段设计的输入侧问题**,应先做语料过滤。

---

## 优先级与修复路线(按 杠杆/成本)

1. **FG-3 `Document.role` 死轴**——派生或删除。最便宜,且解锁 FG-1 的体裁分流。
2. **FG-1 贡献可为非 Method**——让 contribution 落在 ExperimentSetup/Resource + `method_kind` 增资源值 + 连双胞胎。**解锁最大的受损体裁(benchmark/数据集)**。
3. **FG-9 census 能规划 Problem/Finding**——上游根因;不修则换再多类型仍 coerce。与 FG-1/FG-2/FG-5 联动。
4. **FG-2 理论原生表示**——Theorem/Result 类型 + `scores.value_kind` + `proves`/`assumes` 关系。解锁理论会议。
5. **FG-4 + FG-12 依赖边**——加 `builds_on`/`uses` 边并把 reference 角色回填(半成品已存在),拆 `compared_against`。
6. **FG-5 Finding-as-root**——解锁分析/机理类。
7. **FG-10 静默丢失上浮**——别再静默丢空 Measure / 未覆盖指标 must-node(防止知识图谱无声丢成果)。
8. **FG-6 / FG-11 / FG-8**——非榜单 score 轴、Finding 量化载荷、边语义矩阵扩展(FG-8 需先复核)。

> 完整的 42 条结构化结果(逐条证据 + 逐文件验证)在 workflow 任务 `wn1zctf2h` 输出中,可按需展开任意一条。
