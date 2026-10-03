# 元数据特征与官方类型：380篇补证的观察

这些特征用于决定下一步核查渠道。它们不是自动科学分类器，不改变既有科学范围、日期或类型规则。

## 已验证的特征

| 数据特征 | 本轮实际观察 | 后续操作 | 不能推出的结论 |
|---|---|---|---|
| Crossref abstract只有单句 | Science若干条实际是标题下导读句；官方另有较长的明确Abstract段落 | 按DOI核实官方栏目，并区分deck、Abstract和正文 | 单句不能直接支持研究内容审读或类型排除 |
| 编辑选文说明 | In Science Journals / In Other Journals在官方目录属于RESEARCH HIGHLIGHTS | 目标主标题DOI匹配后，按现有非目标类型规则排除 | RESEARCH大栏目不表示每条都是Research Article |
| 书名、出版社、页数附在题名中 | 官方BOOKS ET AL.的主标题比Crossref题名短 | 核实官方DOI和书评栏目，保留附加书目差异 | 不能只按题名模式直接排除 |
| 泛化article或research-article | PNAS微塑料条目官方是INNER WORKINGS，Front Matter也列为科学报道，但dc.Type为research-article；Nature Clinical Briefing也被数据库写成article | 具体栏目和目标身份优先于通用元数据；保存冲突 | 非空abstract和数据库article标志均不保证原创研究 |
| 无abstract字段 | PRL的jv51-thxz有官方摘要，但HTTP解析器因缺失citation_issn拒收 | 核对官方期刊、可见DOI、主h1及页脚ISSN，再提取明确摘要 | 自动取证失败不等于出版社没有摘要 |
| APS题名不匹配 | 公式空格、同位素、上下标、连字符、重音及MathML可造成差异；也发现真正的题名修订 | 逐条保存原题名、citation题名、实际h1和身份核验依据；实质变化继续核查版本 | 不能全局删除符号或无条件用DOI替代全部身份检查 |
| 摘要混入Close/Next/PHYSH | APS外层Abstract容器还包含图片控件和主题标签 | 用abstract-section-content中的摘要段落；拒收污染版本，保存新版本和旧哈希 | 容器存在、文本非空、字数足够不表示材料正确 |
| HTTP403或安全验证页 | 部分Science官方页在普通浏览器可读，但HTTP仍被拦截 | 通过正常浏览器读取明确摘要和必要元数据；不保存HTML、正文或cookie | 403不说明文章无摘要或不属于目标类型 |
| Accepted Paper且Abstract空白 | PRL lvpn-gblk的普通浏览器页面明确显示接收稿和空Abstract标题 | 保留材料不足；后续同DOI补核正式发表材料 | 接收状态或摘要空白不证明非研究类型 |

## 固定55篇材料不足组的官方类型核验

54篇Science按四个官方期号目录逐DOI核对，均未列在RESEARCH ARTICLES子栏目。具体为：NEWS 25、RESEARCH HIGHLIGHTS 8、BOOKS ET AL. 4、PERSPECTIVES 13、POLICY ARTICLES/POLICY FORUM 4。另1篇PNAS属于INNER WORKINGS。

这仅描述固定缺证组，不能推断Science全体文章的比例或将这些标签一律排除。38篇有明确非目标类型依据；另15篇依据实际官方摘要排除。2篇保留未决：Noise and diversity can boost stability已有明确摘要，科学范围需核查；Observation and exploration widen the menu确认Perspective，但未取得明确摘要。

官方目录：

- [Science 393/6815](https://www.science.org/toc/science/393/6815)
- [Science 393/6816](https://www.science.org/toc/science/393/6816)
- [Science 393/6817](https://www.science.org/toc/science/393/6817)
- [Science 393/6818](https://www.science.org/toc/science/393/6818)
- [PNAS目标报道](https://www.pnas.org/doi/10.1073/pnas.2628766123)、[Front Matter](https://www.pnas.org/front-matter)

## 必须保留的反例与信息边界

- [Noise and diversity can boost stability](https://www.science.org/doi/10.1126/science.aek9090)：Crossref只有提示，但官方Perspective的Abstract讨论真实的异质性、噪声和集体稳定性。Perspective与短提示都不能成为自动排除理由；本篇已依据官方明确Abstract摘段纳入core；正文访问受限，未声称全文审读。
- [Network-Irreducible Multiparty Entanglement in Quantum Matter](https://journals.aps.org/prl/abstract/10.1103/jv51-thxz)：自动渠道拒收曾经是解析/身份字段问题，官方摘要实际存在。其主题另按实际内容判断，材料可获取与科学纳入是不同问题。
- [Eight-unit-cell electronic modulations…](https://journals.aps.org/prl/accepted/10.1103/lvpn-gblk)：官方接收页的摘要内容确实为空，不能因此把接收稿归为新闻。
- 不借用Perspective卡片里的RELATED RESEARCH ARTICLE作为目标文章类型或摘要；目标h3 DOI与嵌套相关研究DOI分别核验。
- 官方明确标为Abstract的commentary excerpt只记录为该篇的摘要摘段，不能称为完整研究Article摘要。足够支持独立范围排除时可使用；信息不足仍保留未决。
- 数学排版转纯文本可能损失符号。保留提取限制；不能据此解释公式或编造缺失变量。范围判断只能使用仍然明确的主要研究陈述。

## 为什么数据库没有摘要

目前能验证的是字段缺失、导读句被填入abstract、通用类型过粗、身份解析拒收、访问拦截或官方页摘要空白。不能从这些现象确定出版社为何不向Crossref存入摘要；版权、提交政策、更新延迟等只能作为待验证设想，不能写成已确认原因。Crossref与OpenAlex可能共享来源，不作为两份独立科学证据计数。

## 可复用执行顺序与留痕

1. 复用已经核验的缓存和历史失败原因，不重新遍历全候选池。
2. 优先对官方目录的目标主标题DOI核实具体栏目；明确非目标类型不再索取摘要。
3. 对需科学审读的条目，依授权渠道取得明确摘要。4个文献任务并行，各来源遵守自身限额；429停止继续任务与渠道。
4. 核实DOI、标题、期刊和ISSN；浏览器读取必要元数据与明确Abstract；用户授权的无摘要短评论可在线实际审读正文，仅留简短观察。
5. 主代理实际审读；保存来源、获取时间精度、字段特征、冲突、材料哈希、判断及输入哈希。材料与判断均保留旧版本。
6. 每批最多100篇；全部已保存判断或明确延期后再进下批。已读未决与未取得可用材料分别统计。

正式执行记录在reports/2026-09/screening-log.jsonl，完整摘要只在Git忽略的新目录.private/abstract-cache/v9。观察事件supplement_type_verified、supplement_identity_observed等并不表示语义审读已完成；最终以assessment/assessment_corrected为准。

## 后续浏览器补证：具体类型与反例

- Nature官方[其他投稿栏目说明](https://www.nature.com/nature/for-authors/other-subs)把Correspondence解释为面向编辑的公共/政策议题通讯，Futures为虚构故事；本轮Nature杂志的World View、Comment、Nature Index、Spotlight及Technology Feature结合具体目录与代表页确认性质。Nature的Spotlight特写栏目和本网站九刊Spotlight展示范围不同。不能把Nature杂志Comment的解释套用于NC科学Comment或Matters Arising。
- PNAS的Commentary、Letter及Opinion可以无明确摘要而有科学正文；Opinion的dc.Type甚至可为research-article。具体栏目与实际内容必须独立核验，通用类型不足以决定是否为目标研究文章。
- Science的LETTERS编辑通讯不同于PRL研究Letters；SA的The next century of spin具体标签为Introduction to Special Issue。不同期刊同名类型不能机械合并。
- [水星Comment](https://www.nature.com/articles/s41467-026-74974-1)的Abstract实际上是一张没有alt文字的图形摘要。DOM只返回标题并不代表栏目内容为空；实际看图后可读出主要地质论证。缓存仅保存图中四个论述文字框的转录，未保存图像/PDF/正文；图例没有转录，不据此作定量解释。
- APS MathML题名可能导致合法摘要被身份门控拒收。b728-gh5v属于数学排版差异；bgv1-lpq7和gny7-xz9s则是同一明确官方DOI下的实质题名差异。保留数据库与官方题名，不将后者伪装成空格规范化；本轮确认材料属于该DOI，未证明历史题名修订的时间序列。Crossref Anonymous是作者占位符，不证明未发表或非研究类型。
- [lvpn-gblk接收稿](https://journals.aps.org/prl/accepted/10.1103/lvpn-gblk)的实时官方Abstract确实空白，搜索索引却出现摘要。实时页与索引不同，不能把搜索片段当作当前官方摘要。本篇经用户单独授权，采用[arXiv明确摘要](https://arxiv.org/abs/2609.09615)和全部13位作者/题名匹配作范围排除。页面列出唯一v1；直接v1链接抓取失败，读取来自官方未版本化页面，版本链接仅作稳定引用。未把arXiv日期当期刊日期，未声称两个版本相同。

## 本轮闭合与记录修复

固定380篇结果为377 excluded、3 core，未决与未审读均为0；详见[本轮报告](../reports/2026-09/supplement-380.md)。新增两篇评论明确标明证据性质，未声称是原始研究或专家全文审定。

此前共享临时日志视图导致15处链指针断接，根因已修复。全部原事件内容和备份保留，修复只重建尾部36条链字段，正式追加log_chain_repaired。此后正式写入由主线程串行完成；已核验全链及最新判断输入/使用材料哈希，39项离线测试通过。历史supplement_batch_closed中的decisions_saved可能包含既有延期事件，历史字段不改写；最终统计以最新独立判断为准，新闭合事件把判断与延期分开记录。

41份本轮私有工作目录摘要中转副本迁入.private/abstract-cache/v9/legacy-work，原始字节和旧路径哈希保留，工作目录仅留指针；正式判断使用的规范缓存版本不变。没有完整摘要、正文、HTML或PDF进入公开报告、网站或Git输出。
