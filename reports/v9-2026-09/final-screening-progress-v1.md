# v9 最终筛选进度（未完成）

窗口：2026-09-01 至 2026-09-30；固定候选池：3,987 个 DOI。

**本文件不是九月最终收录结果。多数旧材料只保存摘要可用性、字数、哈希或关键词，不能替代逐篇语义审读。**

## 当前进度

- 全池硬检查排除 746 篇：日期窗外 293、非目标类型 355、明确通知标题 98。
- 已重新读取并审读旧候选 25 篇：收录 20、主题排除 3、边界待复核 2。
- 全池当前排除 749 篇，review 3,218 篇；其中 3,214 篇尚未主题审读，2 篇边界不确定，2 篇已知缺摘要。
- 20 篇为目前已确认的收录下限，不能作为九月最终数量。

## 已确认候选

| DOI | 期刊 | 类别 |
|---|---|---|
| 10.1038/s42005-026-02852-9 | Communications Physics | core |
| 10.1063/5.0351619 | Chaos | core |
| 10.1103/c44l-89p7 | Physical Review E | transferable_application |
| 10.1073/pnas.2537815123 | Proceedings of the National Academy of Sciences | transferable_application |
| 10.1063/5.0347364 | Chaos | core |
| 10.1126/science.aeg3946 | Science | core |
| 10.1063/5.0351862 | Chaos | core |
| 10.1063/5.0349918 | Chaos | core |
| 10.1103/tmkq-33c4 | Physical Review Research | transferable_application |
| 10.1063/5.0342298 | Chaos | core |
| 10.1103/p6qp-2s9f | Physical Review Research | transferable_application |
| 10.1073/pnas.2614238123 | Proceedings of the National Academy of Sciences | transferable_application |
| 10.1063/5.0346196 | Chaos | core |
| 10.1063/5.0349270 | Chaos | core |
| 10.1137/26m1837459 | SIAM Journal on Applied Dynamical Systems | core |
| 10.1137/25m1821569 | SIAM Journal on Applied Dynamical Systems | core |
| 10.1103/rt96-mb8q | Physical Review E | core |
| 10.1063/5.0338836 | Chaos | transferable_application |
| 10.1063/5.0337453 | Chaos | core |
| 10.1063/5.0348359 | Chaos | core |

## 恢复工作

- 使用 final-screening-progress-v1.json 的 pending_dois，不能重复从旧25篇开始。
- 按 DOI 从已有确认来源临时读取摘要，读取后立即保存分类理由、简短证据、输入哈希和来源。
- 不落盘完整摘要，不以 description、搜索片段或关键词命中替代语义判断。
- 新批次另存文件，保留旧文件；最终必须分别报告未审读、证据缺失和判断不确定。
- 尚未修改或发布生产网页。
