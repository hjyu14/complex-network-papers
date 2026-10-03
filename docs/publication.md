# 审核快照发布

- 来源：`reports/2026-09/screening-log.jsonl`的最新纳入判断；原始候选、覆盖、采集日志不改。当前为17篇，其中15篇已发表、2篇已接收；380篇补证暂不处理。
- 阅读说明与主题：`config/publication-notes.json`逐DOI保存中英文短说明、主题和对应判断哈希；输入或判断变化时旧说明会被导出器拒绝，须重新实际核查。主题不是纳入条件，允许多标签，other独占。
- 导出：`python scripts/publish_snapshot.py`。所有输入检查先于写入，缺少说明、未决硬检查、原始文件变化或判断哈希失配直接失败。无网络请求、无私有摘要读取，也不推进审读队列。
- 核验：`python scripts/publish_snapshot.py --check`只读比对公开快照与日志／规则／说明；另运行32项Python测试、18项前端测试与JS语法检查，进行实际浏览器验收。
- 公开内容：site/data中的papers.json、screening-report.json、status.json；只含允许的元数据、简短说明、日期／类型依据、判断与材料哈希和来源链接。不得加入完整摘要、正文、PDF、私有目录、凭据。作者补充保存在reports/2026-09/author-metadata.json：15篇Crossref名单、2篇APS官方接收稿署名，均已核验记录身份；保留旧版本、来源、时间与哈希，不保存完整响应。导出器校验DOI集合、候选记录哈希、作者数据哈希及正式留痕，拒绝占位姓名。
- Spotlight：用户确认九刊全部列入；总数17与纳入数一致，首页仅展示最新六篇。该展示调整不改变科学判断。
- 日期：固定2026-09-01至09-30。展示接收稿时明确接收日期、待发表状态，published_date保持空值。筛选相对于快照截止日；尚未宣称最近90天或自动日更。
- 覆盖：Nature Communications目录分页未通过稳定性验证；网站如实披露，不能将快照导出成功改写为出版社覆盖完整。
- 部署：codex/new-workflow的`.github/workflows/publish-reviewed.yml`校验已有快照，只上传site目录到GitHub Pages。无schedule、无自动采集／补证、无自动改写结果。旧Update literature and deploy工作流停用，避免旧main数据覆盖。
- 留痕：正式审读日志记录发布准备事件及来源日志头，公开快照绑定该日志头。部署运行ID、提交、产物哈希和验收结果追加到本地忽略目录的最小部署记录；部署本身不改变17篇科学判断。
