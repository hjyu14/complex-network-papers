# 九刊九月书目采集与交叉核对

执行日期：2026-10-03（北京时间）。分支：`codex/new-workflow`。窗口：2026-09-01—2026-09-30，包含首尾。日期和科学范围规则仍见 `screening-protocol.md`。

## 当前结论

已登记九刊的整刊书目候选，已知窗口候选均有官方资料或用户核实的出版依据。八刊完成本次列明来源的数量核对；NC 已知候选全部确认，但源目录分页稳定性仍未通过。所有条目均为 `not_assessed`，尚未进行主题或文章类型筛选。数量含编辑部文章、勘误等全部目录类型，不能解释为网络科学研究论文数量。

| 期刊 | Crossref 窗口查询 DOI 并集 | 官方窗口唯一条目 | 合并窗口候选 | 官方／用户核实的窗口候选 | 数量核对 |
|---|---:|---:|---:|---:|---|
| Nature | 518 | 410 | 410 | 410 | 完成 |
| Science | 161 | 161 | 161 | 161 | 完成 |
| Nature Communications | 909 | 908 | 910 | 910 | 已知候选确认，目录枚举未完成 |
| Nature Machine Intelligence | 13 | 13 | 13 | 13 | 完成 |
| Nature Computational Science | 13 | 13 | 13 | 13 | 完成 |
| Physical Review X | 42 | 42 | 42 | 42 | 完成 |
| Physical Review Letters | 461 | 463 | 463 | 463 | 完成 |
| Science Advances | 355 | 398 | 398 | 398 | 完成 |
| PNAS | 549 | 412 | 412 | 412 | 完成 |

合并窗口候选 2,822 条，其中 2,821 条有本次直接核查的官方身份与窗口依据，NC 最后一条由用户提供出版社首页截图确认。完整保存的跨来源候选共 3,068 条，另 246 条因优先日期不在窗口而保留为 `out_of_window`，不计入九月数。

**日期例外不可省略：** PRX 的 42 条含 18 条 Accepted Paper，PRL 的 463 条含 171 条 Accepted Paper。这些依已有授权按明确接收日入窗，分别只有 24、292 条具有本次核实的九月发表依据。接收日不能称为发表日，接收状态不能称为最终文章类型。

上述“完成”相对于获取时的列明来源及已有日期规则，不是出版社永不遗漏、迟到登记永不存在的保证。本轮没有后续延迟登记复查。

## 一个程序、三个正式输出

复用 `collect_nmi.py`，更名为 `scripts/collect_candidates.py`；离线验证位于 `tests/test_collect_candidates.py`。ISSN、渠道和页数预算在现有 `config/sources.json` 中配置。

| 正式结果 | 用途 |
|---|---|
| `reports/2026-09/candidates.json` | DOI、标题、ISSN、来源字段、日期依据、状态与差异 |
| `reports/2026-09/coverage.json` | 逐刊查询、目录枚举、数量核对、字段未决及整体状态 |
| `reports/2026-09/collection-log.jsonl` | 追加的原始允许书目、请求、失败、补证、规则／源码哈希和结果版本 |

日志每事件有 SHA256 链；当前候选和覆盖文件的内容哈希与最新状态事件一致。逐刊结果事件可重建当前两个 JSON。较短的失败遍历引用并保留之前较长的书目清单，完整性仍为 false。已存在的原始事件不改写；相同逐刊结果的后续恢复只记录哈希引用。日志目前约 80 MB，包含本轮失败、恢复和早期重复状态，未擅自删除历史证据。

NMI 原两轮独立试验输出实际为四个 JSON 文件，此前误写为六个。四个 JSON 和旧入口已保存于本地提交 `bdfa863`；正式日志的 `pilot_import` 包含完整成功轮候选、覆盖和来源文件哈希。按用户授权，四个独立 JSON 及两处 Python 缓存目录已删除，空试验目录移除。正式日志和历史原始事件保留。

程序的 `cached_nmi_pilot` 仅复用当前日志内已有且窗口／书目哈希核验通过的试验证据，不再读取历史文件；没有该事件的新输出会按九刊统一流程查询 Crossref 与 Nature 官方目录。删除不改变已有 NMI 13 条候选或其他刊物结果。新增离线新输出验证，在没有任何试验文件的临时目录中跑通 NMI 采集；共 19 项测试通过。删除与验证记录追加到现有日志，不新增正式报告。

## 技术执行顺序

1. 按每刊全部配置 ISSN 查询 Crossref journal works，不使用全库网络关键词。分别查询 online、print、pub 日期窗口，合并 DOI。
2. 每页 500 条，以 cursor 遍历；每 ISSN／日期渠道最多 8 页。核对唯一数量与报告总量、终止页、游标、ISSN、所选字段；截断、重复或失败不能标记完整。
3. 仅选择 `DOI,title,ISSN,container-title,type,published-online,published-print,published,issued,URL,resource`。`resource.primary.URL` 用于出版社链接匹配。没有选择作者、参考文献、摘要或正文。
4. 独立枚举出版社全类型目录。Nature 系列和 APS 从最新页按日期倒序读到早于 9 月 1 日的守卫页；不是遍历整年的声明。NMI 复用已核实的 8 页年度目录及 13 条九月候选。
5. Nature 检查日期顺序、页面范围、唯一文章链接及年度计数。年度计数变动时，必须第二次联网读取整个月份前缀，并且逐页书目哈希完全一致，才允许目录完成；本轮 NC 未满足。
6. APS 同时枚举 Recent Articles 和 Accepted Papers，按 DOI 合并。只解析链接标题与明确 Published／Accepted 日期；网页 SVG 的 title、登录标题不能作为文章条目。必要时仅提取官方出版历史的身份与日期，并按既有 APS 例外处理 online 等于 Accepted 的情况。
7. DOI 身份无法直接匹配时补查明确 citation 元数据；官方 DOI 在窗口查询中缺失时作精确 DOI 查询，最多 100 个／刊。找不到的记录保留官方元数据及失败，不构造 Crossref 记录。
8. 保留来源字段和差异，分别计算来源枚举、窗口成员资格、候选库存与严格字段一致性。每刊完成后追加结果和更新状态；恢复先验证日志链与当前两个 JSON 的哈希。

请求超时 25 秒、发起间隔至少 1 秒，无自动重试。APS 出版历史补查最多 700 次／刊，URL 身份补查最多 40 次／刊，目录页数按配置限制。首次适配中 APS 解析问题曾导致较多历史补查，日志已缓存，后续恢复不重复请求。

## 普通浏览器补证渠道

Science、SA、PNAS 的普通 HTTP 请求返回访问限制，因此使用正常浏览器读取公开目录；未登录、未解验证码、未绕过访问控制。不保存 HTML、全文、PDF 或认证数据。

当前这些渠道需要人工执行浏览器补证，再将允许书目追加为 `browser_directory` 事件；程序尚不能从空目录自动完成它们。每页只读取文章卡片的 DOI、条目日期、期号导航和条目数。Science／SA 使用 `h3.article-title` 的文章链接及所在 `.card` 的 `.card-meta time`；PNAS 使用标题链接及卡片的 `.card__meta__date`。按 DOI 去重，同时保留跨栏目重复观察数。浏览器与转录的 `DOI|date` 集合逐页 FNV1a 校验一致，保存后由日志 SHA256 链保护。

已枚举的官方路线：

- Science：current、393/6818—6815、6814（八月守卫）、First Release `/toc/science/0/0`；九月 161 个 DOI。
- SA：current 即 12/40、12/39—36、12/35（八月守卫）；官方 no-first-release 页面明确没有独立 First Release。416 次窗口卡片观察去重为 398 个 DOI。
- PNAS：123/39—35、123/34（八月守卫）、123/40、沿 Next 到 123/41，以及 latest。未来期号不等于未来在线日期；第 40、41 期中的九月在线条目必须计入。

目录转录没有完整采集 Science／SA／PNAS 标题，`publisher_title_compared=false`；不能声称这些刊物做过逐标题出版社对照。补证仅针对具体缺失或日期冲突条目。

## 已闭合的数量差异

- PNAS 的两个初始差异在 123/41 找到：`10.1073/pnas.2602433123`、`10.1073/pnas.2617910123` 均为 9 月 28 日。官方与 Crossref 优先日期 DOI 集合最终一致，共 412 条。
- Science `10.1126/science.aem6125` 官方文章页 9 月 24 日，纸刊 10 月 1 日；精确 DOI 查询补齐书目。`10.1126/science.aea9708` 官方 7 月 16 日，纸刊 9 月 3 日，故出窗。`10.1126/science.ael8642` 官方 9 月 11 日、纸刊 9 月 17 日，仍在窗内。采用明确文章发表 header 与独立纸刊历史，未把通用 dc.Date 当作固定 online 字段。
- SA 42 篇 9 月 30 日条目只有 Crossref 10 月 2 日纸刊日期，全部逐条打开文章页核实发表 header 为 `30 Sep 2026`，并补查最小书目。42 条浏览器 DOI/header 集合转录 FNV1a 为 `43d0daa3`。另 `10.1126/sciadv.aea6376` Crossref 未返回，通过官方文章页确认标题、DOI、ISSN `2375-2548` 和 9 月 18 日；不伪造 Crossref 字段。
- PRL 两条 Crossref 未返回的 DOI 为 `10.1103/6789-9w6m`、`10.1103/ly48-b4l2`。官方 Accepted 列表给出标题和 9 月 23 日，Accepted 页面确认 DOI、刊名及 footer 中 ISSN `1079-7114`、`0031-9007`，按已授权接收例外保留。

## 尚未闭合的 NC 与字段差异

NC 曾读取 48 页直到 8 月 31 日，取得 908 条官方窗口记录。但年度计数 10218/10219 变化，第二遍第 3 页记录改变；全新第三遍第 6 页又出现跨页重复。全部失败保留，不以年度计数接近或双方数量接近冒充完整。

NC 三项具体差异：

- `10.1038/s41467-026-77970-7` 未出现在保留的月份目录中，但官方文章页明确 DOI、ISSN 及 `citation_online_date=2026/09/30`，已确认其窗口身份；目录缺口仍保留。
- `10.1038/s41467-026-77425-z` 为官方独有；citation 元数据确认身份及 ISSN，目录显示 9 月 17 日，Crossref 精确查询仍未返回。
- `10.1038/s41467-026-77677-9` 仅 Crossref 返回九月日期；出版社链接 404，官方精确标题搜索未找到结果，尚不能确认其官方窗口身份。未删除、未猜测替代 DOI。

因此 NC 合并候选 910 条，官方确认 909 条，`source_enumeration_complete=false`、`candidate_inventory_complete=false`。进一步确认需稳定的官方月份目录／独立官方索引及这条 404 记录的出版证据。不得称为“NC 九月恰有 910 篇”或“九刊全部完整”。

### 单条复核：2026-10-03

再次核查 `10.1038/s41467-026-77677-9`，标题为 *Cognitive appeal promotes the persistence of inefficient solutions and hinders cumulative cultural evolution*。

- 精确 DOI 请求仍取得相同 Crossref 最小书目：刊名 Nature Communications、ISSN `2041-1723`、`published-online=2026-09-12`。附加查询取得 created `2026-09-12T04:44:00Z`、deposited `2026-09-12T04:44:03Z`；登记时间不能作为独立发表证据。
- DOI 解析器返回 **302**，Location 指向原 Nature 地址；随后 Nature 落地页返回 **404**。因此不能将它解释为 DOI 无效或未登记。正常浏览器也明确显示 `Page Not Found`，不是验证码或登录页面。
- Nature 官方 NC 精确标题检索显示 `Sorry, No results were found.`；这仅证明本次该检索无结果，不能证明文章从未发表。
- [第一作者 Ali Seyhun Saral 主页](https://www.saral.it/)列有相同标题、期刊和 DOI，但标签为 **Accepted**；[共同作者 Haneul Jang 主页](https://sites.google.com/view/haneuljang)也列为 accepted in Nature Communications。作者网页没有明确接收日或首次在线日，也可能未及时更新，不能覆盖 Crossref 日期或直接套用需要出版社确认的 Accepted Paper 例外。

结论：相同标题和 DOI 有作者本人页面佐证，但**九月首次在线发表仍未取得独立官方证据**。保留原 Crossref 日期、候选和 `needs_check`；新增书目复核证据，出版确认状态为 `unverified`。910 仍为按已登记日期合并的待核对候选数，官方确认数仍为 909，未把这一条确定收录、排除或改成已确认接收文章。可能是出版社页面／索引未上线或失效、日期登记差异、作者页面未更新，现有证据不能判定具体原因。

复核只追加到现有三个结果文件，并由程序恢复时保留 `bibliographic_recheck`。没有新增正式报告、抓取摘要或全文、联系作者或修改科学／日期协议；NC 月份目录变动问题也未在这次单条核查中重做。

### 用户出版证据确认：2026-10-03

用户确认该文章于九月十二日发表，并提供 Nature Communications 首页截图；其中相同 DOI 与标题、`Article | Article in Press`、`Published online: 12 September 2026`、`Accepted: 1 September 2026` 均清晰可见。按既有 online 优先规则确认入窗，无须套用接收日例外。判断明确署名为用户核实，保留前次网页失败和未决事件。

仅登记截图文件名、SHA256 和上述书目／出版元数据，不复制截图、摘要或全文进仓库。该 DOI 的 `publication_verification_status` 更新为 `user_confirmed_published`，保存日期依据；DOI 链接此前失效和官方目录未命中的事实仍保留。

NC 当前 910 条已知窗口候选已全部有确认依据：909 条来自本次官方资料，1 条为用户核实的出版证据。`confirmed_inventory_count=910`、`user_confirmed_inventory_count=1`，没有未解释的已知窗口内独有 DOI。但源目录的变动／重复检查未通过，故 `source_enumeration_complete` 和依赖该执行门槛的 `candidate_inventory_complete` 仍为 false，不能称为已证明不存在任何未发现条目。前文 909 条已确认、最后一条待核查等数值是本次用户补证之前的历史状态。

其他字段未决也保留：PRX 9 条、PRL 79 条标题差异（包括数学表示）；SA 181 条来源日期不同但都在九月；NC、PRL、SA 的四条 Crossref 缺失记录已有官方身份依据，但该渠道仍缺字段。不以删符号、删冲突或造元数据消除未决。

## 状态解释与恢复

- `source_enumeration_complete`：列明 Crossref 查询及官方目录是否完整枚举。
- `window_membership`：该 DOI 的日期证据是否确定属于窗口；同月两个不同日子可确定成员资格，但日字段仍未解决。
- `candidate_inventory_complete`：来源枚举完成，窗口／身份明确，且没有未经解释的窗口内 Crossref 独有记录。
- `window_status`、`window_reconciliation_complete`：更严格的字段核对，标题或具体日期冲突也会使其未完成。
- `subject_scope_status=not_assessed`：尚未实际主题审读。以上任何状态均不能替代科学筛选或发布审批。

```powershell
python -m unittest discover -s tests -v
python -X utf8 scripts/collect_candidates.py --as-of 2026-10-03 --out reports/2026-09 --resume
# 只恢复具体刊物：
python -X utf8 scripts/collect_candidates.py --as-of 2026-10-03 --out reports/2026-09 --resume --journals NC
```

窗口、配置哈希和 as-of 日期必须一致。新窗口用新输出目录；只有显式追加目录 revision 或补证才重新请求已经缓存的目录。当前已完成渠道复用获取时的证据，不能把恢复执行时间称为新的完整联网复查时间。程序非零退出代表严格核对未全部闭合；本轮两个整体完成标记均为 false。

本轮 18 项离线测试通过；实际结果另核对完整日志链、当前 JSON 哈希、从逐刊事件重建、DOI 唯一性、白名单 ISSN、全部未审读、无禁存字段，以及 NMI 原始输入哈希未变化。没有网站、主题筛选、全文审读、部署或 Git 推送验证。

官方依据：[Crossref REST API 分页说明](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)、[日期过滤说明](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/)、[PNAS 123/41](https://www.pnas.org/toc/pnas/123/41)、[Science 发表／纸刊日期示例](https://www.science.org/doi/10.1126/science.aea9708)、[SA 九月三十日示例](https://www.science.org/doi/10.1126/sciadv.aem1250)、[NC 目录](https://www.nature.com/ncomms/articles?year=2026)。
