# 整刊候选采集与覆盖核对

## 轮次与输入

每次采集单独使用 `reports/runs/<run-id>/`。日期窗口（含首尾）、ISSN、官方目录和请求预算取自 `config/sources.json`；`--journals` 指定本轮期刊子集，不把未选期刊算成缺口。新轮保存 `inputs/sources.json`、`inputs/screening-protocol.md` 和哈希清单，后续恢复读取这些冻结输入。


```powershell
python scripts/collect_candidates.py --out reports/runs/example-run --as-of 2026-10-05 --window-start 2026-10-01 --window-end 2026-10-05
python scripts/collect_candidates.py --out reports/runs/example-run --as-of 2026-10-05 --resume
```

恢复的窗口、配置与 as-of 必须一致；可用 `--journals` 只恢复本轮部分期刊。未封存轮在原目录恢复；封存后不重新采集或改写旧候选，新增证据与复议另立明确轮次。已发布目录和压缩日志由 CLI 拒绝写入。

经授权的新窗口使用成对的 `--window-start` / `--window-end`（含首尾）。它们只改变新轮冻结配置，不修改全局 `config/sources.json`；恢复时禁止传窗口覆盖，以已冻结输入为准。日期须有序、同年且不晚于 `--as-of`。日期上限不是全天覆盖保证，实际覆盖截至各来源获取时间。

```powershell
python scripts/collect_candidates.py --out reports/runs/example-run --as-of 2026-10-05 --window-start 2026-10-01 --window-end 2026-10-05
```

## 技术顺序

1. 按每刊全部 ISSN 查询 Crossref journal works，分别查 online、print、pub 窗口并合并 DOI。禁止全库关键词搜索替代整刊采集。
2. 仅收最小书目：DOI、标题、ISSN、刊名、类型、各日期、URL 和出版社链接。此阶段不请求摘要、作者、参考文献或正文。
3. cursor 分页，并检查唯一数量、报告总量、终止页、游标与 ISSN。每页 500 条，每 ISSN／日期渠道最多 8 页；截断或失败标记未完成。
4. 独立枚举官方全类型目录，从最近页到早于窗口的守卫页。包括在线先发、未来期号中的窗口内在线文章；APS 同时核对 Recent 与 Accepted。
5. 检查目录顺序、跨页重复和范围。Nature 年度计数变化时须第二次读取月份前缀并比较逐页哈希；不以双方数量接近证明完整。
6. 精确补查官方独有 DOI、身份与日期冲突；保留双方字段及失败，不造数据库记录。日期与接收稿例外按筛选规程。
7. 每刊保存结果并更新来源覆盖；数量核对与严格字段一致性分开统计。后续审读不能靠修改原始候选消除冲突。

采集请求默认超时 25 秒、启动间隔至少 1 秒、无自动重试。429 保存已取得的书目并停止本次运行后续请求与渠道，未启动项不能记为无文献。目录页数按配置；APS 历史默认最多 700 次／刊，配置中的 PRResearch 250、PRE 350；身份查找最多 40 次／刊、精确缺失 DOI 最多 100 次／刊。CP 最多 12 个目录页，PRResearch 每渠道 30 页、PRE 每渠道 40 页；Chaos 最多 12 个全刊列表页、120 次文章元数据核验。所有限制及源码哈希写入日志。

## 浏览器补证

Science、Science Advances、PNAS 等可能拒绝普通 HTTP。允许正常浏览器访问公开目录，不登录、不解验证码、不绕过访问控制；只读取允许书目，不保存 HTML、正文或 PDF。将目录来源、分页／守卫依据、重复条目及允许书目追加为 `browser_directory` 事件，再恢复程序。

目前浏览器目录导入需要人工执行，不能承诺从空目录全自动复现。逐页核验 DOI／日期转录集合，记录校验及来源；文章卡片内的 RELATED RESEARCH DOI 不能当目标 DOI。新期刊如需新解析器，先用离线夹具验证栏目、分页、日期与身份，再运行有预算的真实采集。

### Chaos / AIP

AIP 普通 HTTP 返回 403 时使用正常浏览器，不复制 cookie、不绕过验证。由官方首页的 `View All Most Recent Articles` 进入全刊通配符 `*` 列表，选择 `Date - Newest First`，不选主题、合集或研究栏目。读取卡片标题、文章 URL、DOI 与列表月份；逐页检查连续页号、唯一 DOI，读取到早于窗口的完整守卫页。另核对窗口月及后续已公开期号的全部 DOI 集合，包含 Editorial、Errata 等类型。

列表及卷期月份不是首次发表日。对枚举前缀中的每篇文章，只读取身份和页面明确 `.article-date` 日期；`citation_publication_date` 可能是期号月首，单独保留，不能替代页面具体日期。页面在内存中解析，不保存 HTML、正文或摘要。将允许字段整理为 `aip-browser-bibliography-1` 输入，由 `scripts/import_aip_directory.py` 严格校验（字段白名单、期刊 ISSN、逐篇身份、日期倒序、边界、分页和卷期 DOI 差集）后追加 `browser_directory` 事件，再恢复采集器。具体输入结构见该脚本及合成测试；原始浏览器输入暂存 `.private/work/<run-id>/`，正式允许书目与核验依据存追加日志。

```powershell
python scripts/import_aip_directory.py --out reports/runs/example-run --input .private/work/example-run/aip-browser-bibliography.json
python scripts/collect_candidates.py --out reports/runs/example-run --as-of 2026-10-05 --resume --journals Chaos
```

导入器不联网，不把数量相同当作 DOI 集合相同；跨页重复、无完整日期、缺少守卫或刊物身份不符均拒绝完整性声明。恢复不重写追加日志中的旧证据；当前 `candidates.json`、`coverage.json` 是由保留的版本事件生成的本轮状态，旧 `reports/runs/2026-09/` 不变。

## 正式输出与状态

### Nature 系列浏览器目录导入

普通 HTTP 目录读取失败时，可由正常浏览器读取全类型年度列表的连续页、刊名／ISSN、年份、年度计数和分页。允许书目转录使用 `scripts/import_nature_directory.py --out <run> --input <bibliography.json>`；它只追加经过结构核验的 `official_page` 事件，不自行宣称覆盖完成。恢复采集器后仍由原有排序、下界守卫、跨页唯一性和年度计数变化的二次前缀核验决定完成状态。文章页 DOI 身份补核另行留痕，不从 Nature 页面 URL 推造 DOI。

当天截止窗口可显式使用 `import_aip_directory.py --live-as-of`，从本轮已保存的 collection settings 核对 `as_of=end`；全部目录、卷期与逐篇观察必须带时区且在该北京时间日获取。仍须从未筛选的全刊最新第一页连续枚举、核对逐篇具体日期、早于窗口的守卫与卷期 DOI 集合。此模式允许最新公开文章早于窗口末日，仅声明来源在读取时刻的快照，输出 `boundary_mode=live_as_of_snapshot` 和获取时间区间，不表示当天已结束或全天无遗漏。默认历史窗口的上界检查保持不变。

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
| `publication_status_counts` | 窗口候选中已发表、仅已接收、状态未确认分别计数；不得把总数当作已发表数 |

采集清单中的 `subject_scope_status=not_assessed` 是采集时状态，后续结果以审核日志为准。完整 API 查询不等于完整出版社覆盖；目录核对完成也不等于科学审读完成。失败或较短遍历保留此前证据与上次有效网站快照。

官方参考：[Crossref 分页](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)、[日期过滤](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/)。
