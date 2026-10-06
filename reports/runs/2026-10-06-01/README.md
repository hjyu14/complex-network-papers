# 2026-10-06-01

日期窗口和 as-of 均为 2026-10-06；范围为冻结白名单全部 13 刊。本轮审核和覆盖补证已完成，已封存并选入发布清单。

## 当前结果

- 原始来源采集观察时间：北京时间 2026-10-06 10:38:38–10:40:56；四刊浏览器补证在同日约 11:20–11:30 完成。逐来源准确时间存于日志和补证；仅表示读取时刻快照，不承诺当天全天覆盖。
- 共登记 95 个 DOI：2 个窗口内 NC 候选，93 个 PNAS 候选首次在线日期早于窗口（仅纸刊日期命中），后者不进入本轮科学审读。
- 2 个窗口内候选均已由主代理实际阅读身份匹配的官方明确摘要：`excluded=2`；`core=0`、`transferable_application=0`、`review=0`、`deferred_unassessed=0`。无已知窗口内未审读或活跃项。
- 待人工科学裁决：无。待人工补资料：无。无未解决整刊覆盖阻塞。

## 已分类文献

| DOI | 题名 | 判断依据 |
|---|---|---|
| 10.1038/s41467-026-78192-7 | MOF-mediated cascade photoreactions under nanoconfinement for defluorination of per- and polyfluoroalkyl substances | 排除：主要贡献为催化材料、PFAS 脱氟反应与纳米限域机制，未建立网络科学主要问题。 |
| 10.1038/s41467-026-78460-6 | Real-time visualization of G2L4 reverse transcriptase in DNA repair via microhomology-mediated end joining | 排除：主要贡献为 DNA 修复分子机制和反应中间体，分支 DNA 不是独立网络组织贡献。 |

判断、硬检查、材料版本和输入哈希见 `screening-log.jsonl`；冻结书目、规则及覆盖见 `candidates.json`、`inputs/` 和 `coverage.json`。摘要仅在 Git 忽略的私有缓存；可重建分类视图位于 `.private/work/2026-10-06-01/exports/`。

## 覆盖补证与限制

原始输入已完成 9 刊来源枚举和候选清单，Science、SA、PNAS、Chaos 的原始目录失败标志保留。四刊现由独立浏览器补证闭合；所有选定 ISSN 的 Crossref online/print/pub 查询亦已完成。正式补证见 [publication-evidence.json](publication-evidence.json) 和 [允许书目及核对依据](evidence/browser-directory.json)，逐文件 SHA-256 和审核日志事件绑定原候选。未修改原始 `candidates.json`、`coverage.json` 或 `collection-log.jsonl`。

| 期刊／官方入口 | 全类型目录与边界依据 | 本窗口结果 |
|---|---|---|
| [Science](https://www.science.org/toc/science/current) | 当前 394/6819 全部 45 个主标题 DOI；First Release 全部 11 个 DOI，日期倒序，最新 10 月 1 日；当前期 Next 无后续期号。相关研究链接不算目标。 | 无新在窗 DOI。 |
| [Science Advances](https://www.science.org/toc/sciadv/current) | 当前 12/40 全部 83 个主标题 DOI，日期为 9 月 30 日或 10 月 2 日；官方明确无 First Release，Next 无后续期号。 | 无新在窗 DOI。 |
| [PNAS](https://www.pnas.org/toc/pnas/123/40) | 123/40 全部 93 个 DOI 与原始候选精确集合相等，首次在线日全部相等；未来 41/42 期分别 32/2 篇，最远期无下一期；无访问或类型过滤的最新搜索完整第一页 20 篇均为 10 月 5 日，构成早于窗口的完整守卫页。 | 93 项仅纸刊日期命中，优先首次在线日全部出窗；无新在窗 DOI。 |
| [Chaos](https://pubs.aip.org/aip/cha) | 全刊通配符列表按 Date - Newest First，完整第一页 20 篇逐篇核对 DOI、题名、ISSN 和 `.article-date`，日期 10 月 5 日至 9 月 23 日；十月在编期全部 12 个 DOI 与列表相等，尚无后续期号。现有 AIP 导入器 `normalize` 在 live-as-of 模式严格通过。 | 无新在窗 DOI；卷期月首日期未冒充在线日。 |

PNAS 两个出窗题名保留上标／空格排版差异，不宣称严格字段核对全部完成。来源级原始覆盖标志仍为原始读取结果，公开发布另保留补证引用和完成结论；该轮没有全天覆盖承诺，也不能保证后续回填的文章已在本次观察中出现。

## 故障恢复、验证与收尾

- 沙箱启动故障由 `.agents` 目录所有者异常引起，经用户授权仅恢复该目录所有者；站点拒绝另由本聊天保存的拒绝记录引起，用户亲自清空后已恢复。两项原因和成功核验均保留于审核日志；代理未绕过拒绝、未解验证码，Science 和 Chaos 的自动检查自行完成。
- 恢复期间验证：Python 115 项测试、前端 36 项测试、JavaScript 语法、现有网站快照一致性、目录职责检查及历史归档 113 文件核验全部通过；这些检查不替代本轮覆盖完成。

- 原始采集输入、判断输入及完整日志链校验通过；空纳入集的作者完成事件已保存；[publication.json](publication.json) 钉住原始轮、作者及补证。现有阅读说明集合不变。
- 私有发布预览核对：既有 152 篇全部保留，新增、移除及修改 DOI 均为 0；更新窗口截止日期至 10 月 6 日。上线验证以本次提交对应的 GitHub Pages 部署为准，精简验收存私有目录。
- 正式来源、判断和摘要缓存保留。私有中转的核验与清理计数随发布验收记录；没有对应删除授权的文件保留，不从发布授权推导删除权限。
