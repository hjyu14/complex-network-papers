# Complex Network Papers

面向网络科学读者的文献网站，收录网络结构、网络上的动力学和可迁移网络科学方法。按期刊白名单采集整刊候选，核对来源后实际审读，并保留逐篇证据与判断。

网站：[Complex Network Papers](https://hjyu14.github.io/complex-network-papers/)。当前发布的是 2026 年 9 月审核快照，共 20 篇（18 篇已发表、2 篇已接收）。最近 90 天与自动日更尚未启用。

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

## 下一轮：扩刊验证

继续使用 **2026-09-01 至 2026-09-30**，新增期刊另建 `reports/2026-09-expansion-01/`。现有 `reports/2026-09/` 保留，完成新轮审核后按 DOI 合并发布。新期刊名单仍待确定；不自动加入 Spotlight。

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
