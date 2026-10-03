# Complex Network Papers · New Workflow

九刊文献工作流的起点。当前已执行九刊九月书目采集、来源对照及全量首轮筛选；NC 已知候选的最后一条由用户提供出版截图确认，910 条已有来源或用户核实依据，目录分页稳定性仍未通过。当前网站发布本次已确认的九月审核快照；没有自动语义分类器或日更。

## 当前方向

- 首阶段仅处理 `config/sources.json` 中的九刊；先核对目录覆盖，再补证、筛选和上线。
- 初始试验窗口沿用 2026-09-01 至 2026-09-30；网站最终目标为最近 90 个日历日，增量更新尚未实现。
- 文献范围限网络结构、网络上的动力学和可迁移网络科学方法的主要贡献。
- 目录覆盖、材料取得、科学审读和发布分别记录；缺口和未决项明确保留。
- 按需从旧版本引入文件，每次检查其适用性；不自动导入历史文献池。

## 必要文件

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 当前工作约束 |
| `config/sources.json` | 九刊 ISSN 白名单及当前九刊 Spotlight 名单 |
| `docs/screening-protocol.md` | 已确认的科学、日期、类型及证据边界 |
| `.gitignore` | 私有缓存和凭据隔离 |
| `.gitattributes` | 文档与配置换行约定 |

## 旧成果与恢复

- 旧成果保存提交：`8e0932a2523eeadbee50b4650c4c5ccff6128c8b`，已同步至 `origin/main`。
- 旧工作目录：`E:\cursor_file\papers_of_complex_networks`。
- 新工作目录：`E:\cursor_file\papers_of_complex_networks_newflow`。
- 当前开发分支：`codex/new-workflow`；与旧版本共享 Git 历史。
- 从保存提交按需取文件，例如：

```powershell
git restore --source=8e0932a2523eeadbee50b4650c4c5ccff6128c8b -- scripts/private_abstract_cache.py
```

引入旧文件时检查其依赖、硬编码路径和过期规则；旧结果不能自动成为本流程的审读结论。

旧流程的历史摘要缓存仍在旧目录的 `.private/abstract-cache/v9/`，未提交、未整包复制。Git 历史不能恢复该缓存，后续按 DOI 核对身份、来源、版本与哈希后复用，保留原始来源及导入记录。

新流程所有新增私有材料均写入 `E:\cursor_file\papers_of_complex_networks_newflow\.private\`：完整摘要放 `abstract-cache/v9/`，临时编辑和最小取证工作文件放 `work/`。旧目录只用于历史资料读取。两处新目录都受现有 `.gitignore` 保护；不保存正文、HTML、PDF或凭据。

旧保存提交通过 79 项 Python 测试、14 项前端测试及 `node --check site/app.js`。三个历史状态 JSON 文件末尾含字面量 `\n`，按原样保存，不作为新流程输入。本起点仅完成配置和目录检查，没有可运行的采集或网站测试。

## 九刊书目采集

入口复用 NMI 试验程序并更名为 `scripts/collect_candidates.py`，仅登记书目、核对日期与目录覆盖。执行办法、实际数量、未决 DOI 和限制见 `docs/collection-workflow.md`。

本轮只保留三个正式结果文件：`reports/2026-09/candidates.json`（候选）、`coverage.json`（覆盖与差异）、`collection-log.jsonl`（追加证据与执行记录）。`window_membership` 独立于严格字段核对状态；数量核对完成不等于标题／日期字段全部一致，也不等于相关性筛选完成。

```powershell
python -m unittest discover -s tests -v
python -X utf8 scripts/collect_candidates.py --as-of 2026-10-03 --out reports/2026-09 --resume
```

恢复会验证完整日志链和当前结果哈希，复用完成的请求；非零退出表示严格核对仍有未决项，应阅读 coverage，不表示结果为空。浏览器转录的官方目录证据已进入日志；当前 Science／SA／PNAS 不支持从空输出目录自动复现浏览器步骤，需要按执行文档补证。NMI 当前恢复复用正式日志中的完整试验证据，新输出按统一流程采集；独立的四个试验 JSON 已按用户授权删除。旧试验文件及入口可从本地提交 `bdfa863` 取回，未推送。

## 材料取得与筛选

执行入口为 `scripts/screen_candidates.py`，按新缓存／核验旧缓存、Crossref 精确 DOI、官方页、OpenAlex、普通浏览器、用户补证的顺序取证；具体限制见筛选规程。完整摘要仅保存于新仓库忽略目录，公开的 `reports/2026-09/screening-log.jsonl` 保存来源尝试、哈希、硬检查和简短判断。结果可从该日志导出，无需再存每批报告。

```powershell
python -B -X utf8 scripts/screen_candidates.py status
python -B -X utf8 scripts/screen_candidates.py next
python -B -X utf8 scripts/screen_candidates.py fetch cache
python -B -X utf8 scripts/screen_candidates.py fetch crossref
```

有明确、身份匹配的摘要后，当前审读者实际阅读，并将含 `doi`、`category`、`reason`、`evidence_summary`、`reviewer`、`hard_checks` 的判断 JSON 交给 `decide <path>`。`hard_checks` 分别记录 identity/type/date；纳入另需 `screening_summary`、全部硬检查通过和完整窗口内日期。程序不自行生成语义判断。缺失摘要依序继续 `fetch publisher`、`fetch openalex`；正常浏览器补证仅提取明确 Abstract 与必要元数据，可从新仓库 `.private/work/` 的核验材料 JSON 用 `import-material <path>` 导入。浏览器不是无需人工审查的后台接口。

逐篇模式用 `fetch-active` 一次执行剩余自动渠道，取得匹配摘要即停。用户已授权先做批量自动取证检测：首轮 30 篇，最多 4 个并发请求；随后按检测结果调整，单批上限 100 篇。渠道失败或身份未核验的条目转入延后材料队列，保持未审读；可自动取得材料的条目集中实际审读，上一批判断或延期记录齐全后才推进下一批。

```powershell
python -B -X utf8 scripts/screen_candidates.py batch --size 30
python -B -X utf8 scripts/screen_candidates.py collect-batch --workers 4
python -B -X utf8 scripts/screen_candidates.py review-pack --limit 30
python -B -X utf8 scripts/screen_candidates.py decide-pack .private/work/decisions.json
```

`review-pack` 输出完整摘要，仅用于当前私有审读会话，不能重定向到普通报告或提交；`decide-pack` 输入是当前审读者实际阅读后写出的逐篇结论列表，程序不自行分类。已由官方明确标为新闻、勘误等非目标类型的条目只准备栏目证据，无需抓摘要。Review、Perspective 等不会自动排除。

`next` 对未保存判断的活跃篇仍返回同篇。批次按期刊轮转、各刊剩余 `(date, doi)` 顺序登记；不提前抓整个候选池的摘要。`export` 输出允许的逐篇 JSONL（不含摘要），不自动创建结果副本。日志链与固定候选／规程哈希在恢复时校验；授权的取证调度修订用 `adopt-rules` 追加规程哈希及理由，旧判断继续保留旧哈希，科学规则不能借此静默修改。

2026-10-03 首先完成九刊各一篇及罗马道路样例的首批 10 篇，另完成 NMI 模块化与 PRX 化学反应网络两篇定向样例；这是流程验证选样，不代表总体相关率。这 12 篇中 `core=2`、`excluded=9`、`review=1`；10 篇取得明确摘要，2 篇依据官方非目标栏目排除。罗马道路文章已读摘要但科学边界未决；PRX 化学反应网络按已授权接收日例外标为“接收”。

随后按用户授权执行 30 篇自动取证速度检测：4 个并发任务，程序取证用时 17.828 秒，24 篇取得明确摘要、6 篇已有非目标类型依据，本批没有自动渠道失败延期项。随后当前审读者实际读完材料并保存 30 个判断（28 excluded、2 review）；从自动检测启动到这批判断全部持久化共约 3.75 分钟，不包含此前程序改造时间。两篇 review 分别是 PRL 波包网络与渗流模型（研究类型未核实、实验验证限制保留）和 PNAS 神经回路输入输出图谱（科学范围边界与类型未决）。上述时间仅是本批实测，不能直接保证全量平均速度。

上述两批累计已完成 42 篇：`core=2`、`excluded=37`、`review=3`；34 篇有私有明确摘要，8 篇依据官方非目标栏目排除。

随后完成固定 50 篇并发取证与三子代理盲审测试，详见 [实测报告](reports/2026-09/benchmark-50.md)。4 并发用时 48.813 秒，单并发 168.297 秒，均取得 39 份有效摘要、6 条非目标类型依据、5 篇延期；8 并发遇 429 中止，2 并发及重复轮次未执行。三代理并行阶段 407.187 秒，主代理独立基准 253.088 秒，本轮未获审读提速；科学／最终类别一致率为 46/50、45/50，均不是专家准确率。默认保留 4 并发取证、主代理集中实际审读，429 停止新任务及后续渠道。

另完成同三篇的串行／三代理各一篇小测试，记录追加在上述实测报告中。修复测试准备错误后，热身补测主代理审读、校验与保存三篇共43.953秒，三代理加主代理逐篇复核与保存共149.531秒，包含共同正式入库成本；取证另计7.562秒。本轮也未获得审读提速，单次小样本和材料熟悉效应不支持普遍结论。一篇神经回路文章的范围分歧经实际回读后确认 core，另外两篇 excluded。

性能测试结束时累计已判断 90 篇：`core=3`、`transferable_application=2`、`excluded=71`、`review=14`；当时剩余 2,732 篇窗口内候选为 `not_assessed`，其中 5 篇已明确延期。90 篇判断中 76 篇有固定私有摘要，14 篇依据明确非目标栏目排除。此为历史检查点；当前全量进度见下节。

实际路线包括 Crossref、官方 Abstract 和普通浏览器；本批新旧缓存均未命中，PNAS 的 OpenAlex 也无摘要。APS 接收稿页没有 citation 元数据，初版 HTTP 解析器未识别其 Abstract 容器，浏览器补证后已追加解释，不能把解析未取得写成文章无摘要。PNAS 通用元数据将 In This Issue 写作 research article，按官方可见 This Week in PNAS 具体栏目排除并保留差异。SA 官方页日期 9 月 2 日与 Crossref 纸刊日期 9 月 4 日并列未决，尚未明确核实首次在线日期的语义；原“已确认”硬检查已用追加修正事件收紧，不改写旧记录。该篇的主题排除独立成立。`status` 和 `export` 采用最新追加判断，导出同时保留 inventory_date 与已确认 date；日期未决时 date 为 null。

原始三份采集结果不改写。数量／来源覆盖、材料取得、未审读、已审读未决和发布分别记录，不能互相替代。

## 九月全量首轮筛选结果（2026-10-03）

采用 4 个文献任务并行取证，Crossref 同时最多 1 请求，随后由主代理实际逐篇审读。性能测试之后完成 28 个批次，单批最多 100 篇，上一批全部判断或明确延期后才进入下一批。初始窗口内的 2,822 篇均已有处理记录，未进入处理的候选为 0；这表示固定候选池的首轮处理闭合，不代表所有出版社目录缺口已消除。

| 当前状态 | 篇数 | 含义 |
|---|---:|---|
| `core` | 23 | 网络结构或网络动力学为主要贡献，硬检查通过 |
| `transferable_application` | 4 | 具有可迁移网络科学贡献，硬检查通过 |
| `excluded` | 2,125 | 已读后排除，或官方明确非目标类型 |
| `review` | 345 | 实际审读后科学范围或身份／类型／日期仍未决 |
| `deferred_unassessed` | 325 | 未取得可用的正确摘要，保留未审读状态，待下一轮补证 |
| 合计 | 2,822 | 2,497 篇已有判断，325 篇明确延期 |

2,497 篇判断中，2,240 篇使用固定私有摘要，257 篇依据官方明确非目标栏目判断。已读未决项包含类型未决 313 篇、日期未决 172 篇、身份未决 37 篇；这些原因可重叠，不能相加作为文献总数。全量批次中另有 112 篇明确保存科学范围未决，历史试验项的具体理由仍以逐篇日志为准。

本轮实际读到并拒收了数据库误填的受众标签、数据集说明、新闻图注、截断摘要、疑似回复正文片段及作者信息；共 7 个缓存版本已标记拒收，均未被最新正式判断使用。旧版本和拒收原因继续留痕，不将题名或数据库摘要标志当作科学判断。

原始 `candidates.json`、`coverage.json`、`collection-log.jsonl` 的 SHA256 与开轮固定值完全一致；正式日志链、全部最新判断的输入哈希、材料身份和内容哈希通过全量核验。已判断集合与延期集合互斥，合并覆盖全部窗口候选。完整摘要未出现在公开筛选日志，缓存及工作草稿受 Git 忽略；29 项 Python 测试通过。核验与闭合摘要已追加到 `screening-log.jsonl` 的 `screening_round_closed` 事件，未另建逐批结果副本。

下一轮分别处理 325 篇材料补证和 345 篇已读未决。材料补证优先复用已登记的失败渠道及官方链接，通过普通浏览器或用户材料核验；已读未决按身份、类型、日期与科学范围分别补证。27 篇拟纳入仍是摘要辅助筛选结果，尚未发布，不能称为全文专家审定。逐篇结果可用 `python -B -X utf8 scripts/screen_candidates.py export` 从日志导出；该输出不含完整摘要。


## 27 篇拟纳入文章定向复核（2026-10-03）

从 345 篇已读未决中固定 27 篇科学范围拟纳入记录，实际回读其既有完整摘要版本，并逐篇核实官方文章类型。此轮没有处理其余 318 篇已读未决，也没有重新采集全池摘要。27 篇分别来自 PNAS 12 篇、Science Advances 9 篇、PRL 4 篇、Science 2 篇。

本轮新增纳入 26 篇：`core=24`、`transferable_application=2`；另 1 篇继续 `review`。26 篇官方类型为 Research Article 21 篇、PRL 研究 Letter 3 篇、PNAS Brief Report 1 篇、Science Advances Research Resource 1 篇。可见具体栏目优先于通用数据库类型；Brief Report 和 Research Resource 按实际研究内容审读，没有套用新闻排除规则。

三篇原日期冲突均取得官方页面明确的 JSON-LD `datePublished`，且与可见出版日期一致：`10.1126/sciadv.aef2894`、`10.1126/sciadv.aeg1229` 在线日期为 2026-09-02，`10.1126/sciadv.aee9425` 为 2026-09-09。采用现有首次在线日期优先规则，原纸刊日期与官方 `dc.Date` 保留为另一日期字段，不改写原始候选日期。此次也保留了九月底文章与十月卷期日期的区别。

仍未决的是 [Preferential attachment with local flexibility](https://journals.aps.org/prl/accepted/10.1103/9y9m-q7qj)：摘要支持核心网络结构研究，官方确认 Accepted Paper 和 2026-09-21 接收日；目前没有找到明确研究子类型。接收日例外继续有效，但出版状态不能代替类型标签，因此暂不纳入。PRL 另外三篇的类型来自各自官方期号中实际包含目标文章的 LETTERS 栏目。

当前累计状态为 `core=47`、`transferable_application=6`、`excluded=2125`、`review=319`、`deferred_unassessed=325`，合计仍为 2822 篇。累计 53 篇通过摘要辅助筛选及元数据硬检查；这是筛选结果，尚未发布，也不是全文专家审定。等离子体波包网络文章明确保留摘要中的“尚待实验验证”限制。

官方元数据来源、核验结果及摘要版本哈希追加在 `reports/2026-09/screening-log.jsonl`：本轮以 `metadata_review_round_started` / `metadata_review_round_closed` 标识，逐篇保存 `metadata_verification_attempt`、`metadata_verified`、`scope_review` 和 `assessment_corrected`。最初部分网页观察未记录精确获取时刻，事件明确标注仅能确认本会话日期；持久化时间不冒充获取时间。原判断和固定摘要版本继续保留；没有另建公开结果副本或保存网页正文。

本轮完成后再次验证：29 项 Python 测试通过；全部 2497 篇最新判断的输入哈希、2240 份使用中的摘要材料身份及哈希、27 篇本轮元数据证据哈希有效；已拒收材料使用数为 0，三份原始采集文件字节未变，判断与延期集合互斥且完整覆盖固定候选池。核验结果以 metadata_review_integrity_verified 事件留痕。


## PRL 接收稿规则补充与应用（2026-10-03）

用户确认 PRL Accepted Paper 的类型证据例外，规则已补充至 `docs/screening-protocol.md`。官方接收页及完整官方摘要能支持原创研究判断时，可通过现有科学筛选纳入，明确注明“根据官方摘要判断，具体子类型待确认”和“已接收，待正式发表”；正文暂不可读不阻断摘要筛选。证据不足或有类型冲突仍保留未决，不能把所有接收稿自动当作 Letter。首次在线日期尚未确认时沿用接收日例外，接收稿与已发表文献分开统计，正式发表后按同一 DOI 追加核验。

按新规则重新审读 [Preferential attachment with local flexibility](https://journals.aps.org/prl/accepted/10.1103/9y9m-q7qj)：官方确认的模型提出、数值模拟与严格随机分析支持原创研究判断，科学分类为 `core`，状态为已接收，日期为“2026-09-21 接收”，已发表日期保持空值，具体子类型待正式发表后补核。用户确认的是证据规则；本次逐篇科学分类依据实际摘要审读，仍非全文专家审定。

当前累计为 `core=48`、`transferable_application=6`、`excluded=2125`、`review=318`、`deferred_unassessed=325`，合计 2822 篇。54 篇通过筛选的记录包括依接收日例外纳入的记录，不能称为54篇已发表文章；此前53篇及1篇未决的数字保留为规则修订前历史检查点。

规则修订及本篇新判断追加至 `screening-log.jsonl`，保留旧规则哈希、旧判断、原接收证据及固定摘要版本；其他记录未自动改用新规则，无新增公开摘要或结果副本。

补充核验：54 篇通过筛选的记录中，2 篇按既有接收日例外纳入（含此前的 PRX 接收稿和本篇 PRL 接收稿）。29 项 Python 测试及 git diff --check 通过；全部2497篇最新判断的输入哈希、所用摘要身份及哈希有效，原始三文件字节未变；导出保留本篇接收状态、接收日及未确认具体子类型。核验结果已追加留痕。


## 117篇边界共性裁决与执行（2026-10-03）

117篇旧边界队列包含60篇范围争议、55篇材料不足和2篇已有规则可处理项。用户明确裁决：罗马道路网络文章纳入，其他59篇科学边界文章排除，因为未达到本项目要求的网络科学问题边界；七组较宽的草案推荐未采用。另2篇按现有材料和既有范围规则排除。55篇材料不足保留review，待官方类型或明确研究摘要补证。

规则、逐篇对应及结果保存在[裁决报告](reports/2026-09/scope-boundary-117.md)，稳定边界补入筛选规程。逐篇记录追加至screening-log.jsonl，保存用户裁决来源、旧判断、固定材料和新输入哈希。网络用语、领域连接描述或一般互动本身不能支持纳入；未来文章按实际网络科学问题审读。

当前core=49、transferable_application=6、excluded=2186、review=256、deferred_unassessed=325，合计2822。55篇历史/当前通过筛选记录中，新增道路网络文章已按新边界纳入；此前54篇保留旧规则判断，已登记一致性复核清单，不能称为全部符合新规则。历史数字保留为当时检查点，接收稿与已发表文献分开统计。未发布。

本轮逐篇回读62篇现有缓存材料并保存判断；55篇材料不足、54篇历史纳入及其他未涉及记录的判断未变。已核验日志链、固定记录/材料及新旧输入哈希、硬检查和原始三文件字节。后续分别进行55篇补证和54篇历史纳入的一致性复核。


## 201篇有据拟排除记录的闭合（2026-10-03）

用户确认：已有足够匹配证据支持范围排除的文章可直接excluded，不再补核日期、具体类型等字段；原冲突保留，可能纳入的文章仍需全部必要硬检查通过。稳定规则见筛选规程。

本轮固定201篇：198篇已有scope_review=excluded，另3篇早期记录已有明确科学排除理由。检查全部已保存的具体理由及固定材料绑定，复用历史已完成的科学审读，针对可能含网络用语及短摘要的案例回读缓存；未宣称重新逐篇审读201篇完整摘要。按100、100、1篇串行追加独立排除判断，不进行网络请求。原判断、原科学审读规则及输入哈希保留，201篇的元数据硬检查原样不变，停止为这些排除项补核。

201篇来自Science Advances 166篇、PRL 32篇、PRX 3篇；保留类型未决201篇、日期未决166篇、身份未决35篇（原因重叠）。材料DOI、题名及白名单ISSN的匹配检查和内容哈希已核验；已拒收版本未被使用。未决的出版社题名呈现差异保留，不被写成已核实。

当前core=49、transferable_application=6、excluded=2387、review=55、deferred_unassessed=325，合计2822。55篇review均是此前保留的材料不足记录（Science 54篇、PNAS 1篇）；325篇仍未取得可用正确摘要，保持未审读状态。此前54篇历史纳入的一致性复核清单仍待处理；其判断未变。

逐篇记录及闭合检查追加至screening-log.jsonl，不另建公开结果报告。三个原始采集文件、全部摘要版本、其余2296篇正式判断均未变，规则新旧版本及输入哈希可追溯。未发布。


## 已纳入55篇一致性复核（2026-10-03）

实际回读原core49与transfer6的全部固定摘要，按已确认网络科学边界复核：保留core13、transfer2，排除32，范围待裁决8。原6篇transfer逐篇内容、去向及全部55篇依据见[复核报告](reports/2026-09/inclusion-review-55.md)。此前将特定回路机制或领域流程可复用直接当作网络科学贡献的理由过宽，本轮纠正；未修改科学规则。

当前core=13、transferable_application=2、excluded=2419、review=63、deferred_unassessed=325，合计2822。review为原55篇材料不足加新增8篇科学范围争议；原380篇补证队列未处理。15篇保留中13篇按发表日期纳入，2篇（PRX热力学空间、PRL优先连接）按接收日例外纳入，不计作已发表文献。

逐篇旧判断、材料版本和硬检查原样保留，新复核追加至screening-log.jsonl并绑定新旧输入与材料哈希；未涉及的2442篇判断及原始采集三文件未变。无新增网络请求、完整摘要公开副本、发布或推送。


## 8篇范围争议用户裁决闭合（2026-10-03）

用户明确纳入接触网络渗流与肿瘤群体运动、LLM意见动力学两篇（恢复core），其余6篇因领域专门性不适合本项目选文而排除；逐篇结果见[55篇复核报告的最终裁决](reports/2026-09/inclusion-review-55.md)。具体正例补入筛选规程，未建立领域黑名单。

当前core=15、transferable_application=2、excluded=2425、review=55、deferred_unassessed=325，合计2822。17篇纳入含15篇已发表与2篇已接收；transfer仍是等离子体渗流、宿主—病毒缺失链接推断两篇。8篇范围争议已闭合，剩余380篇为55篇材料不足及325篇未审读延期。其他2489篇正式判断、原始采集三文件、材料版本及硬检查均未改变；用户裁决与新旧判断哈希追加留痕。未发布、未推送。


## 九月审核快照网站发布

用户授权先发布17篇确认纳入记录（core15、transfer2；已发表15、已接收2），暂不处理380篇补证。网站复用旧页面样式，只导出新流程纳入集合；每篇中英文一句话阅读说明及逐篇主题存于`config/publication-notes.json`，绑定最新判断哈希。网站包含双语流程与规则、目录覆盖限制、接收稿标记和快照截止日筛选；未复制旧文献池或完整摘要。

```powershell
python -B -X utf8 scripts/publish_snapshot.py
python -B -X utf8 scripts/publish_snapshot.py --check
python -m unittest discover -s tests -v
node --check site/app.js
node --test tests/test_app.cjs
python -m http.server 8001 --directory site
```

Pages从`codex/new-workflow`的`site/`发布，入口为`.github/workflows/publish-reviewed.yml`；仅提交已审核的快照并执行校验，不运行采集或补证。旧main定时重筛工作流停用，避免用旧181篇池覆盖新快照。运行和追溯约定见[发布说明](docs/publication.md)。

## 九刊 Spotlight 与作者补充（2026-10-03）

用户确认九刊全部列入Spotlight，因此全站纳入数和重点期刊总数均为17；首页仍只展示最新六篇。17篇作者已补齐：15篇来自DOI、标题和ISSN匹配的Crossref元数据，两篇接收稿来自明确显示同一DOI的APS官方署名。完整原序名单和来源可在卡片收录依据中展开；本轮未重采书目、未重审科学范围，380篇补证仍待后续处理。作者元数据及旧版本保存在`reports/2026-09/author-metadata.json`，导出器与正式日志校验其哈希。
