# 收录与分类规则 v7（试验）

## 来源与边界

`config/sources.json` 是可执行规则的唯一来源。保留 27 本期刊白名单；名单外期刊一律不收录，包括 Scientific Reports 与未列入的 MDPI 期刊。不以出版商、SCI 身份或影响因子推断单篇文章质量。期刊名称不能代替 ISSN 验证。

首页重点区限 Nature Communications、Physical Review X、Science Advances、PNAS、Physical Review Letters，以 `featured_journals` 为准，不使用历史 `tier` 字段决定。Nature、Science、Nature Physics 仅退出重点区，仍可收录复杂网络文章。“其他期刊”是名单的补集，不是低质量评级。

唯一方向为复杂网络：网络结构和网络上的动力学。不因一般 chaos、bifurcation、soliton 或 Hamiltonian 信号独立收录文章。网络中的同步等动力学研究仍属于范围内。

## 分类依据与本站映射

以下是有依据的浏览分类，不声称参考来源逐字定义了本站所有标签。分类规则是英文关键词启发式，不是专家审定。

| 本站维度 | 主题 | 参考依据与映射说明 |
| --- | --- | --- |
| 复杂网络 | 网络结构与生成；社区发现与网络推断、重构；传播、扩散与渗流；同步、博弈与集体行为；鲁棒性、级联与控制 | [PRE 官方分区](https://journals.aps.org/authors/guidelines-section-selection-physical-review-e) 的 Networks and Complex Systems，以及 [Journal of Complex Networks 范围](https://academic.oup.com/comnet/pages/About)；本站将范围中的问题组织成五个可重叠标签，不将其视为五个官方分区。 |
| 其他 | 未命中上述研究主题 | 保留的分类不确定性，不是新的科学领域。固定放在导航末尾；与明确主题互斥。 |

“社区发现”“网络推断”“网络重构”均是研究任务名词短语，避免把裸名词“社区”与两个过程名混排。分类词表并不等于完整语义理解：标题表述差异、摘要缺失都会造成“其他”，不能把它自动视为不相关，更不能为压低数量而强制分配主题。后续应逐篇检查“其他”的命中依据，再讨论是否补充同义词或调整主题边界。

## 方法标签（与主题正交）

主题回答“文章研究什么”，方法标签回答“文章如何研究”。方法标签不参与网络科学相关性的放行，不构成 AI 或图机器学习的绿色通道；一篇文章可以有多个方法标签，也可以没有可验证的方法标签。当前仅使用四个保守标签：`theory`（理论模型）、`empirical`（实证或观测数据）、`simulation`（数值或计算模拟）和 `ai_ml`（人工智能与机器学习）。标签只依据标题和摘要中可核对的证据生成，证据不足时留空。

图数据或图模型的出现本身不构成网络科学证据。若图只是分子、材料或生物对象的输入表示，而研究问题并不分析关系结构或网络动力学，文章不会因 `ai_ml` 标签而自动收录。相反，若机器学习研究传播、同步、渗流、网络推断或网络控制，则同时获得网络主题和 `ai_ml` 标签。

## v7 科学原则与实现边界

本站汇集指定期刊中最近 90 天的网络科学论文，涵盖关系结构及其组织、网络方法和相互作用系统中的动力学，同时收录运用网络科学方法开展的实证与应用工作。标题、摘要是否出现 network/graph 不是必要条件。

识别隐式相关研究时，检查关系结构、研究方法、动力学机制：连接或依赖的组织方式是否被研究；是否构建和分析这些关系；是否研究结构、耦合方式、节点差异对系统行为的影响。这些是补充路径，不要求同时满足。一般稳定性、矩阵或复杂性表述并不自动证明网络相关性。

### 可执行的第一阶段

- 标题与摘要中的各句分别评估，不强制标题命中，也不把不相干句子的弱词拼成证据。
- 四条自动收录路径：明确网络概念；网络分析方法；网络对象及结构／动力学；隐式相互作用及动力学。记录 `screening_routes`，包括路径、证据来源 title/abstract 和命中词。
- 标题明确讨论网络结构／机制时可作为证据；仅在摘要中出现 network 加 structure/stability/reconstruction 等泛词时，还需图意义或具体机制证据，否则留待核查。这样避免因摘要背景泛词误收，同时保留标题明确的常规网络研究。
- 删除 v5 的生物医学模型特殊排除规则。一般中心性等方法应用不因贡献大小而排除。
- 软件模块化等歧义概念需要关系语境；机器学习和材料网络不能仅因名称通过，但正文主题的摘要证据可以覆盖标题歧义。
- 不命中、摘要缺失或语境不明保留 review，而不是 not_core。明确类型／日期／期刊不符才排除；一般机器学习应用的排除还要求摘要存在、未发现网络证据。日期不完整单列待核查，不补造日期。
- 输出 `screening-report.json` 逐条判定表（标题、DOI、原因、摘要是否可用、检索路径），不保存摘要或全文。收录名单与待核查名单分离。

### 仍需人工或语义核查的部分

当前实现仍是可解释的证据词表，不声称理解全部研究含义，也没有自动读取全文。没有线索的记录不会被遗忘，但仍需逐条核查待核查列表；自动收录也可能仅命中背景表述，应抽查并保留反例。本轮目的为验证规则，不以收录数量增加证明准确性。

`Disorder-promoted stability` 的摘要描述网络异质性与稳定性，可独立通过；那篇 PNAS 鼠神经系统工作依据网络结构、方法及动力学证据通过，无 DOI 专属例外。

### 来源覆盖与运行

- 27 刊范围不变；每刊按首选 ISSN 查询窗口内全部记录，最多 10 页 × 1000 条作为安全上限。达到上限或提前返回空页而总数未取尽时视为不完整，不更新有效快照。offset 不超过 10,000 范围。
- Crossref 结果取尽不等于出版方目录全部核对。单一首选 ISSN、元数据延迟、日期不完整仍需核查。
- 任一期刊请求失败或截断均保留有效快照。试采集使用 `--out reports/v6-trial` 与发布数据隔离。
- 当前发布仅重筛原有 181 个 DOI；不运行全窗口扩展，未实现每日增量、自动出版方补录或待核查语义裁决。日期与 DOI 去重定义不变。
- 作者占位值保留审计信息，不作为已核实姓名展示；不从 Anonymous 推断发表状态。
- 主题是收录后的独立步骤，一文可多类，“其他”仍与具体主题互斥。

## 重点期刊展示顺序

采用 2025 年 Journal Impact Factor 降序（核对日期 2026-09-29）；仅影响期刊名称说明行，六篇文献仍按发表日倒序，而非按影响因子排序。

| 名称说明行 | 2025 JIF | 依据 |
| --- | --- | --- |
| Nature Communications | 18.1 | [出版方指标页](https://www.nature.com/ncomms/journal-impact) |
| Physical Review X | 16.8 | [APS 2026 年指标公告](https://www.aps.org/about/news/2026/06/journals-performance-metrics-citation-reports) |
| Science Advances | 13.9 | [Xia & He Publishing 对 2025 JIF 的报道](https://xiahepublishing.com/m/2475-7543/MRP-2026-06271)；本次访问 AAAS 官方指标页返回 403，此项暂据二手报道，尚待官方页面复核。 |
| PNAS | 9.5 | [PNAS 官方指标页](https://www.pnas.org/about/article-journal-metrics) |
| Physical Review Letters | 9.4 | [APS 2026 年指标公告](https://www.aps.org/about/news/2026/06/journals-performance-metrics-citation-reports) |

说明行只有 PNAS 缩写；所有重点文献卡片使用期刊全称，包括 Proceedings of the National Academy of Sciences。期刊范围控件使用“全部期刊／重点期刊／其他期刊”，避免“水准”暗示单篇质量保证。

## ISSN 校验记录

同日根据 [Network Science 官方主页](https://www.cambridge.org/core/journals/network-science) 修正纸刊／电子 ISSN 为 2050-1242／2050-1250；根据 [Nature Reviews Physics 官方主页](https://www.nature.com/natrevphys/) 修正电子 ISSN 为 2522-5820。此前值未通过校验位测试。

实际接口检查：Journal of Statistical Physics 的纸刊 ISSN 在本次窗口返回 0 条，而电子 ISSN 返回 47 条，故将电子 ISSN 1572-9613 设为首选检索入口。Network Science 的纸刊和电子 ISSN 在同一窗口均返回 0 条；不能推断出版方实际没有文章。

2026-09-29：根据 [Springer 官方期刊页](https://link.springer.com/journal/332) 将 Journal of Nonlinear Science 的电子 ISSN 修正为 1432-1467；1573-269X 属于 Nonlinear Dynamics，不能共享。根据 [SIADS 官方主页](https://epubs.siam.org/journal/sjaday) 将其 ISSN 修正为 1536-0040。测试检查 ISSN 校验位与跨期刊唯一性；校验位通过本身不能证明期刊身份正确。
