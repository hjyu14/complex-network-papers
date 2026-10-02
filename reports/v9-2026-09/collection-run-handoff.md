# 当前材料收集的续跑说明

补采目标的固定范围仍为原 1,264 DOI，不修改原始清单或生产网站。补采统计以 `material-progress-v1.json` 为准；用户随后授权合并本次补齐与此前资料，完整候选池合并以 `material-master-v1.json` 为准。

## 2026-10-02 完整资料合并

- 已完成用户要求的资料合并：新脚本 `scripts/merge_all_material_v9.py`，输出 `material-master-v1.json`、`.md`、`material-master-audit-v1.json`，不覆盖输入报告，输出已存在时拒绝覆盖。
- 完整原始候选池为 3,987 个唯一 DOI；此前 review 3,850，最近补采 1,264 是其子集，不能把 1,264 当完整池，也不能把历史 1,992 缺摘要统计当当前候选总数。
- 总表状态：3,507 篇已有摘要级材料与完整记录日期（此前 2,605 + 最近 902）；295 篇非研究类型证据（此前 6 + 最近 289）；62 篇浏览器核查完成但无摘要；11 篇日期冲突；112 篇此前排除记录未重采。合计 3,987。保留旧 25 篇收录的历史评估，不作为新审读结论。
- 历史“摘要级材料”含部分 description-based 证据，尚未逐篇验证为独立摘要；不把总表材料数量当新的正式 v9 分类。日期窗口关系仅诊断：3,594 in_window、282 before_window、100 初始排除记录无已存日期、11 日期冲突；合并不删条目。
- 1,264 补充字段逐项保留；未在补采集内的 2,586 旧材料记录完全保持；62 最新浏览器结果、73 review 原因、2703 状态补证及 Springer/Nature 证据按 DOI 关联。旧状态补证单独保存，不能覆盖新日期或新出版社状态。
- 独立校验：原始 DOI 集合完全一致、无重复、所有补采字段保留、旧记录/保留记录/review 证据逐项一致、10 输入文件 SHA256 未变、总表 SHA256 匹配。65 Python/14 Node 测试与 app 语法通过。生产网站未修改。
- 本次用户的合并任务已完成，全部材料收集目标仍不满足，未标 complete。下一步可使用此总表做类型、日期核对与统一 v9 审读；不能无证据排除 Letter、Reply、Commentary。

## 执行顺序与现状

- 已完成程序化批量渠道；普通 HTTP 访问 ScienceDirect 的最新单篇检查仍为 403。
- 原 105 篇优先日期待办已全部补齐，已在合并报告中逐 DOI 核对。
- Elsevier 297 篇已全部补齐，包含 DOI 匹配、摘要、明确 online 日期、期刊、ISSN 和文章类型，不重复采集。280 篇在线发表于九月以前，17 篇发表于九月；独立审计保存在 `elsevier-online-date-audit-v1.json`。原浏览器待办 378 条均已尝试且身份确认，DOI 与导航 URL 保存在 `browser-navigation-queue-v1.json`。
- PNAS 41 条已补充正文顶部类型标签，其中 4 条 This Week in PNAS 和 3 条 Opinion 的元数据错误标为 research article。标签差异完整保留，不进行主题分类。
- Science 4 条 Working Life 的纸刊 DOI 身份通过正文标注的 Download PDF 链接确认。只读取链接，不下载 PDF；网页还有独立 DOI。
- AIP 唯一记录已确认页面明确标为 Editorial。
- APS 3 条 Accepted Paper 已确认 Abstract 栏目为空，仍保留为缺摘要。
- APS 11 条日期冲突已通过普通 HTTP 补齐接收和正式发表日期。原 Crossref online 日期等于九月接收日期，正式发表均为 2026-10-01；冲突保留，窗口决策未执行。
- 剩余 Elsevier 的 Crossref 更新检查完成 238 条（其中 6 条是浏览器已补齐的对照），无完整 online 日期；3 条错误单独重试成功，也无完整 online 日期。

## 2026-10-02 续跑结果

- 7 篇有明确 Editorial 类型证据，按 v9 第 2 节补入 `non_research_type_documented`，不扩大为排除 Letter 或 Commentary。当前 902 篇摘要/日期齐、289 篇非研究类型有证据、62 篇缺摘要、11 篇日期冲突；固定 1,264 DOI 未增删。
- 原 105 篇优先日期待办全部补齐；浏览器 378 DOI 集合与原导航清单逐项一致。`material_collection_audit_v9.py` 实际执行了这些断言。
- APS 3 条官方 RIS/BibTeX 均没有摘要；有界 RSS 也未补到。2026-10-02 普通 HTTP 再次检查 3 条均返回 200、DOI 匹配，摘要仍为空，见 `aps-empty-abstract-http-refresh-v1.json`。
- 对剩余 62 篇新做 Europe PMC core DOI 查询：完整响应，57 篇匹配但均无摘要，5 篇未索引。输出 `remaining-europepmc-refresh-v3.json`。旧 OpenAlex 和 Crossref 检查均覆盖这 62 篇且无摘要；旧 PubMed XML 覆盖其中 48 篇且无摘要。
- PNAS/Science 官方 Cite UI 导出表单实际入口均为 `/action/downloadCitation`，普通 HTTP POST 均 403，已停止该渠道批量重试。正常浏览器按钮分别成功导出一份 RIS，DOI 匹配但无 AB/N2 摘要字段。仅保存衍生证据 `pnas-citation-browser-probe-v1.json`、`science-citation-browser-probe-v1.json`，未向项目保存引用文件或摘要全文。浏览器生成的两份无摘要引用文件仍在 Downloads，由用户自行保留或删除。
- Science `10.1126/science.aem6084` 已补到顶部明确 `Association Affairs` 标签，保留旧 `other` 元数据；未因此自动排除该文章。模块 revision 9 修复了 Science 期刊文章类型定位 `.meta-panel__type`。
- Semantic Scholar 单次正常批量恢复请求仍为 429，无即时重试，见 `remaining-semantic-recovery-v3.json`。
- OpenAIRE 新 Graph V3 官方文档已核对。初始批量查询 400 原因是最多 4 个逻辑运算符；改为每批 5 DOI 后已完成 62/62 篇、13 批全部 200，均未索引到 DOI。结果保存在 `remaining-openaire-graph-probe-v3.json`，会话 46740 已确认退出 0。不使用新凭据；不得把一般 description 自动当作已核实摘要，不得用无 online 标签的聚合日期覆盖出版社日期。
- 用户明确选择保持 v9：无摘要且证据不足继续 review，不授权正文补证例外。`remaining-material-disposition-v1.json` 保存 62 篇缺摘要和 11 篇日期冲突的逐 DOI review 原因，未执行主题分类。
- 材料仍不全，目标未标完成；没有后台浏览器采集任务。不要把 review 清单生成当作全部摘要已收集。
- 本轮实际验证：固定清单与浏览器清单集合、原 105 日期、Elsevier 297 字段、剩余 62 的 Crossref/OpenAlex/出版社/Europe PMC/OpenAIRE 覆盖均通过断言；Python 4 个脚本语法、浏览器模块 `node --check`、生产 app 语法、65 个 Python 测试和 14 个 Node 测试通过。UI 未改动。目标轮次有实质进展（7 篇类型处理、独立日期审计、新渠道证据），不满足连续三轮阻断条件。

## 浏览器执行约束

## 2026-10-02 NIH / PMC 补证续跑

- 上一目标轮次为有实质进展。本轮新增正规元数据证据，仍不是全部信息已收集。
- Europe PMC core PMCID 补查覆盖 62 篇：10 篇有可公开读取的 XML，全部 200、DOI 匹配且无 abstract 元素；47 篇无该渠道提供的 PMCID，5 篇未索引。报告 `remaining-pmc-abstract-probe-v1.json`，会话 18312 已退出 0。
- NIH 官方 ID Converter 覆盖 62/62 DOI：32 篇给出 PMCID，其中 22 个此前未由 Europe PMC core 给出。进一步读取 live/release-date 发现 16 篇明确尚未公开，归档开放日期为 2027 年。这些日期绝不替代出版社发表日期。报告 `remaining-nih-pmc-id-audit-v1.json`。
- 对新 22 个 PMCID 的 Europe PMC XML 查询均为 500，不能记录成“正常返回且没有摘要”；会话 57432 已退出 0，报告 `remaining-nih-pmc-abstract-probe-v1.json`。
- 改用官方 NIH OAI `metadataPrefix=pmc_fm` 元数据接口，32/32 篇均返回 200、DOI 匹配，没有 abstract 元素。响应均没有 body；未请求 NIH 全文接口，不将正文用于审读。报告 `remaining-nih-oai-front-probe-v1.json`，会话 32049 已退出 0。
- 实际对照验证：来自官方来源的 PMC4383902（DOI 10.1093/nar/gku1061）在 Europe PMC XML 和 NIH pmc_fm 均能提取明确摘要，分别 109/108 个词，DOI 一致，后者无 body。说明 pmc_fm 与解析程序能处理真实摘要。对照不加入原始 cohort，摘要/XML 未归档。报告 `nih-oai-format-control-v1.json`。另有几个当前 cohort 对照候选没有适合的 PMC 摘要源，未将它们视为通过的对照。
- 补查此前未被 PubMed XML 覆盖的 9 篇：完整返回、9/9 DOI 匹配、无摘要。与原 48 篇合并后，已核对剩余中的 57 篇。报告 `remaining-pubmed-xml-completion-v3.json`。
- 未补到新摘要，统计仍是 902 / 289 / 62 / 11。NIH 类型字段与出版社可见类型分别保留，不据此排除 Letter、Commentary，不修改窗口或生产数据。用户保留 v9 无摘要 review 的决定仍有效。
- 没有仍在运行的采集进程；本轮新增证据支持正常推进后的收尾核对，不满足连续三轮无法推进的 blocked 阈值。

## 浏览器会话与续跑约束

## 2026-10-02 剩余 APS Harvest 核查

- 上一目标轮次只复核统计和审计，没有取得新材料，归为 no progress（1 次）。本轮补充此前未覆盖的正规渠道证据。
- 正常无凭据调用 APS Harvest 单篇 JSON 接口，剩余 3 个 DOI（lvpn-gblk、qbxp-7cbs、qz1m-4942）全部返回 404；不是本次请求被拒绝授权，也不能据此断言文章不存在。出版社 Accepted Paper 页面已确认这些 DOI。
- 输出 `remaining-aps-harvest-probe-v1.json`；只保存 HTTP 状态和衍生字段，未保存响应正文或凭据。没有尝试全文接口或替代请求绕过权限。
- 此渠道未补到新摘要，902 / 289 / 62 / 11 不变。当前已检查正规来源仍缺 62 篇摘要；无摘要不足证据继续 review，11 篇日期冲突继续保留。没有活跃采集进程。
- 后续若无新的可提供明确摘要的正规来源或出版社材料更新，不重复这些已完成的请求；当前目标未完成。本轮新证据确认不应继续用 Harvest 补这 3 篇，尚不满足连续三轮阻断阈值。

## 浏览器恢复说明

### 2026-10-02 用户授权的剩余 62 篇全量浏览器复核

- 用户明确要求通过浏览器获取剩余文献，已逐篇完成 62/62：PNAS 40、Science 19、PRL 1、PRE 2。全部 DOI 确认，新增摘要 0；59 篇没有独立摘要、3 篇 APS Abstract 栏为空。最终无 blocked 或 identity_unconfirmed 记录。
- 新文件 `browser-remaining-recheck-v1.json` 和 `.md`，complete=true 仅表示本轮浏览器覆盖完成，不表示材料目标达成。固定集合与原 62 缺摘要集合完全一致。
- Science aej8902 首次处于中文安全验证成功等待响应页；正常重新导航恢复，旧尝试保留 previous_attempt。浏览器模块 revision 10 增加中文验证提示识别；revision 11 处理 Windows EPERM/EACCES 的短暂检查点 rename 失败，仅重试保存，不重访页面。一条保存失败已从内存恢复并核对磁盘，未丢 DOI。
- 审计脚本增加可选完整浏览器复核验证及逐篇来源，已执行通过；65 Python/14 Node 测试、app 和浏览器模块语法通过。902 / 289 / 62 / 11 不变，生产网站及原清单未变。
- 当前没有活跃浏览器批量 Promise。句柄 remainingReader 为 revision 11，remainingResults 为完整 62，remainingReportPath 指向新报告。四标签 27/28/29/32 重新标记 handoff。续跑不要再次遍历此已完成队列。
- 无摘要继续 review 的用户决定不变；这轮授权浏览器核查已完成，全部材料目标仍未达成，需要外部摘要更新或新合法来源。

### 2026-10-02 用户手动检查页面

- 用户要求打开内置浏览器以手动批准权限。本轮使用既有浏览器 ID 2，显示浏览器并保留四个示例标签：27 PNAS pnas.2622915123；28 PRL lvpn-gblk；29 Science aem6084；32 PRE qz1m-4942。四篇均在缺摘要 review 清单，未改采集/审读规则。
- 已关闭 27、28、29 的引用导出面板。PNAS 页面显示 FULL ACCESS，Science 显示 FREE ACCESS；PRL 和 PRE Accepted Paper 页面可读但 Abstract 栏为空。当前示例没有验证码或拒绝访问提示，不能将缺摘要解释为统一的权限阻断。
- 为用户检查保存 PRE 空摘要栏目截图 `aps-empty-abstract-user-check-2026-10-02.png`，未下载 PDF、存储摘要或修改认证配置。四个标签均标记 deliverable，供用户检查，后续如需保留应再次标记。
- 902 / 289 / 62 / 11 不变；这次打开页面不等于补到新摘要。用户此前维持 v9 无摘要 review 的决定继续有效。

### 目标恢复后的阻断审计第 3 轮及状态

- 前两次恢复轮均为 no progress。本轮重新确认 1,264 DOI 总数、73 条唯一 review、62 篇出版社身份及已查询渠道无摘要、goal_complete=false；同一阻断不变。本轮也没有新材料进展，恢复后的连续三轮阈值已满足。
- 仍为 902 篇材料齐全、289 篇非研究类型有证据、62 篇缺摘要、11 篇日期冲突。没有新的合法摘要来源或已确认活跃采集句柄；保持 v9 无正文替代。
- 目标再次设为 blocked，未标 complete。恢复所需条件为新合法摘要证据或出版社/数据库更新；既有结果和原始 cohort 保留，不重复已完成的请求。

### 目标恢复后的阻断审计第 2 轮

- 前一恢复轮为 no progress；本轮从磁盘重新确认三个主报告的时间与数量未变，仍为 902 / 289 / 62 / 11、73 条唯一 review、goal_complete=false。
- 没有新的正规摘要来源、用户材料或已确认活跃采集句柄，当前无法采取能补齐缺口的行动。维持 v9，不使用正文替代。本轮为连续第 2 轮 no progress；目标仍 active，不沿用恢复前的阻断计数。

### 目标恢复后的阻断审计第 1 轮

- 目标工具返回 active，updatedAt=1790927201，视为先前 blocked 后恢复；重新从第 1 轮计算阻断，不沿用旧三轮计数。
- 本轮主进度和逐 DOI review 报告未出现新材料，仍为 902 / 289 / 62 / 11，73 条唯一 review。没有新来源或用户材料，没有已确认活跃采集句柄；本轮未启动请求。
- 上一目标轮次为阻断确认、没有材料进展。本轮为 no progress。同一缺摘要阻断仍在，需要新合法摘要来源或外部材料变化；用户保持 v9 的决定不变。
- 目标未完成，当前恢复后的第 1 轮不标 blocked；不重复旧渠道请求来制造进展。

### 后续阻断审计第 3 轮及目标状态

- 前两轮均只作状态核对，没有新增材料，为连续 no progress。本轮重新核对固定集合、73 条唯一 review、62 篇出版社身份与 Crossref/OpenAlex 无摘要证据、3 篇 Harvest 404，数据与同一阻断均未变化。
- 当前 902 篇材料齐全、289 篇非研究类型已有证据、62 篇缺摘要、11 篇日期冲突。完成条件不成立，不标 complete，不改变目标为较小范围。
- 同一阻断已连续三轮：没有已知尚未执行且可提供明确摘要的授权正规来源，也没有已确认活跃采集句柄可等待；v9 明确禁止正文替代。需要新的合法摘要证据或出版社/数据库更新才能继续补齐。
- 将目标设为 blocked，停止无新证据的自动重复。恢复时先检查新的外部材料或用户提供的新来源；不要重复全部历史请求。用户无摘要继续 review 的决定保持有效。

### 后续阻断审计第 2 轮

- 前一轮只核对来源覆盖，为 no progress。本轮主合并与逐 DOI review 报告仍为固定 1,264 DOI、62 缺摘要、11 日期冲突，审计仍明确 goal_complete=false。
- 没有新的摘要证据写入；系统进程查询被权限拒绝，不能据此声称没有 Python/Node 采集进程。此前采集句柄已确认退出，本轮没有启动采集任务、没有可等待的已确认活跃工具句柄，不能把本轮记为 verified wait。
- 同一阻断连续第 2 轮：现有正规来源不提供摘要，用户维持 v9，正文不能替代。没有已知可推进的安全下一步。本轮为 no progress，目标仍 active；下一轮若阻断不变且无新来源或外部变化，满足三轮阈值后应标 blocked。

### 后续阻断审计第 1 轮

- 前一目标轮次新增 APS Harvest 3 篇逐 DOI 404 证据，属于 progress。本轮只有重新核对覆盖和规则，属于 no progress，不把审计或重写统计算作材料进展。
- 当前 62 篇均已确认出版社身份；Crossref/OpenAlex 均匹配但无摘要，Europe PMC 57 匹配、5 未索引，OpenAIRE Graph 62 未索引。APS 3 篇正常单篇 Harvest 请求均 404。固定 1,264 DOI、62 缺摘要、11 日期冲突不变。
- 当前没有发现尚未执行且能提供明确摘要的正规渠道。现有材料无法补成全部齐全；用户明确保持 v9，不能用正文或自拟总结替代摘要。需要出版社/数据库新增摘要或取得新的合法摘要来源才可继续补齐。
- 同一阻断首次连续 no-progress 核查，目标仍 active；后续不要靠重复请求、统计或审计制造 progress。达连续三轮且阻断不变时按规则标 blocked，不标 complete。

最新补证：2026-10-02。模块最新缓存 revision 9；下面旧的 revision 8 导航恢复说明仍适用。

使用已授权的 Codex In-app Browser，浏览器 ID 2；ScienceDirect tab 31。tab 27 当前为 PNAS Commentary（引用导出对话框），28 为 APS，29 为 Science Association Affairs。27、29 及存在的旧 APS/Elsevier 句柄已重新 markHandoff。保持会话，不导出 cookie，不绕过访问控制。

使用 `scripts/browser_material_reader_v9.mjs` 的 `runBatch`，由 `mcp__cua_repl.js` 传入授权 tab。模块最新缓存版本 revision 9。

在 REPL 中已有 `taskFs`、`taskDir`、`browserReader`、`browserRows`、`browserResults`、`elsevierTab`。如会话变量失效，从导航清单和主浏览器报告恢复结果，不能重新从首篇开始。

本轮新增句柄 `pnasExportTab`、`scienceExportTab`、`readerRevision9`、`fsEvidence`、`evidenceDir`。旧 `browserReader`/`browserResults` 内存可能落后于磁盘：如继续运行，应使用 revision 9 并从主报告恢复最新行，避免丢掉 Science 新类型补证。

当前间隔：`minNavigationIntervalMs: 40000`。每次工具调用使用 `batchSize: 1`、60 秒超时，等待调用完成。工具结束后的异步任务不能继续正常调用浏览器：此前实验得到 `node_repl exec context not found`，两条受影响记录已正常重试补齐。现在没有后台采集任务。

每篇写 checkpoint，已尝试 DOI 自动跳过。失败重试应使用单独 retry 文件，成功后升级主记录并保存 `previous_attempt`。访问错误发生时暂停该站；此前暂停约 10–11 分钟后正常刷新可恢复。40 秒间隔下目前持续成功，但不能保证后续永不受限。

revision 8 在导航观察超时后先检查同一 tab：页面可能已经加载完成。若 DOI 和元数据可核对，保存结果及 `navigation_warning`，不重复导航；若仍不能核对，保留执行错误。已实际发生过一条超时后页面正常的记录，并通过直接读取补齐。

定期执行：

```powershell
python -X utf8 scripts/summarize_programmatic_material_v9.py
python -X utf8 scripts/material_progress_v9.py
```

缺摘要、空摘要栏、访问错误、未访问及日期冲突分别报告。摘要仅瞬时读取，保留可用性、词数等衍生字段，不存摘要全文、HTML、PDF或认证数据。材料可用不等于 v9 主题筛选完成。
