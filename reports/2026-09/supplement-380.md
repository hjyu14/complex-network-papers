# 固定380篇补证结果（2026-10-03）

## 最终结果

|集合|core|transferable_application|excluded|review|未审读|
|---|---:|---:|---:|---:|---:|
|本轮固定380篇|3|0|377|0|0|
|完整2822篇池|18|2|2802|0|0|

当前20篇纳入中18篇已发表、2篇已接收。此前17篇纳入判断与本轮范围外的全部判断不变。网站保持此前17篇快照，本轮未发布或推送。

## 新增三篇

|文章|类别与证据|收录依据|
|---|---|---|
|[Criticality and Universality of the Generalized Kuramoto Model](https://journals.aps.org/prl/abstract/10.1103/61hq-rs8x)|core；完整官方摘要及官方研究Letter栏目|完全图与局部耦合晶格上的同步临界性、频率牵引连接矩阵和普适类。官方Published为2026-09-29，期号日2026-10-02另存。|
|[Noise and diversity can boost stability](https://www.science.org/doi/10.1126/science.aek9090)|core；Perspective的官方明确Abstract摘段|异质相互作用群体的集体稳定与噪声效应。正文访问受限，未读全文；评论综述所报道理论，不将原研究的新结果归为评论原创贡献。官方日期2026-09-17。|
|[From leaf veins to bus lanes: Emerging simplicity in complex spatial systems](https://www.pnas.org/doi/10.1073/pnas.2622915123)|core；无摘要Commentary，按用户例外在线实际审读全部可见论证|空间运输网络的资源约束优化、导流自适应、树/环结构及生物网络与公交理论类比。未声称评论提出新的原始数据或方法。官方日期2026-09-02。|

三篇均保存一句话screening_summary，未新增transfer类别。类型、日期、科学判断及其证据性质分别记录。

## 如何闭合

按固定manifest分小批推进，最多100篇、4个文献任务并行；Crossref公共池遵守串行请求与启动间隔。优先恢复已有缓存与已知失败路线，不重新搜整池。取得材料后由主代理实际审读，官方非目标类型可有据排除；排除后停止不必要的日期补核。每批判断或明确延期后再推进，最后只回访原380篇内的9项，不以题名或摘要缺失代替分类。

用户确认两项证据例外：无摘要短科学评论可在线实际审读，只留简短记录；仅lvpn-gblk可用题名与全部13位作者匹配的作者arXiv摘要完成范围排除。后一材料没有直接期刊DOI关联，接收版本等同性未核实，限制原样保留。预印本未加入候选池，常规研究文章未改为正文取证。

可复用字段经验见[数据特征文档](../../docs/evidence-data-features.md)，当前规则见[筛选规程](../../docs/screening-protocol.md)。它们是补核线索：栏目名、单句提示、MathML差异、图形摘要和作者占位符都不能单独裁定科学范围。

## 验证与留痕

- 380个唯一DOI均有最新独立分类；无review、deferred_unassessed或not_assessed。
- 全部2822条最新判断的record/input哈希有效；2364份使用材料版本的内容及摘要哈希有效，路径在允许的私有缓存内。无摘要评论观察与判断的身份、类型、来源及证据哈希绑定。
- screening-log.jsonl全链有效。此前15处链断接已修复，原事件内容与备份保留，修复及后续写入有事件记录；历史闭合统计字段不改写，最终计数从最新判断重建。
- candidates.json、coverage.json、collection-log.jsonl与HEAD逐字节一致；旧17篇纳入判断和本轮范围外判断均未改变。
- 39项Python离线测试通过；git diff --check通过。网站未改动。
- 完整摘要只在Git忽略的.private/abstract-cache/v9；41份旧工作中转副本已迁入允许路径，原字节、旧路径哈希及指针保留。全文、HTML、PDF未保存。

正式逐篇证据、渠道失败、用户授权、规则版本、旧判断及输入哈希均在screening-log.jsonl；报告不重复完整摘要或逐批日志。结论为基于明确摘要/摘段或授权短评论在线审读的辅助范围筛选，不是专家全文评审，也不表示解决了出版社全覆盖的所有外部限制。
