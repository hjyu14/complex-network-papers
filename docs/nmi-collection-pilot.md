# NMI 九月书目采集试验

执行日期：2026-10-03（北京时间）。分支：`codex/new-workflow`。目标窗口：2026-09-01 至 2026-09-30，首尾包含。

## 目的与边界

建立整刊窗口候选清单，核对可列举的官方目录与 Crossref 的差异。只取得书目信息，不按研究主题过滤，不获取摘要，不执行科学相关性筛选，也不发布网站。

## 可复用步骤

1. 读取 `config/sources.json` 的 NMI ISSN `2522-5839` 和窗口。
2. 查询 Crossref `/journals/2522-5839/works` 的 online、print、通用 publication 三种日期窗口。仅选择 DOI、title、ISSN、container-title、type、published-online、published-print、published、issued、URL；每页 100 条，每查询最多 5 页。
3. 使用 cursor 逐页读取，检查终止页、报告总量、唯一 DOI、重复游标和响应字段。失败或预算截断不算完整成功。
4. 普通 HTTP 读取 NMI 全类型 2026 年度目录的全部分页；只解析文章标题、类型、time 日期、URL、年度计数及分页控件。最多 12 页；不保存 HTML 或目录介绍。
5. 目录页使用链接和 `data-page` 控件识别页码，包括不可点击的当前页；逐页检查重复文章、稳定计数和最终唯一条目数。
6. Crossref 返回的 URL 可能只有 DOI 解析链接。无法直接与目录 URL 对照时，读取文章页明确 citation 元数据中的 DOI、标题、ISSN 和刊名；每轮最多 20 次身份补查，不提取摘要或正文。
7. 按明确 DOI／URL 身份合并；保留所有来源日期和标题。按既定日期优先级判定窗口，来源冲突、身份不足或不完整日期进入 `needs_check`，不自动放行。
8. 输出 `candidates.json` 与 `coverage.json`。记录源码与配置哈希、来源时间、请求和分页、书目输入哈希、差异和限制。

每次请求超时 25 秒，发起间隔至少 1 秒，无自动重试；访问失败保留状态，不绕过访问控制。响应仅在内存解析，文件只保存上述允许字段。

## 实际结果

| 项目 | 数量／状态 |
|---|---|
| Crossref online 日期查询 | 13 个 DOI，1 页，完整 |
| Crossref print 日期查询 | 0 个 DOI，1 页，完整 |
| Crossref通用 publication 日期查询 | 13 个 DOI，1 页，完整 |
| Crossref 三查询去重 | 13 个 DOI |
| 官方 2026 年度目录 | 8 页、146 个唯一条目，与年度计数一致 |
| 官方目录九月条目 | 13 条 |
| 逐条 DOI、标题和日期对照 | 13/13 匹配；两边无独有条目 |
| 窗口判断 | 13 条 `in_window`，0 条 `needs_check` |
| 出版社类型 | Article 10；News & Views、Editorial、Publisher Correction 各 1 |
| 主题筛选 | 全部 `not_assessed` |
| 完整摘要／正文／HTML 文件 | 未保存 |

13 条是全部目录类型的书目候选，不是 13 篇网络科学文章，也不是 13 篇符合最终文章类型要求的研究文章。

## 首轮问题与恢复记录

- `reports/nmi-2026-09/run-2026-10-03-01/` 原样保留。首轮已完成三种 Crossref 查询、前七页 140 条目录记录及九月 13 条身份对照。
- 第八页当前页号是没有超链接的 span；首版只数可点击链接，误读最大页号为 7，因而触发分页范围变化检查。首轮报告明确未完成，没有用数量吻合冒充采全。
- 修正解析器读取分页控件 `li[data-page]`，新增末页及恢复哈希检查。十项离线测试通过。
- `run-2026-10-03-02/` 引用首轮文件哈希和源码哈希，验证既有 Crossref 元数据及已完成目录页哈希，复用已核实的文章 citation 身份记录，仅新请求第八页，补齐剩余六条年度条目。首轮文件未覆盖。
- 第二轮 `source_enumeration_complete=true`、`window_reconciliation_complete=true`，仅表示本次列明来源的枚举与窗口对照完成。

## 运行与复核

```powershell
python -m unittest discover -s tests -v
python -X utf8 scripts/collect_nmi.py --as-of 2026-10-03 --out reports/nmi-2026-09/new-run
```

输出目录必须不存在。恢复本次首轮的命令为：

```powershell
python -X utf8 scripts/collect_nmi.py --as-of 2026-10-03 --resume-from reports/nmi-2026-09/run-2026-10-03-01 --out reports/nmi-2026-09/new-recovery-run
```

恢复只适用于相同配置、窗口和 as-of 日期且 Crossref 查询完整的记录，源文件保留；其他情况应显式启动新的采集轮次。

## 完整性限制

这是截至本次获取时间、相对于所列官方年度目录的覆盖核对。不能证明出版社目录本身绝无遗漏；尚未审计文章完整出版历史，也未做后续迟到登记／日期修订复查。未验证 NMI 的独立已接收文章渠道。

其他八刊的目录结构、类型栏目和访问方式尚未验证，不能直接宣称本程序适用于全部九刊。

官方依据：[NMI 年度目录](https://www.nature.com/natmachintell/articles?year=2026)、[Crossref 字段、分页及同步说明](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)、[日期过滤说明](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/)。
