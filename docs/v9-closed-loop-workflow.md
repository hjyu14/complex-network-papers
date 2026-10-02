# v9 历史路由与读取后立即审读

## 当前入口

`scripts/review_workflow_v9.py` 是本次剩余队列的新入口；旧的 `read_final_review_v9.py` 命令行入口已停用。其他历史采集脚本只用于查证旧报告和提取器实现，不再用于先采全池后分类。

这里的“接通”是程序取数、私有缓存与助手逐篇语义审读之间的闭环，不是关键词分类器或无人值守的模型 API。程序准备输入后返回，助手读取本篇摘要并提交判断；程序验证记录后才放行下一篇。

## 路由

- `reports/v9-2026-09/historical-routes-v1.json` 固定了原进度表中全部 3,218 篇 review 的来源顺序，包括 3,214 篇未审读、2 篇边界复核、2 篇已知缺摘要。
- 每条来源注明具体报告、历史证据强弱、URL、来源类别及是否曾经通过浏览器取得。
- 历史明确摘要优先；Crossref、Europe PMC、PubMed、OpenAlex 有对应读取器。出版社只解析明确摘要字段或 Abstract 栏，不把 description 当摘要。
- 即使此前通过浏览器成功，先尝试同一网址的普通 HTTP；程序渠道失败后停在 `needs_browser_or_source_review`，交给已有授权浏览器。不会自动绕过访问限制。
- 来源清单中 2,505 篇有历史明确摘要成功记录；其余 713 篇依靠较弱历史线索或备用渠道，不保证都能重新取得摘要。
- 三个旧状态文件含追加的 JSON 片段，未被当作逐 DOI 来源证据：`material-collection-status.json`、`openalex-fallback-status.json`、`publisher-fallback-status.json`。路由报告记录解析错误；旧文件未改动。

## 每篇闭环

1. `python -X utf8 scripts/review_workflow_v9.py next`：先恢复当前篇，或选择下一篇；优先本地缓存。可用 `--doi` 指定队列内尚未处理的文章，但当前有未完成篇时禁止切换。
2. `python -X utf8 scripts/review_workflow_v9.py show`：仅向当前审读助手输出完整输入，禁止重定向到普通日志或报告。
3. 助手按照 v9 阅读标题、摘要及元数据，生成短小 assessment JSON（无完整摘要）。必须有 `doi`、`review_input_sha256`、`class`、`reason`、`evidence`、`reviewer`。证据必须是输入里的连续短语，至多35词。
4. 收录还必须提供 `screening_summary`（一句12–30词）和六项 `hard_checks`：`doi_identity`、`whitelisted_issn`、`eligible_type`、`date_in_window`、`title_matches`、`date_conflicts_resolved`。`hard_check_evidence` 必须按同名字段保存具体来源引用或已核实值。无法确认时不能收录，应留 review。
5. `python -X utf8 scripts/review_workflow_v9.py submit --assessment <assessment路径>`：检查 DOI、输入哈希、当前规则哈希、证据和说明句。永久决策逐篇写入 `reports/v9-2026-09/closed-loop-decisions-v1/` 后才关闭当前篇。
6. 提交成功后再运行 `next`。`status` 分别报告已审读、获取失败和未完成数量。

获取失败时仍停在当前篇，可先浏览器补证。浏览器提取的私有 JSON 结构为 `{"metadata": {...}, "abstract": "..."}`，只能存于 `.private/`。metadata 必须含本文 DOI 已匹配、标题、出版社 URL、获取时间、明确摘要依据（`publisher.Abstract` 或 `publisher.citation_abstract`）。用 `import-browser --private-packet <路径>` 接回同一篇审读。这个接口不负责操控浏览器；由助手调用授权浏览器读取后导入。

确实无法获取时用 `defer --reason <具体原因>`，保存 `review` 与 `subject_scope_assessed=false`，保留待补材料清单。已缓存摘要禁止用 defer 跳过审读。`retry` 仅用于当前获取失败项的有理由重试，并保留旧尝试记录；不要对429等限流连续重试。

## 中断与公开边界

若已核实 Nature 出版社页面明确标为 `RESEARCH BRIEFINGS`、`CLINICAL BRIEFINGS` 或 `POLICY BRIEF`，可用 `exclude-type --assessment <类型证据JSON>` 或 `Workflow.exclude_publisher_type(evidence)` 完成文章类型硬排除，无需获取摘要。证据必须包括当前 DOI、doi_match=true、匹配标题、出版社 URL、明确类型标签、获取时间、reviewer 和 reason。保存类型输入哈希，标为 `subject_scope_assessed=false` 与 `publisher_type_excluded`；不得将导语缓存为摘要，不计为完成主题审读。仅覆盖上述明确标签，不能由 DOI 前缀推断类型。

- 当前篇在发请求前持久化；重启优先恢复它，不重新从队首开始。
- 输入改变或规则改变会阻止套用旧判断。流程锁防止两个进程同时操作；异常终止后若锁残留，先核实原进程已退出再处理，不能盲目删除。
- 私有缓存保存摘要，公开候选与报告保存短证据、结论和来源。`show` 输出只能用于当前审读。
- 本流程不自动更新生产网站，也不会把获取失败或尚未审读统计为主题排除。
- 路由报告是固定输入；新的逐篇决策覆盖旧状态时按 DOI 合并，不覆盖历史报告。

## 已验证范围

真实样本已验证 Crossref 与 APS 出版社两条路径，均完成缓存、当场审读与保存结论。数据库其他读取器、浏览器导入、中断恢复、跨篇阻断和输入绑定有离线测试；尚未逐一实测所有出版社的网页布局。新布局或访问失败将留下明确的补证状态。
