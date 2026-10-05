# 2026-09-expansion-01

本目录保存原始采集候选、覆盖和逐篇审核；当前发布由 `publication.json` 显式组合原始判断与正式复议。冻结输入不被当前全局规则重新解释。

- `candidates.json`、`coverage.json`：原始候选和来源覆盖。
- `inputs/`：当时配置、规程和哈希。
- `collection-log.jsonl` / `.gz`：来源枚举与失败记录。
- `screening-log.jsonl` / `.gz`：材料引用、判断和修订事件。
- `author-metadata.json`：纳入者的作者资料；来源完成事件由 `publication.json` 指定。
- `publication.json`：直接发布清单，不引用嵌套发布视图。

历史日志中的旧路径通过 [迁移索引](../../archive/legacy-2026-10-05/manifest.json) 定位。压缩日志解压后字节不变。更多说明见 [审核入口](../../README.md) 与 [文件规范](../../../docs/repository-layout.md)。
