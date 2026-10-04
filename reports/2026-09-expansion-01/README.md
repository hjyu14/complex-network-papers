# 2026 年 9 月扩刊：第一步书目采集

窗口：2026-09-01—2026-09-30（含首尾）；as-of：2026-10-04。采集于北京时间 2026-10-04 完成，日志时间使用 UTC。范围仅为新增四刊，不重采旧九刊，不进行科学范围审读或发布。

## 结果

| 期刊 | 窗口候选 | 已发表 | 仅已接收 | 有标题字段差异的记录 |
|---|---:|---:|---:|---:|
| Communications Physics | 60 | 60 | 0 | 0 |
| Physical Review Research | 228 | 146 | 82 | 38 |
| Physical Review E | 299 | 183 | 116 | 14 |
| Chaos | 58 | 58 | 0 | 2 |
| 合计 | 645 | 447 | 198 | 54 |

这些是整刊、全类型的书目候选，包含 Editorial、Erratum、Retraction 等；不是已筛选出的网络科学研究论文。仅已接收条目依现有接收稿例外登记，不计入已发表数；尚未确认研究类型或科学范围。

四刊的 `source_enumeration_complete`、`candidate_inventory_complete` 均为 true；本轮 `selected_journal_inventory_complete=true`。645 个 DOI 唯一，无窗口归属待核、未解释 Crossref 独有项或身份待核项。

54 条标题差异保留在候选 `issues` 中，未通过宽松归一化消除。包括数学排版／空格差别及用词、连字符等差别，未宣称已逐条裁定其等价性。因此 `selected_journal_reconciliation_complete=false`，采集程序仍返回其原有严格核对未完成状态（预期退出码 2），不是所有字段均已一致。窗口清单完整与严格字段一致是两个独立指标。

## 来源与边界

- Crossref：每刊所有配置 ISSN 分别查询 online、print、pub 窗口，共 18 个查询全部完成。只返回白名单书目字段，不取摘要、作者或参考文献。
- CP：官方全类型年度目录 4 页，遍历到早于窗口的守卫页。
- PRResearch：Recent 8 页、Accepted 6 页；PRE：Recent 11 页、Accepted 7 页。保留出版与接收状态和日期依据。
- Chaos：普通 HTTP 探测返回 403，转用正常浏览器，未登录、未处理验证码、未导出 cookie。全刊列表显式选择 Date - Newest First，4 个连续页面共 80 个唯一 DOI：58 个九月、8 个十月、14 个八月。全部 80 篇仅核对文章身份和明确页面发表日期；九月、十月卷期 DOI 集合分别与列表一致，并再次复查集合未变。八月记录为下边界守卫，十月记录核验未来期号中的潜在窗口内在线文章，不进入本轮候选。
- AIP `citation_publication_date` 常为期号月首，与页面 `.article-date` 不同。两者分别保存；不把月首或卷期月份冒充首次发表日。浏览器转录经校验值对照，再由 `scripts/import_aip_directory.py` 验证身份、日期、连续分页、唯一 DOI、守卫和卷期集合后导入。
- 完整性仅相对于本次读取的来源、目录与时间；不保证发现将来补登、回填或来源均未公开的记录。浏览器补证仍需实际操作，不能宣称从空目录完全无人值守复现。

## 文件与恢复

- `inputs/`：本轮四刊及窗口配置、筛选规程和哈希清单。
- `candidates.json`：当前书目清单及原始来源字段、差异；全部 `subject_scope_status=not_assessed`。
- `coverage.json`：逐刊覆盖、来源差集、窗口归属和发表状态计数。
- `collection-log.jsonl`：追加日志、原始允许书目、浏览器依据和状态版本；保留首次 Chaos 尚未补证时的记录，不改写历史。

```powershell
python scripts/collect_candidates.py --out reports/2026-09-expansion-01 --as-of 2026-10-04 --resume
```

恢复读取冻结输入和已有证据；不以当前全局配置重解释旧轮。完整浏览器输入暂存 Git 忽略的 `.private/work/aip-browser-bibliography.json`，正式书目和逐篇日期观察已保存于采集日志。未存摘要、正文、HTML、PDF 或凭据。

## 验证与未执行事项

- Python 56 项测试通过；前端 22 项测试通过；`node --check site/app.js` 通过；`python scripts/publish_snapshot.py --check` 通过。
- 追加日志哈希链、冻结输入哈希及当前两份状态文件哈希核验通过；645 个 DOI 无重复。
- `reports/2026-09/`、`site/`、`config/release.json` 没有 Git 内容改动。逐字节对照 Git 对象的 19 个文件中，6 个仅有本地 CRLF 与 Git LF 差别；换行归一化后全部一致。本次未写这些路径。
- 未获取摘要、未做科学筛选、未调整 Spotlight、未更新发布快照、未提交或推送。

下一步如获授权，使用本轮清单开展取证与逐篇审读；保留标题差异及仅已接收状态，不将其当作已经通过全部纳入检查。

## 后续：用户授权的资料采集与逐篇筛选已完成

以上为第一步书目采集完成时的历史说明。随后按用户授权，对全部 645 条候选逐批取证、实际审读及保存判断；本轮结果为 24 条 core、490 条 excluded、131 条人工 review，无未判断项。原始三个书目文件保持逐字节不变，科学判断独立追加至 `screening-log.jsonl`，没有发布网页。

详见 [筛选汇总](screening-summary.md)、[645 条逐篇结果](screening-results.md)、[人工复核清单](manual-review.md) 和 [纳入清单](included-papers.md)。这些是 AI 辅助标题／摘要筛选，不是全文专家审查。
