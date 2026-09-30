# NetSci Observatory · 复杂网络文献观察

无需登录的复杂网络文献看板。聚焦网络结构与网络上的动力学，提供白名单期刊近 90 天论文的元数据与 DOI 原文链接；不独立收录一般非线性动力学，不存储全文，不使用数据库。

正式访问：[文献网站](https://hjyu14.github.io/complex-network-papers/) · [收录规则文章](https://hjyu14.github.io/complex-network-papers/rules.html)。首次访问默认英文，可切换中文并记住选择；不翻译论文标题或作者，不重置筛选条件。

## 当前发布与规则

规则 v8：网络结构、网络动力学或可迁移网络科学方法须为主要贡献。原有 181 篇固定池保留 117 篇（110 核心网络科学、7 可迁移应用研究），58 篇范围外、6 篇待核查。依据为用户确认的 AI 标题／选定摘要审读登记表 `config/scope-review-v8.json`，不是全文专家审定或通用自动语义分类器。主题仍为五组可重叠标签；不分配研究方法标签，不提供方法筛选。

窗口固定为 2026-07-02 至 2026-09-29；原始基线 `site/data/baseline-v6.json` 保持字节不变。定时刷新仅处理原有 181 个 DOI。未审读或标题变化进入待核查，不自动增加文献。27 刊 ISSN 白名单、五刊重点区、日期优先级、元数据来源和失败保留策略不变。

## 运行与验证

Python 3.11+，无第三方运行依赖。摘要仅在内存处理，不存储 PDF 或完整摘要。

```sh
python -m unittest discover -s tests -v
node --check site/app.js
node --test tests/test_app.cjs
python scripts/rescreen_existing.py --out reports/v8-release
python -m http.server 8000 --directory site
```

浏览 http://localhost:8000 。页面不能通过 file:// 读取 JSON。试验目录通过 `--promote-from` 验证后才发布到 `site/data`。不完整刷新不得替换有效快照。

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

GitHub Pages 使用 Actions 部署 `site/`。工作流允许手动运行，每天 UTC 22:20（北京时间次日 06:20）只刷新原有 181 个 DOI 的元数据和筛选，也在 main 推送后部署（不采集）。定时运行可能延迟。重新扩展期刊采集或启动日推需另行授权。

固定名单试验：`python scripts/rescreen_existing.py --source site/data/baseline-v6.json --out reports/v8-release`。完整试验可用同一脚本的 `--promote-from reports/v8-release --out site/data` 校验并发布到本地站点目录，再测试与提交。实验摘要仅存在内存，不写文件。

采集请求部分失败时不替换上次有效论文快照，但保存失败状态并部署警告；最后将工作流标记失败。预算截断与请求失败分别报告。首次失败或历史快照不兼容当前规则时显示不可用，不生成示例论文，也不把旧规则结果冒充新结果。成功但零条匹配时如实展示空结果。站点只发布 site/，自动运行不请求付费服务。

每次成功生成的数据和尝试状态提交回仓库，便于追溯。规则变化必须显式更新配置版本与测试。密钥不得提交；当前采集无需 API key。
