# 2026 年 9 月扩刊：645 条候选筛选完成

窗口：2026-09-01—2026-09-30（含首尾）；as-of：2026-10-04。结果依据本轮冻结规则、原始清单及 `screening-log.jsonl` 的最新逐篇判断，不改写候选中的采集时 `not_assessed` 状态。

## 结果

| 期刊 | 纳入 core | 纳入 transferable_application | 排除 | 人工 review | 合计 |
|---|---:|---:|---:|---:|---:|
| Communications Physics | 5 | 0 | 51 | 4 | 60 |
| Physical Review Research | 0 | 0 | 194 | 34 | 228 |
| Physical Review E | 0 | 0 | 211 | 88 | 299 |
| Chaos | 19 | 0 | 34 | 5 | 58 |
| 合计 | 24 | 0 | 490 | 131 | 645 |

645 个唯一 DOI 均有独立、已保存的最新判断；未判断、未取证延期和活跃文献均为 0。原候选中 447 条已发表、198 条仅已接收；接收日定窗没有冒充发表日。

## 材料与判断的含义

637 篇根据身份匹配的明确摘要实际审读；其中最新判断材料来自 Crossref 明确 abstract 字段 263 篇、出版社明确 Abstract 341 篇、浏览器摘取官方 Abstract 33 篇。浏览器还用于核实具体类型、题名差异及摘要空白，不能将这个 33 当作全部浏览器访问数量。

另外 6 篇依据官方明确非目标类型排除，不为排除而额外取得摘要；2 篇在自动渠道及普通浏览器补证后，官方接收页 Abstract 仍为空，保留人工 review：

- `10.1103/qz1m-4942`
- `10.1103/x78y-924k`

131 篇人工 review 中，127 篇的具体文章类型仍未核实；这与科学范围边界、题名差异或资料不足可能重叠，不能相加。尤其 PRE 和 PRResearch 的网络科学相关条目不能仅凭刊名、Accepted Paper、Published 或通用 Crossref journal-article 推断具体官方类型。本轮没有扩展 PRL 接收稿的摘要类型推断例外。因此 APS 两刊本轮纳入数为 0，不表示它们没有网络科学相关工作。

每篇 review 都列明已有证据、具体原因及下一步缺口；它不是自动批量占位，也不等于范围排除。科学边界实例包括神经网络自身动力学与预测工具的区别、材料相互作用与可迁移网络方法的区别，以及量子/单通道输运是否构成网络科学贡献。不按领域、关键词或最少节点数作自动判断。

纳入只表示通过当前标题／摘要辅助筛选及必要书目硬检查，不是全文专家审定；摘要中的性能、因果或适用范围主张没有额外独立验证。所有完整摘要仅在本项目 Git 忽略的 `.private/abstract-cache/v9/` 中保存，没有存入普通报告、Git 或 `site/`。本轮早期的一份摘要转录临时输入已移入同一允许缓存目录，材料未删除；无关旧轮私有文件未改动。

## 交付文件

- [逐篇完整结果](screening-results.md)：645 篇的类别、理由、硬检查、来源、差异及判断输入哈希。
- [人工复核清单](manual-review.md)：131 篇及具体待补证／裁决问题。
- [纳入清单](included-papers.md)：24 篇。
- [机器可读完整结果](screening-results.json) 与 [校验汇总](screening-summary.json)。
- `screening-log.jsonl`：追加证据和判断日志；旧判断、失败及纠正全部保留。

## 验证与未执行事项

- 两份日志哈希链、全部最新判断输入哈希及所引用私有摘要／材料哈希核验通过。
- 全部 24 篇纳入者的身份、具体类型和日期硬检查均为 verified。
- 原始 `candidates.json`、`coverage.json`、`collection-log.jsonl` 的 SHA-256 与开始审读时相同，逐字节不变。
- `site/`、旧 `reports/2026-09/`、`config/release.json` 的所有已跟踪文件与 HEAD 内容一致（允许已有 CRLF/LF 换行差别）；本任务未写这些路径。
- Python 57 项测试通过；前端 22 项测试通过；`node --check site/app.js` 及 `python scripts/publish_snapshot.py --check` 通过。前端负例测试预期输出 Invalid or outdated snapshot，不是测试失败。
- 针对 PRE／PRResearch 扩展了既有 APS 严格身份解析器，并增加测试；未放宽科学范围、日期或类型规则。
- 未提交、推送、改变发布轮次、更新网页或部署。

审核日志最终链头：`49448d9071384b1d8c6e5dadc2e374b0ae75eed43d97b8320ea5237c1b7b7a0c`。
