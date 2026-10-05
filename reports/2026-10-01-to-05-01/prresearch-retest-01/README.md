# PRResearch 接收稿目录复测

## 本次结果（2026-10-05）

用户授权：再次测试，若仍失败，报告具体问题供用户测试。独立诊断，不改冻结候选、覆盖或原采集日志。

- 程序：限定最多 4 页、25 秒超时、无自动重试、429 停止。请求第 1 页时即发生 `SSL: UNEXPECTED_EOF_WHILE_READING`，没有取得目录页面。
- 普通内置浏览器：访问同一第 1 页，报 `net::ERR_CONNECTION_CLOSED`。没有登录、验证码处理或访问限制绕过。
- 本次不能重验分页内容；网络中断原因不确定，不能据此认定为 APS 全站故障或原分页重复已消失。

程序事件和结果见 `retest-log.jsonl` / `result.json`；普通浏览器失败另在日志追加记录。

## 此前确实读到的分页问题

此前 2026-10-05 成功取得的第二次目录遍历中，两页分别显示 1–20、21–40，第二页前三条与第一页重复，且均为 2026-10-02 接收。以下位置是每页内第几篇文章，不是网页元素编号：

| DOI | 标题 | 第1页位置 | 第2页位置 |
|---|---|---:|---:|
| 10.1103/xcls-6nzd | Space-time Floquet operator: Non-reciprocity and fractional topology of space-time crystals | 17 | 1 |
| 10.1103/sm6w-5ttl | Quantum eigenvalue transformations for arbitrary matrices | 8 | 2 |
| 10.1103/l3c8-3pbp | Edge currents shape condensates in chiral active matter | 9 | 3 |

原始证据：本轮 `collection-log.jsonl` 的序号 236（第一页）和 238（第二页）；对应键为 `official:PRResearch:accepted:1:1` / `official:PRResearch:accepted:1:2`。

这里的错误是“分页 DOI 不唯一”，不是“文章摘要缺失”。若简单去重，两页 40 个位置只有 37 个不同条目，仍不能证明原本应该出现在重复位置上的记录没有遗漏。因此不能把去重结果当成完整枚举。

同一天接收的记录排序不稳定是一种可能解释，但未证实服务端排序规则或根本原因。

## 用户可以怎样测试

1. 打开 [第1页](https://journals.aps.org/prresearch/accepted?page=1)，确认标题为 Physical Review Research — Accepted Papers，截图范围、日期以及上表对应文章。
2. 在第二个标签页打开 [第2页](https://journals.aps.org/prresearch/accepted?page=2)，确认显示 21–40，检查前三条是否与第一页重复。
3. 如果两页能正常打开且没有重复，保留两页截图；如可见旧于 2026-10-01 的日期，也记录所在页。请给出检查时间和显示范围，当前列表可能与此前快照不同。

不要提供 token、cookie 或登录信息；只需要页面可访问性和文章位置／日期。如果只有网页可访问而程序仍被拒绝，可以继续采用正常浏览器目录核对。
