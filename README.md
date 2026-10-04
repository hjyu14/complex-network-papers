# Complex Network Papers

面向网络科学读者的文献网站，收录网络结构、网络上的动力学和可迁移网络科学方法。按期刊白名单采集整刊候选，核对来源后实际审读，并保留逐篇证据与判断。

网站：[Complex Network Papers](https://hjyu14.github.io/complex-network-papers/)。当前发布的是 2026 年 9 月审核快照，共 122 篇（93 篇已发表、29 篇已接收）。最近 90 天与自动日更尚未启用。

## 从哪里开始

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 稳定工作约束 |
| `config/sources.json` | 白名单、采集窗口、Spotlight |
| `docs/collection-workflow.md` | 整刊采集与覆盖核对 |
| `docs/screening-protocol.md` | 科学范围、证据与审核规则 |
| `docs/evidence-data-features.md` | 数据特征、补证线索与反例 |
| `docs/publication.md` | 作者、阅读说明、多轮发布与验证 |
| `config/release.json` | 明确选择发布轮次 |
| `reports/<run-id>/` | 每轮候选、来源、正式日志与冻结输入 |
| `site/` | 网站部署文件 |

## 九月扩刊与正式发布

窗口为 **2026-09-01 至 2026-09-30**，13 个白名单期刊的固定清单共 3,467 篇，全部完成分类；122 篇纳入，3,345 篇排除，无未审读或未决项。固定清单完成不等于出版方目录绝无遗漏；Nature Communications 分页覆盖限制仍保留。

新增四刊原始轮次为 `reports/2026-09-expansion-01/`，131 篇疑难项的正式裁决为 `reports/2026-09-expansion-adjudication-01/`。发布使用 `reports/2026-09-expansion-publication-01/` 的显式引用视图，验证原轮及裁决哈希，不改写任何原始记录，也不伪造一次新的科学审查。现有 `reports/2026-09/` 保持不变；新增四刊不加入 Spotlight。

采集、审读与作者补充均显式指定轮次，详细命令见相应文档。旧轮使用自己的 `inputs/`，不会随全局白名单或工作规程变化而被重新解释。

## 本地核验

```powershell
python -m unittest discover -s tests -v
python scripts/publish_snapshot.py --check
node --check site/app.js
node --test tests/test_app.cjs
python -m http.server 8003 --directory site
```

无第三方运行依赖。完整摘要与开发历史位于 Git 忽略的 `.private/`，不得上传或部署。开发历史不是科学判断的依据；正式来源、证据哈希、判断和冻结规则保留在仓库，见各轮记录。
