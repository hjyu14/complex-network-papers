# Network Observatory · 复杂网络文献观察

无需登录的复杂网络文献看板。聚焦网络结构与网络上的动力学，提供白名单期刊近 90 天论文的元数据与 DOI 原文链接；不独立收录一般非线性动力学，不存储全文，不使用数据库。

正式访问：[文献网站](https://hjyu14.github.io/complex-network-papers/) · [收录规则文章](https://hjyu14.github.io/complex-network-papers/rules.html)。首次访问默认英文，可切换中文并记住选择；不翻译论文标题或作者，不重置筛选条件。

## 运行

Python 3.11+，无第三方依赖。

```sh
python -m unittest discover -s tests -v
node --test tests/test_app.cjs
python scripts/collect.py
python -m http.server 8000 --directory site
```

浏览 http://localhost:8000 。页面不能通过 file:// 直接读取 JSON。

## 科学口径与限制

- 初始数据源为 [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)。它不是复杂网络专门索引，有收录延迟、摘要和日期缺失。
- 收录类型为 `journal-article`（可能包括综述）；排除预印本、明确的更正/撤稿通知。类型依赖出版方元数据，不独立认证同行评审。
- 以运行日（Asia/Shanghai）为终点，包含当天及之前 89 天。日期优先级：`published-online` → `published-print` → `published` → `issued`。优先可用日期只有年/月时排除，绝不补造日。日期回退会在界面显示。未来日期排除。
- 规则 v5：27 本期刊 ISSN 白名单为硬过滤，不再全库搜索 network。仅访问期刊 works 接口，按出版日期倒序，每期刊最多 5 页 × 100 条；达到预算上限的查询明确显示截断，不声称全量覆盖。
- 新增应用主导的生物医学模型标题筛选；有明确网络机制或方法任务的脑网络论文仍可收录。这是保守的编辑边界，不是对所有应用研究的科学质量判断，具体词表和误收／漏收风险见规则文档。
- 作者 Anonymous 等占位值保留审计字段，但不作为人名显示。页面提示缺失或部分缺失，并提供出版方链接；每轮采集重新读取作者元数据，不据此推断出版状态。
- 仅收录复杂网络，保留 5 个研究主题，未命中主题的放入末尾“其他”；允许多标签。页面支持主题、期刊、时间、期刊范围筛选，不再展示网络类型和应用领域。一般机器学习应用排除，材料网络需图意义证据。详见[分类依据与边界](docs/classification.md)。
- 分类是多标签启发式，不是专家审定；仅用于辅助浏览。记录每篇命中依据。摘要只在内存中参与筛选，不写入发布数据。
- 重点区采用独立五刊名单：Nature Communications、Physical Review X、Science Advances、PNAS、Physical Review Letters。期刊说明按 2025 年影响因子顺序，文献卡片按日期显示最新六篇且期刊名全称；来源与核实限制见分类文档。Nature、Science、Nature Physics 仍保留在普通收录范围。“其他期刊”不表示单篇质量较低。
- “查看全部重点文献”同步设置可见的期刊范围控件；可改为全部／其他期刊，或点击“返回全部文献”。选具体期刊会清除期刊范围限制；改期刊范围会重置具体期刊，避免两者相互锁死。
- DOI 去重。只有 Crossref 元数据可确认的期刊标记才进入重点区。原文可能需要订阅。
- 更正/撤稿识别不完整；阅读前以出版方最新版本为准。

## 项目结构

```text
config/sources.json       检索、期刊、筛选与分类规则
scripts/collect.py        有界采集与原子写入
tests/test_collect.py     离线确定性测试（不是真实论文数据）
tests/test_app.cjs        前端筛选逻辑测试（不替代浏览器布局检查）
docs/classification.md   分类依据、映射及已知边界
site/                    唯一发布目录
site/data/papers.json     最近一次完整成功的元数据快照
site/data/status.json     最近一次采集尝试状态
.github/workflows/        手动/定时采集、测试与部署
```

## 部署与更新

GitHub Pages 使用 Actions 部署 `site/`。工作流允许手动运行，每天 UTC 22:20（北京时间次日 06:20）更新，也在 main 推送后运行。定时运行可能延迟。

采集请求部分失败时不替换上次有效论文快照，但保存失败状态并部署警告；最后将工作流标记失败。预算截断与请求失败分别报告。首次失败或历史快照不兼容当前规则时显示不可用，不生成示例论文，也不把旧规则结果冒充新结果。成功但零条匹配时如实展示空结果。站点只发布 site/，自动运行不请求付费服务。

每次成功生成的数据和尝试状态提交回仓库，便于追溯。规则变化必须显式更新配置版本与测试。密钥不得提交；当前采集无需 API key。
