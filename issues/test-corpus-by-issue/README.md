# 按 issue 类型组织的测试语料

每个 `FG-NN_*/` 对应 `field-design-generalization-issues.zh.md` 里的一个字段泛化问题,装着**触发该问题的代表性论文**,供修复后做针对性回归测试。

**布局:** `FG-NN_xxx/papers/<paper>.md`(源文献,re-extract 的输入)+ `<paper>.before.json`(当前抽取输出,作为修复前基线)。`MANIFEST.md` 列出选中论文 + 命中证据 + 测试配方。

`papers/` 已 gitignore(每篇 ~252K,源在 production-outputs/ 之外),仓库只跟踪 `MANIFEST.md` 与本 README。

**回归测试通用流程:** 修好某个 FG 后,对该文件夹重跑抽取并与 `.before.json` 对比:
```bash
.venv/bin/python -m production issues/test-corpus-by-issue/<FG-dir>/papers /tmp/<FG-dir>_after --model deepseek-v4-pro
# 再用 MANIFEST 里的 jq 检查项确认问题已消除、且其他字段无回归
```

| issue | 选中/全部命中 | 一句话 |
|---|---|---|
| [FG-01_contribution-must-be-method](FG-01_contribution-must-be-method/MANIFEST.md) | 25/77 | 贡献必须是 Method |
| [FG-02_theory-no-home](FG-02_theory-no-home/MANIFEST.md) | 25/50 | 理论/证明类无家可归 |
| [FG-03_document-role-dead-axis](FG-03_document-role-dead-axis/MANIFEST.md) | 18/88 | Document.role 死轴 |
| [FG-04_missing-dependency-edges](FG-04_missing-dependency-edges/MANIFEST.md) | 18/449 | 关系矩阵缺依赖边 |
| [FG-05_finding-as-contribution](FG-05_finding-as-contribution/MANIFEST.md) | 15/15 | Finding 不能当 arc 根 |
| [FG-06_non-leaderboard-eval](FG-06_non-leaderboard-eval/MANIFEST.md) | 20/86 | 非榜单评测不适配 |
| [FG-07_single-arc-co-contribution](FG-07_single-arc-co-contribution/MANIFEST.md) | 15/19 | 单 arc / 协同贡献 |
| [FG-08_monomorphic-edges](FG-08_monomorphic-edges/MANIFEST.md) | 12/114 | 边语义近乎单态 |
| [FG-09_census-blind-to-result](FG-09_census-blind-to-result/MANIFEST.md) | 12/64 | census 对结果失明(上游根因) |
| [FG-10_silent-loss](FG-10_silent-loss/MANIFEST.md) | 18/150 | 静默丢失 |
| [FG-11_finding-no-payload](FG-11_finding-no-payload/MANIFEST.md) | 15/190 | Finding 无量化载荷 |
| [FG-12_reference-roles-stranded](FG-12_reference-roles-stranded/MANIFEST.md) | 15/714 | reference 关系词表被搁置 |
