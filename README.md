# Complex Network Papers · New Workflow

九刊文献工作流的起点。当前已有 NMI 有界书目采集试验，尚无主题筛选器、网站或自动部署。

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

## NMI 书目试验

入口为 `scripts/collect_nmi.py`，仅登记书目、核对日期与目录覆盖，不读取摘要或进行主题筛选。执行记录见 `docs/nmi-collection-pilot.md`；运行输出使用新目录，不覆盖旧轮次。

```powershell
python -m unittest discover -s tests -v
python -X utf8 scripts/collect_nmi.py --as-of 2026-10-03 --out reports/nmi-2026-09/new-run
```

下一步：根据 NMI 试验结果核验其他期刊的目录渠道，分别适配来源结构。
