# 整刊候选采集与覆盖核对

## 轮次与输入

每次采集单独使用 `reports/<run-id>/`。日期窗口（含首尾）、ISSN、官方目录和请求预算取自 `config/sources.json`；`--journals` 指定本轮期刊子集，不把未选期刊算成缺口。新轮保存 `inputs/sources.json`、`inputs/screening-protocol.md` 和哈希清单，后续恢复读取这些冻结输入。

下一轮扩刊继续九月窗口，新增期刊与旧九刊分开存放。以下 `NEW_SHORT` 只是命令占位符，须先明确新增白名单与相应官方渠道；没有自动扩刊授权。

```powershell
python scripts/collect_candidates.py --out reports/2026-09-expansion-01 --as-of 2026-10-04 --journals NEW_SHORT
python scripts/collect_candidates.py --out reports/2026-09-expansion-01 --as-of 2026-10-04 --resume
```

恢复的窗口、配置与 as-of 必须一致；可用 `--journals` 只恢复本轮部分期刊。旧轮不重新采集，追加元数据修正写入审核事件，不改原候选。

## 技术顺序

1. 按每刊全部 ISSN 查询 Crossref journal works，分别查 online、print、pub 窗口并合并 DOI。禁止全库关键词搜索替代整刊采集。
2. 仅收最小书目：DOI、标题、ISSN、刊名、类型、各日期、URL 和出版社链接。此阶段不请求摘要、作者、参考文献或正文。
3. cursor 分页，并检查唯一数量、报告总量、终止页、游标与 ISSN。每页 500 条，每 ISSN／日期渠道最多 8 页；截断或失败标记未完成。
4. 独立枚举官方全类型目录，从最近页到早于窗口的守卫页。包括在线先发、未来期号中的窗口内在线文章；APS 同时核对 Recent 与 Accepted。
5. 检查目录顺序、跨页重复和范围。Nature 年度计数变化时须第二次读取月份前缀并比较逐页哈希；不以双方数量接近证明完整。
6. 精确补查官方独有 DOI、身份与日期冲突；保留双方字段及失败，不造数据库记录。日期与接收稿例外按筛选规程。
7. 每刊保存结果并更新来源覆盖；数量核对与严格字段一致性分开统计。后续审读不能靠修改原始候选消除冲突。

采集请求默认超时 25 秒、启动间隔至少 1 秒、无自动重试。目录页数按配置；APS 历史最多 700 次／刊、身份查找最多 40 次／刊、精确缺失 DOI 最多 100 次／刊。所有限制及源码哈希写入日志。

## 浏览器补证

Science、Science Advances、PNAS 等可能拒绝普通 HTTP。允许正常浏览器访问公开目录，不登录、不解验证码、不绕过访问控制；只读取允许书目，不保存 HTML、正文或 PDF。将目录来源、分页／守卫依据、重复条目及允许书目追加为 `browser_directory` 事件，再恢复程序。

目前浏览器目录导入需要人工执行，不能承诺从空目录全自动复现。逐页核验 DOI／日期转录集合，记录校验及来源；文章卡片内的 RELATED RESEARCH DOI 不能当目标 DOI。新期刊如需新解析器，先用离线夹具验证栏目、分页、日期与身份，再运行有预算的真实采集。

## 正式输出与状态

| 文件／字段 | 含义 |
|---|---|
| `candidates.json` | 原始跨来源书目、差异及窗口成员资格 |
| `coverage.json` | 逐刊来源枚举、数量和字段核对 |
| `collection-log.jsonl` | 追加来源与失败事件、版本和哈希链 |
| `source_enumeration_complete` | 列明的 API 与目录枚举完成 |
| `window_membership` | 在窗、出窗或日期／身份待定；同月日冲突未必影响成员资格 |
| `candidate_inventory_complete` | 枚举完成，成员资格明确，独有候选均有解释 |
| `window_reconciliation_complete` | 更严格的标题、具体日期等字段核对完成 |
| `selected_journal_*` | 本轮选定期刊的整体状态；旧 `nine_journal_*` 是兼容字段，不表示总刊数 |

采集清单中的 `subject_scope_status=not_assessed` 是采集时状态，后续结果以审核日志为准。完整 API 查询不等于完整出版社覆盖；目录核对完成也不等于科学审读完成。失败或较短遍历保留此前证据与上次有效网站快照。

官方参考：[Crossref 分页](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)、[日期过滤](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/)。
