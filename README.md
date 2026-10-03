# Complex Network Papers · New Workflow

九刊文献工作流的起点。当前已执行九刊九月书目采集和来源对照；NC 已知候选的最后一条由用户提供出版截图确认，910 条已有来源或用户核实依据，目录分页稳定性仍未通过。尚无主题筛选器、网站或自动部署。

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
| `config/sources.json` | 九刊 ISSN 白名单及原 Spotlight 名单 |
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

完整摘要缓存仍在旧目录的 `.private/abstract-cache/v9/`，未提交、未复制到新目录。Git 历史不能恢复该缓存，后续复用需显式读取并核对。

旧保存提交通过 79 项 Python 测试、14 项前端测试及 `node --check site/app.js`。三个历史状态 JSON 文件末尾含字面量 `\n`，按原样保存，不作为新流程输入。本起点仅完成配置和目录检查，没有可运行的采集或网站测试。

## 九刊书目采集

入口复用 NMI 试验程序并更名为 `scripts/collect_candidates.py`，仅登记书目、核对日期与目录覆盖。执行办法、实际数量、未决 DOI 和限制见 `docs/collection-workflow.md`。

本轮只保留三个正式结果文件：`reports/2026-09/candidates.json`（候选）、`coverage.json`（覆盖与差异）、`collection-log.jsonl`（追加证据与执行记录）。`window_membership` 独立于严格字段核对状态；数量核对完成不等于标题／日期字段全部一致，也不等于相关性筛选完成。

```powershell
python -m unittest discover -s tests -v
python -X utf8 scripts/collect_candidates.py --as-of 2026-10-03 --out reports/2026-09 --resume
```

恢复会验证完整日志链和当前结果哈希，复用完成的请求；非零退出表示严格核对仍有未决项，应阅读 coverage，不表示结果为空。浏览器转录的官方目录证据已进入日志；当前 Science／SA／PNAS 不支持从空输出目录自动复现浏览器步骤，需要按执行文档补证。NMI 当前恢复复用正式日志中的完整试验证据，新输出按统一流程采集；独立的四个试验 JSON 已按用户授权删除。旧试验文件及入口可从本地提交 `bdfa863` 取回，未推送。

下一步进入材料取得与筛选。全部候选目前为 `not_assessed`；本轮未请求或保存摘要，也未发布。文章发表日期确认、链接失效、目录覆盖执行状态分别保留，不能互相替代。
