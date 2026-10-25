# 2026-10-25 日常文献更新（采集未闭合）

- 冻结窗口：2026-10-24 至 2026-10-25（含首尾），固定 14 本白名单期刊；本轮从上一有效发布截止日重叠回扫。
- 采集器已完成 Crossref 与可直接读取来源的登记，候选 37 篇，全部来自 Nature Communications（34）和 Communications Physics（3）。
- Science、Science Advances、Chaos、PNAS 的 `source_enumeration_complete` 和 `window_reconciliation_complete` 仍为 false；本次浏览器页面可进入，但尚未按正式导入器／日志事件保存可复核的全类型目录证据，不能把可见页面当作覆盖闭合。
- 因覆盖缺口未闭合，未初始化正式科学审读，未生成 `publication.json`，未修改 `config/release.json`，未提交、推送或部署。
- 恢复依据：`candidates.json`、`coverage.json`、`collection-log.jsonl` 及冻结 `inputs/`。后续应先完成四刊的正式浏览器目录证据导入和采集器恢复，再进入逐篇审读。

## 2026-10-25 恢复观察（继续）

- 通过浏览器打开 Chaos AIP 全站搜索目录：`https://pubs.aip.org/aip/cha/search-results?q=*&sort=Date+-+Newest+First&fl_SiteID=1000025`；自动安全检查在等待后自行完成，未出现需要人工点击的 CAPTCHA/登录阻塞。
- 页面明确显示 `1-20 of 77715`、排序 `Date - Newest First`、期刊过滤器和分页；但 20 个结果卡片混有 `JOURNAL ARTICLES` 与 `IMAGES`，图片卡片复用文章 DOI，不能作为 20 条独立文章记录。
- 可见文章的出版字段为 `Published: October 2026`（月粒度），没有本轮 2026-10-24 至 2026-10-25 所需的逐篇日级日期。现有 `scripts/import_aip_directory.py` 要求每张卡片对应唯一 DOI、逐篇显式文章日期和下界守卫，因此本次页面观察未导入 `browser_directory` 事件。
- 本轮仍保持未闭合：Science、Science Advances、Chaos、PNAS 的官方目录覆盖未完成；未开始正式审读、未生成 `publication.json`，未发布。

## 更正（2026-10-25）

- 复核确认 AIP 搜索页的公开 `Format -> Journal Articles` 筛选可正常使用；应用后 URL 带 `f_ContentType=Journal+Articles`，页面显示 `1-20 of 9165`，结果为 20 条文章卡片，不再混入图片。
- 点击首条文章后，AIP 文章页标题下显示明确日期 `OCTOBER 22 2026`（DOI `10.1063/5.0331096`）。这说明逐篇文章页可以提供日级日期；此前“只能到月份、无法获得文章目录”的判断不成立。
- 需要继续完成筛选目录分页、逐篇日期证据和下界守卫后，才能导入正式 `browser_directory` 事件；在此之前不改变发布状态。

## 覆盖闭合与审读完成（2026-10-25）

- 已通过浏览器目录与边界证据闭合 Science、Science Advances、Chaos、PNAS；`coverage.json` 中 14 本白名单期刊均为 `source_enumeration_complete=true`、`window_reconciliation_complete=true`。
- Chaos 使用 `Journal Articles` 筛选并核对首篇文章页的日级日期；Science、Science Advances、PNAS 核对当前刊／First Release 或前刊边界，均早于本轮窗口。
- 本轮 37 篇候选已逐篇审读并写入正式审核日志：36 篇 `excluded`，1 篇 `transferable_application`（DOI `10.1038/s41467-026-78646-y`）；无 active DOI、未审读项或延期项。
- 后续收尾需完成跨轮审计、作者与说明绑定、AI’s Suggestion、`publication.json` 和发布校验；在这些步骤完成前不修改 release 选择。
