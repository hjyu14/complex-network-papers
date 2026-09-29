# Network Observatory · 复杂网络文献观察

无需登录的复杂网络文献看板。聚焦网络结构和网络上的动力学，提供近 90 天正式期刊论文的元数据与 DOI 原文链接；不存储全文，不使用数据库。

## 运行

Python 3.11+，无第三方依赖。

```sh
python -m unittest discover -s tests -v
python scripts/collect.py
python -m http.server 8000 --directory site
```

浏览 http://localhost:8000 。页面不能通过 file:// 直接读取 JSON。

## 科学口径与限制

- 初始数据源为 [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)。它不是复杂网络专门索引，有收录延迟、摘要和日期缺失。
- 收录类型为 `journal-article`（可能包括综述）；排除预印本、明确的更正/撤稿通知。类型依赖出版方元数据，不独立认证同行评审。
- 以运行日（Asia/Shanghai）为终点，包含当天及之前 89 天。日期优先级：`published-online` → `published-print` → `published` → `issued`。优先可用日期只有年/月时排除，绝不补造日。日期回退会在界面显示。未来日期排除。
- 双路检索：14 个领域词组 + 7 个白名单期刊内的 network 检索；按相关性取每查询最多 200 条。此预算是初版的覆盖限制，不是全量索引。采集报告显示结果总数、取回数和截断情况。
- 规则 v2：标题含明确网络科学信号；或标题同时有网络对象和结构/动力学信号；或标题有网络对象、摘要有明确网络科学与机制信号。一般神经网络/深度学习应用排除，少数明确研究网络动力学的标题例外。材料类 network 需要额外的节点、边、中心性、渗流等图/网络科学证据。英文检索与规则存在语言偏差。
- 分类是多标签启发式，不是专家审定；仅用于辅助浏览。记录每篇命中依据。摘要只在内存中参与筛选，不写入发布数据。
- 顶刊区采用 `config/sources.json` 的明确 ISSN 白名单：NC、PNAS、PRL、SA、Nature、Science、Nature Physics。并非通用期刊排名，也不推断文章质量，且不绕过主题筛选。
- DOI 去重。只有 Crossref 元数据可确认的期刊标记才进入重点区。原文可能需要订阅。
- 更正/撤稿识别不完整；阅读前以出版方最新版本为准。

## 项目结构

```text
config/sources.json       检索、期刊、筛选与分类规则
scripts/collect.py        有界采集与原子写入
tests/test_collect.py     离线确定性测试（不是真实论文数据）
site/                    唯一发布目录
site/data/papers.json     最近一次完整成功的元数据快照
site/data/status.json     最近一次采集尝试状态
.github/workflows/        手动/定时采集、测试与部署
```

## 部署与更新

GitHub Pages 使用 Actions 部署 `site/`。工作流允许手动运行，每天 UTC 22:20（北京时间次日 06:20）更新，也在 main 推送后运行。定时运行可能延迟。

采集部分失败时不替换上次有效论文快照，但保存失败状态并部署警告；最后将工作流标记失败。首次失败且没有历史数据时显示不可用，不生成示例论文。成功但零条匹配时如实展示空结果。站点只发布 site/，自动运行不请求付费服务。

每次成功生成的数据和尝试状态提交回仓库，便于追溯。规则变化必须显式更新配置版本与测试。密钥不得提交；当前采集无需 API key。
