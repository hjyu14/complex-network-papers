# 收录与分类规则 v8

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

## v8 收录边界与执行方式

网络结构、网络上的动力学或可迁移的网络科学方法须为主要研究问题或贡献。常规网络工具应用不再单独构成收录资格。

- `core`：一般网络结构、生成、网络方法及网络动力学；领域例子不改变主要问题。
- `transferable_application`：领域研究明确提出可迁移网络方法或机制；逐篇记录可迁移内容，不设数量配额。
- `excluded`：具体领域问题或一般非线性动力学为主体，缺少主要网络科学贡献。
- `review`：证据不足或边界未决，暂不展示。

现有 181 篇采用用户确认的标题／摘要审读登记表 `config/scope-review-v8.json`：110 核心、7 可迁移应用、58 范围外、6 未决。部分记录仅有标题证据，不声称全文专家审定。

执行器先做类型、日期、DOI、ISSN 校验，再应用审读登记表。未知 DOI、标题变化进入待核查；登记表不是 DOI 回归测试夹具或对自动语义分类器的隐蔽覆盖，而是当前固定池显式的编辑收录依据。尚未实现通用语义筛选器，扩展文献仍需授权与审读。

主题在收录后独立按标题与摘要词表生成，允许多标签；不据分类命中决定是否收录。研究方法标签及筛选已停用。期刊边界、日期口径、固定基线和失败保留策略不变。

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
