# 下游消费端功能构想

> 基于抽取结果 `tests/cvpr_semantic_segmentation_200_papers`(200 篇 CVPR 语义分割论文,2013–2025)的下游功能 brainstorm。

我先把语料的"形状"摸清楚了,这样建议才不是泛泛而谈。关键结论是:**这不是 200 篇孤立论文,而是一个「单领域(语义分割)+ 跨 13 年(2013–2025)」的纵向语料**。单篇渲染(`extraction.html`)已经有了——真正没被开采的价值几乎全在**跨论文 / 语料级**。

顺手验证了跨论文 join 到底可不可行(这是大部分高价值功能的地基):

| 信号 | 实测 |
|---|---|
| 论文数 / 各自的 contribution | 200 / 200 |
| 全语料 `scores[]` 行数(系统×基准×指标×数值) | **17,052** |
| 不同 baseline 名(`compared_against`) | 1,419,其中 **36 个精确等于另一篇论文的 contribution**(仅做了小写去符号匹配,是下限) |
| 复现率最高的数据集 | Cityscapes 79、PASCAL VOC2012 63、ImageNet 45、SYNTHIA 23、COCO 21、GTA5 19 |
| 指标名 | 1,003 个,但绝大多数是 `mIoU` 的写法变体 |

也就是说:**实体确实在论文间反复出现**(因为是单领域),`compared_against`/`builds_on`/`scores` 让你能把论文织成一张图。下面按"吃哪部分结构"分层给。

---

## 一、跨论文知识图谱(地基,优先级最高)

把 200 篇拼成一张图,这是通用「向量库+PDF」做不到、而恰好吃这套 IR 结构的东西。

- **方法谱系图**:用 `builds_on`(祖先)+ `compared_against`(对手/被超越)把 contribution 连成有向图。能回答"FCN→PSPNet→…→某 2025 方法"的演化链,以及"谁站在谁肩膀上"。
- **影响力排名**:某方法被多少篇当 baseline = 朴素影响力。实测 top 是 `sec/pspnet/boxsup/ficklenet/fcn/ccnn`——正好是领域经典,说明信号靠谱。
- **"谁该跟谁比"推荐**:给定一篇/一个新方法,根据它的 task + dataset 邻域推荐应该对比的 baseline(用现成的 `compares_to` 共现)。

> 前置工程见文末——`compared_against` 名字未归一(1419 个),`provides_unit_ids` 抽样看到是空的(和 memory 里"reference linking 部分 deferred"一致),所以图的连边要靠 `cite_keys` + 名字模糊匹配补齐。

## 二、定量榜单 / SOTA 演进(数据最厚,17K 行)

- **逐基准 leaderboard**:每个 `ExperimentSetup(dataset/benchmark)` × `Measure` 一张榜,行来自 `scores[].{variant,value,system_id,setup_id}`。
- **SOTA-over-time 曲线**:把榜单按论文年份铺开 → "PASCAL-5i 上 1-shot mIoU 逐年最高值"这种趋势线,一眼看清领域进展速度和平台期。
- **表格重建 / 一致性校验**:`setup_id` 保证了多 split 不被压成一个数,可以反向重建论文里的对比表,甚至交叉核对"A 论文报告的 B 方法分数"和"B 论文自报分数"是否一致(数据可信度信号)。

## 三、结构化检索与浏览(吃 discovery arc)

discovery arc(problem→method→evidence→`resolves`)天然就是结构化查询的字段:

- **faceted 检索**:按 `task`/`dataset`/`Method.method_kind`/`Finding.role` 过滤。例:"找所有 *weakly-supervised* 且在 *PASCAL VOC* 上、`comparative` finding 里赢过 FickleNet 的方法"。
- **一句话卡片流**:每篇的 `document.thesis` + `Problem.description` 就是现成的 TL;DR 卡片,比摘要更聚焦。
- **结构化 RAG**:以 unit 为检索单元、`provenance` 的 `§` 标记做引用锚——回答带可点击出处,比 chunk-level RAG 精确得多。

## 四、趋势 / 综述 / 洞察聚合(语料级洞察)

- **数据集采用时间线**:`dataset` 角色 × 年份 → "Cityscapes 何时取代 PASCAL 成为主战场"、新基准的兴衰。
- **研究问题地图**:聚类 200 个 `Problem.description` → 子方向版图(弱监督 / 域适应 / 全景 / 视频 / 3D点云 / few-shot / zero-shot…),并看每个子方向逐年热度。
- **Findings 摘要器**:聚合全语料的 `failure_mode` finding = "这个领域公认的坑";聚合 `ablation_finding` = "哪些组件被反复证明有用"。这是单篇读不出来的元知识。
- **自动 related-work / 迷你综述**:给定一个子方向,用图+thesis+findings 草拟一段带引用的相关工作。

---

## 推荐

**从「一 + 二」入手**,因为:(a) 数据最厚、最独特(17K 分数行 + 单领域实体真的复现);(b) 它俩是地基——三、四都能复用同一张实体表和同一个榜单。先做一个**领域仪表盘**:左边方法谱系图,右边可选基准的 leaderboard + SOTA 曲线,点节点跳到单篇 `extraction.html`。

**唯一的硬前置:实体归一(entity resolution)**。数据已经把问题暴露了——1419 个 baseline 名、1003 个指标名(其实就几个 mIoU 变体)。需要一个归一层:方法名(`cite_keys`→名字模糊匹配)、数据集名、指标名各做一张 canonical 表。这层一旦有了,上面所有跨论文功能都解锁;没有它,leaderboard 会碎成沙子。

可先做的原型方向:
- 写个脚本把 17K 分数行 + 年份聚合成**一个基准的 SOTA 演进表/曲线**(最快见效,顺带验证指标归一的难度);或
- 先建**方法实体归一 + 谱系图的边表**(地基,产出一个 `nodes.json`/`edges.json` 供前端用)。
