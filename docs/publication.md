# 审核快照发布

## 输入与轮次

`config/release.json` 明确列出完成的 `reports/<run-id>/`。当前选择 `reports/2026-09` 和 `reports/2026-09-expansion-publication-01`，合并九月同一窗口。不自动扫描目录，不合并不同时间窗口。

每轮发布读取自己的冻结规则、原始候选、覆盖、采集日志和最新正式判断。必须无活跃任务、未审读或未决项；纳入者通过全部必要硬检查。完整性标志保留来源核对实际限制，不改写历史状态。

重复 DOI 只有候选、判断与公开记录一致才去重；冲突直接失败，须明确核查后追加修正，不能“最新记录优先”。作者、说明、材料与判断绑定继续逐篇验证。每轮仍是独立输入，多轮发布另保存轮次及各输入哈希。

### 裁决引用视图

四刊父轮仍保留其历史 131 个 `review`，不能直接发布。`release-view.json` 显式钉住父轮和裁决轮的原始文件、冻结规则及日志哈希。`scripts/publication_view.py` 验证裁决目标恰等于父轮未决集合、候选逐字一致、旧判断及旧输入哈希匹配、全部源判断绑定各自规则和候选；仅这些未决项被明确替代。已解决父判断不能覆盖，缺项、未决、来源变化或冲突直接失败。

视图沿用完整父目录的覆盖与计数，逐篇保留正式判断原哈希，不新增科学裁决。作者和发布审计单独存于视图目录的 `author-metadata.json`、`publication-log.jsonl`；历史源目录不写入。公开汇总保存完整引用 manifest，不能将子集覆盖计数当作整刊覆盖。

## 作者与阅读说明

```powershell
python scripts/collect_authors.py --run reports/2026-09-expansion-publication-01
```

仅补本轮纳入者的作者，优先 Crossref，必要时官方署名。核对 DOI、标题和 ISSN，拒绝占位姓名；保留来源、时间、记录及作者哈希。已存在作者文件时停止，不覆盖旧版本；更新须先保留原件并留痕。

`config/publication-notes.json` 按 DOI 保存短中英文说明、主题及正式判断哈希，DOI 集合须恰等于所选轮次纳入并集。输入或判断改变须实际回读，不仅换哈希。多主题允许，`other` 独占。区分明确摘要、官方摘要摘段与授权在线审读短评论，不夸大阅读范围。

## 导出与验证

```powershell
python scripts/publish_snapshot.py --out .private/work/release-preview
python scripts/publish_snapshot.py --check
python -m unittest discover -s tests -v
node --check site/app.js
node --test tests/test_app.cjs
```

默认输出为 `site/data`；首次合并先导出私有预览，检查后再更新正式文件。所有输入验证先于写入，无网络请求、无私有摘要读取，也不推进审读队列。`--check` 只读比对，忽略生成时间。界面变化须浏览器验收。

公开输出为 `papers.json`、`screening-report.json`、`status.json`，只含允许的书目、作者、短说明、来源、日期／类型依据与证据哈希。接收稿明确显示接收日和待发表状态，不计入已发表数。

Spotlight 由 `featured_journals` 单独控制，扩刊不会自动改变名单。首页展示最新六篇；读者详情优先统一出版方页面，取证和作者来源保留于数据与审核记录。

## 部署与边界

`site/` 是唯一部署目录，GitHub Pages 工作流只校验并上传已有网站文件，不采集、不补证、不启用日更。Git 推送与生产部署须有当前任务授权。CI 对全部报告轮次的变更触发校验；只有明确选入 release 的已完成轮次影响发布。

部署记录（提交、运行 ID、产物哈希、浏览器验收）保存在本地忽略目录。完整摘要、私有中转材料与开发历史不进入 Git 或部署。技术覆盖状态保留在审核数据；首页和 About 不重复内部历史问题。
