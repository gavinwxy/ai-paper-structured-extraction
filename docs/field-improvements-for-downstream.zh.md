# 为稳健支持下游应用,抽取结果的字段提升

> 承接 [`downstream-consumer-features.zh.md`](./downstream-consumer-features.zh.md)。要稳健支持那份文档里的跨论文应用(知识图谱 / leaderboard / 检索 / 趋势),当前 IR 在字段上还缺什么。结论基于对 `tests/cvpr_semantic_segmentation_200_papers`(200 篇)的实测。

## 总判断

当前 IR 是**为「单篇保真」优化的**,而那些应用全是**「跨篇聚合」**。聚合需要三类字段——**身份链接、可比性、时间轴**——而这三类恰恰是单篇抽取没有动机去产出的(模型读一篇论文时,根本不知道 "PANet" 在语料里还有另一篇是它的主场)。所以缺口不是抽得不准,而是**缺了把论文焊到一起的"接缝字段"**。

### 已经够好、别动的

- discovery arc 用于检索/卡片完全够。
- `system_id`→role 解析良好:自家结果 5451 行 / baseline 9533 行,**88% 的 score 行能判定是自报还是引用**。
- `setup_id` 多 split 处理 **96% 填充**。
- `value` 已经 **99%+ 可解析**(剩下的 `.378` 是省略前导零,`float()` 一行搞定)——**数值类型不是问题,别过度工程**。

## 实测缺口数据

| 检查项 | 实测 | 影响 |
|---|---|---|
| Method unit 带 `cite_keys` | **0 / 4019**(而 census 节点 25/37 带) | 跨篇 join key 被 assembly 丢了 |
| `provides_unit_ids` 填充 | 抽样为空(reconcile 未点火) | 引用↔unit 链接断 |
| metadata `year` / `venue` | **0 / 200**(只活在目录名) | 趋势 / SOTA-over-time 无时间轴 |
| 不同 baseline 名 | 1419 | 无跨篇稳定身份 |
| 不同指标名(含 "iou" 的拼写) | 976(其中 399 种 "iou" 拼写) | 词表碎片化 |
| `variance` 填充 | **1%**(224 / 17052) | 误差棒几乎全丢 |
| Measure 方向位 `higher_is_better` | 无此字段 | 无法自动排名 |
| 可比性轴(shots / backbone / 监督) | 埋在 `variant` / `data_split` / `training_config` 自由文本 | 跨篇 SOTA 表不可比 |

## 缺口分层(按杠杆排序)

### Tier 1 — 身份与链接(卡死整个知识图谱)

- **`cite_keys` 在 census 里有、却没传到 unit**:census 节点 25/37 带 `cite_keys`,材化后的 unit **0/4019** 带。这是最便宜的高杠杆修复——join key 上游已经算出来了,assembly 丢了。顺带:抽样里 `provides_unit_ids` 是空的(reconcile 没真正点火)。**先把它持久化到 unit + 让 reconcile 真的填上**。
- **方法/数据集/指标没有跨篇稳定 id**:`cite_keys` 只解决*篇内* join(ref→unit),解决不了*跨篇* join——A 篇的 baseline "PANet" ↔ B 篇的 contribution "PANet"。证据:1419 个 baseline 名、976 个指标名、光 "iou" 就 399 种拼写。要么给一个全局 canonical id,要么至少在 baseline 上带 **reference 的 DOI/title**,好让它去和"提出它的那篇"对齐。

### Tier 2 — 分数可比性(卡死可信 leaderboard)

- **Measure 没有方向位**:缺 `higher_is_better`。不知道 mIoU↑ 还是 error↓/params↓,就没法自动排名。
- **可比性轴埋在自由文本里**(最大的正确性风险):同样是 "mIoU on PASCAL-5i",可能一行是 1-shot/ResNet、另一行是 5-shot/ViT——**不可比**。但 shots / backbone / 监督方式现在散在 `variant` 串("CAPL+PSPNet"、"CAPL-ViT")、`data_split` 名、和 `training_config` 的描述文本("ViT-B/16 backbone, 512×512…")里。需要把它们**提成 score 行或 setup 上的 typed 字段**(至少 backbone/shots/supervision),否则跨篇拼出来的 SOTA 表是错的。
- **variance 几乎全丢**:只有 1% 填了。能报的误差棒尽量留。

### Tier 3 — 元数据 / 时间轴(卡死趋势 & SOTA-over-time)

- **metadata 只有 title/authors/resources,`year` 和 `venue` 都是 0/200**。年份现在只活在目录名里——这是个 out-of-band 的 hack。SOTA 曲线、数据集采用时间线全靠年份。**把 year/venue(+ 论文级 DOI/arXiv id 供外部去重)提成正式字段**,metadata 这一步本来就在读论文,顺手的事。

### Tier 4 — 受控词表归一(改善 faceted 检索 & 所有聚合)

- dataset/task/metric 名都是表面形(PASCAL-5i / PASCAL VOC 2012 / pascalvoc 指同源数据但各篇各写)。要么闭集 vocab + alias 表,要么后处理归一映射。

## 架构上的看法(关键)

**别把归一塞进单篇 prompt。** 把缺口按"是否单篇可知"切两层:

1. **单篇可知 → 加在抽取/assembly 里**(便宜、立刻能做):`cite_keys` 传到 unit、`provides_unit_ids` 真填、`year`/`venue`、Measure 的 `higher_is_better`、backbone/shots 的 typed 标注、variance 召回。这些模型读一篇就知道。

2. **只有看全语料才知道 → 新建一个"语料 consolidation 阶段"**:跨篇实体归一 + canonical 词表 + 把 baseline 焊到它的主场论文。canonical id 本质上是相对整个语料定义的,**强行下推到单篇 prompt 只会拖垮单篇精度、且逻辑上做不到**。这一层应该吃 200 份 IR、吐出 `canonical_methods.json` / `aliases` / 焊好的边表,供前端用。

## 一句话总结

**Tier 1a + Tier 3 几乎零成本**(持久化已有数据 + metadata 加两个字段),建议立刻做;**Tier 2 的可比性轴是 leaderboard 正确性的命门**,值得在 prompt 里加结构;**真正的跨篇归一别污染单篇**,放到独立 consolidation 阶段。
