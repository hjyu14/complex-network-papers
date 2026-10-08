# 正式审核记录

当前网站从八个原始采集轮直接发布，正式复议及跨轮补采审计显式绑定相应旧判断；不以阶段汇总或“最新文件名”选取结果。

| 入口 | 职责 |
|---|---|
| [九月九刊](runs/2026-09/README.md) | 原始候选、覆盖、审读和直接发布清单 |
| [九月四刊](runs/2026-09-expansion-01/README.md) | 四刊原始候选、覆盖和审读 |
| [十月 1–5 日十三刊](runs/2026-10-01-to-05-01/README.md) | 十月采集、审读及 PRResearch 独立补证 |
| [十月 6 日十三刊](runs/2026-10-06-01/README.md) | 当日读取快照、两篇范围排除及四刊浏览器覆盖补证 |
| [十月 5–6 日补采](runs/2026-10-05-to-06-carryover-01/README.md) | 135 篇完整审读、6 篇新增、3 篇纳入接收稿状态更新及每日跨轮审计 |
| [十月 7 日更新与空档补核](runs/2026-10-06-to-07-01/README.md) | 118 篇审查、6 篇新增、出窗历史追溯及全文荐读 |
| [十月 8 日更新与空档补核](runs/2026-10-07-to-08-02/README.md) | 207 篇审查、9 篇新增、目录边界历史核对及全文荐读；显式绑定中断恢复来源 |
| [Nature Physics 首轮补采](runs/2026-09-01-to-10-08-np-01/README.md) | 9 月 1 日至 10 月 8 日全类型目录核对，47 篇审查、1 篇新增；加入 Spotlight |
| [93 篇出窗历史核对](reviews/2026-10-06-carryover-audit-01/README.md) | 历史判断追溯及已被完整补采替代的初步观察队列 |
| [131 篇人工裁决](reviews/2026-09-expansion-adjudication-01/README.md) | 解决四刊父轮未决项，保留用户意见和旧判断绑定 |
| [九篇编辑复议](reviews/2026-10-05-editorial-revision-01/README.md) | 六篇纳入、三篇维持排除的明确裁决 |
| [历史迁移索引](archive/legacy-2026-10-05/manifest.json) | 全部旧文件的位置、哈希和归档去向 |
| [历史档案](archive/legacy-2026-10-05/artifacts.zip) | 旧发布视图、阶段输出、回溯与复测材料；保留原字节 |

选择入口是 [release.json](../config/release.json)，文件职责与恢复方法见 [目录规范](../docs/repository-layout.md)。每轮 `publication.json` 直接钉住原始轮、复议、作者和补证。历史日志内的旧路径可通过迁移索引查找，不代表该旧位置仍存在。

完整摘要不在公开仓库。这里保存允许的书目、短证据说明、用户裁决、来源和哈希；不是全文专家评审。按 DOI 查看判断链可运行 `python scripts/manage_runs.py trace --doi <DOI>`。
