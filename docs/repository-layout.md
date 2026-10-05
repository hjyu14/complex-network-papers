# 文件职责与生命周期

## 仓库导航

| 位置 | 职责 |
|---|---|
| `README.md`、`README.zh-CN.md` | 面向公众的英文／中文介绍，不记录逐次开发过程 |
| `AGENTS.md` | 每次任务必须遵守的稳定约束和文档入口 |
| `.agents/skills/netsci-literature-update/` | 项目级文献更新技能及收尾指引；引用仓库规则与脚本，不存采集输出 |
| `config/` | 当前期刊与筛选配置、发布选择、阅读说明 |
| `docs/collection-workflow.md` | 整刊登记、时间窗口和来源覆盖核对 |
| `docs/screening-protocol.md` | 科学范围、证据要求、纳入／排除／待裁决规则 |
| `docs/evidence-data-features.md` | 证据字段、来源与材料处理约定 |
| `docs/publication.md` | 作者补全、直接发布清单、快照校验及部署边界 |
| `docs/repository-layout.md` | 本文：目录、文件生命周期和历史恢复规范 |
| `scripts/` | 可复用的采集、审读、发布和文件管理程序；不存任务输出 |
| `tests/` | 合成测试及回归检查；不充当正式文献判断来源 |
| `reports/` | 正式候选、覆盖、判断、冻结规则与历史档案，入口为 `reports/README.md` |
| `site/` | 网站代码、图标、样式及唯一当前公开数据快照 |
| `.github/` | GitHub 校验／部署配置；不负责自动采集 |
| `.private/` | 不提交的摘要缓存、按轮中转、开发历史与本地备份 |
| `.gitignore`、`.gitattributes` | 私有输出隔离、行尾及原始证据字节保护 |

## 单一来源

- `config/sources.json`：当前期刊、ISSN、Spotlight 和采集参数；每轮 `inputs/` 冻结其实际使用版本。
- `docs/screening-protocol.md`：当前科学与证据规则，不以当前文字重新解释历史判断。
- `reports/runs/<run-id>/`：一次采集及审读；重试、补证和中断恢复不另建 `final` 或 `retry` 结果树。
- `reports/reviews/<review-id>/`：封存后或跨轮的明确复议，绑定旧判断与输入。不是新整刊覆盖。
- `config/release.json`：直接选定原始轮，并钉住各轮 `publication.json`。该文件列出有序修订及作者、补证来源；不嵌套发布视图。
- `config/publication-notes.json`：当前中英文短说明与主题，按 DOI 绑定正式判断。
- `site/data/`：唯一当前网站快照，不是审核记录的来源。

## 轮次内容

普通轮次包含 `README.md`、`inputs/{manifest.json,sources.json,screening-protocol.md}`、`candidates.json`、`coverage.json`、`collection-log.jsonl`、`screening-log.jsonl`。发布时增加作者元数据及 `publication.json`；独立补证可使用 `evidence/` 和明确的引用清单。文件数量不设机械上限，但新文件须有独立职责。

当前复议保留迁移前的冻结候选子集、规则和日志，避免伪造新判断；不复制整刊候选或完整作者集。`parent-manifest.json` 中的旧路径属于当时记录，其原位置可通过归档索引定位，不当作当前路径直接打开。

来源事件与判断串行追加。封存轮的日志可保存为 `.jsonl.gz`，解压后的字节和哈希完全不变；压缩日志及具有 `publication.json` 的轮次禁止通过采集／审读 CLI 继续写入。新的正式复议使用 `reviews/`。不通过重算哈希掩盖判断变化。

## 派生输出与临时材料

`python scripts/manage_runs.py export --run reports/runs/<run-id>` 将可重建的 `review.json` 和 `review.md` 写到 `.private/work/<run-id>/exports/`。相同命令替换该派生视图，不创建多套 `final-v2`。正式统计和判断始终来自日志，临时清单不能成为发布输入。

浏览器转录、决定草稿、调试输出和补证工作清单放 `.private/work/<run-id>/`；必要书目和审核依据经校验导入正式记录。摘要只留在 `.private/abstract-cache/v9/`，身份、来源、获取时间、内容哈希及被引用版本保留。不保存全文、HTML、PDF 或凭据。

作者采集默认拒绝覆盖。`--resume` 复用已核验作者，仅处理缺失项；`--refresh-doi` 显式选择重核对象。旧的变动记录及头信息追加到审核日志，可结合当前未变行恢复前一版本，不复制整份 `author-metadata-vN.json`。封存后的作者调整须走新审核／发布选择，不原地修改封存来源。

### DOI 共享摘要缓存与按轮查看

主缓存位置为 `.private/abstract-cache/v9/objects/<DOI哈希前两位>/<完整DOI哈希>/<材料版本哈希>.json`。不同采集／复议轮共享同一 DOI 的材料，判断始终绑定实际使用的具体版本，不随“最新版本”改变。日期属于轮次和书目元数据，不用于拆分同一 DOI 的主缓存。

缓存复用只追加 `material_cached` 事件记录来源；不把新的导入时间写进材料，从而不因重复使用产生新版本。真正内容或证据元数据变化仍形成不同材料版本。历史版本不合并、不改写。缓存命中不是当前发表状态核验，accepted 转正式发表仍须按筛选规程取得新官方证据。

历史 `<DOI哈希>/<版本>.json` 引用由 `scripts/abstract_cache.py` 确定性解析到分片位置，正式日志的旧路径和哈希不改写。历史浏览器／人工输入保留在缓存根下 `legacy-inputs/`，不作为主缓存自动检索；未来完整摘要也不得进入普通 work 输出。所有摘要材料仍在原授权的私有缓存边界内。

`manage_runs.py export --run ...` 在原有私有 `exports/review.json`、`review.md` 中增加判断使用的材料哈希、历史引用、当前路径和本地可用状态，不另存摘要副本。没有引用或本地缺文件明确标记，不用其他版本替代；该视图可重建，不是新的裁决来源。迁移清单位于 `.private/history/work-cleanup-2026-10-05/cache-migration.json`，逐文件保留新旧路径及字节哈希。

## 历史归档与恢复

`reports/archive/legacy-2026-10-05/manifest.json` 对全部 113 个旧报告文件登记旧路径、字节数、SHA-256、新正式位置或 ZIP 成员。`artifacts.zip` 保存不再承担当前独立结果职责的历史文件，包括旧发布视图、复测中间材料、回溯样本和重复导出。当前正式文件只保留一份，压缩时以解压字节校验。

归档中的旧作者完成事件仍是当前作者数据的核验依据；因此 ZIP 是公开构建输入之一，不是可以随意删除的缓存。构建直接按成员读取并验证，不解压到工作区，不执行归档中的内容。历史哈希链内的旧路径是历史标识，通过迁移索引解释，不能批量替换并重写旧事件。

```powershell
python scripts/manage_runs.py check-layout
python scripts/manage_runs.py verify-archive --manifest reports/archive/legacy-2026-10-05/manifest.json
python scripts/manage_runs.py trace --doi 10.1103/vxkg-41kp
```

恢复时按 manifest 找到指定 ZIP 成员，解压到独立私有目录并比对 SHA-256；禁止覆盖现有正式轮次。原始 Git 提交也记录在 manifest，不重写 Git 历史。归档不是备份全部私有摘要；要复现摘要审读仍需要私有缓存或重新取得授权材料。

## 清理与检查

发布前执行目录检查、归档核验、发布一致性测试及隐私检查。未知输出报错后判断用途，不自动删除或挪入 `evidence/`。清理私有中转前确认必要依据已持久化，无未完成任务或正式依赖；需取得相应删除授权。被引用的摘要版本、正式判断和有效来源不得作为临时文件清掉。

临时文件也有收尾：

- 工作中：中转仅放 `.private/work/<run-id>/`，不在 `work/` 根目录散落批次文件。可重建导出与预览使用固定路径；判断草稿、浏览器转录在导入成功并核对必要字段后即可列入待清理范围，不按天数或文件名猜测是否过期。
- 完成后：先核对正式日志、发布依据及中断恢复状态，再列明可清理文件和理由。备份须核验正式副本、归档成员或 Git blob 的内容哈希；不是只确认文件名存在。独有证据、未完成任务及摘要缓存不在临时清理范围。
- 获得对应删除授权后：只删除已验证的具体目标，记录原路径、哈希及恢复来源；区分可恢复副本和只能重新生成的输出。不能把整个 `work/` 或所有旧文件移到 `history/` 冒充清理。
- 有长期价值的部署／验收结论可整理到 `.private/history/<task-id>/`，只留精简记录；临时备份不永久保留。清理审计使用一个清单和结果记录，不为每个文件再建报告。未核实材料留在原处并说明原因，后续按来源核对，不视为已完成清理。
- 清理后验证正式证据、摘要缓存和网站快照未变，报告删除量、保留量、恢复方法及新增历史记录的体积。

历史迁移基准与验收仍可在 `.private/work/repository-reorg/` 查找；其中已验证重复备份的清理映射存于 `.private/history/work-cleanup-2026-10-05/`。后续 skill 引用本文，不复制另一套目录规范。
