# v6 筛选验证记录

## 范围

2026-09-29 开始、2026-09-30 恢复，窗口固定为 2026-07-02—2026-09-29，现有 27 刊。这是筛选实现试验，不是完成了全部文章语义核查的正式发布。即使固定窗口，Crossref 的迟到补录和更正仍会使两次候选集合不同，不能把数量差异全部归因于规则。

## 变更

- 标题和摘要独立作为证据来源，删除标题必含网络线索及生物医学模型排除门槛。
- 保留四种证据路径：明确网络概念、网络方法、网络对象及机制、隐式关系及动力学。
- 未命中记录按缺失摘要、语境不明、无线索分组保留 review；不以无线索证明不相关。
- 逐条导出判定，摘要不落盘。证据词表不能代替人工或语义检查，也不能区分所有背景提及和实际贡献。
- 每刊 1000 条／页，安全上限 10 页。截断不再覆盖有效快照。不改变日期优先级、白名单、DOI 去重定义。
- 初次试采集的大响应在 Nature Communications 耗时较长，已中断且未写入有效试验快照；随后验证并启用 Crossref `select`，仅返回所有判定所需字段，省略参考文献等无用负载，重新运行。此项不改变科学范围。

## 已执行验证

- 恢复后 47 项 Python 测试通过，包括标题无 network、隐式关系动力学、常规中心性应用、分句证据、歧义稳定性不直接收录、待核查记录保留、截断保护。
- 9 项既有前端测试通过；本轮没有更改前端、在线规则页或发布快照。
- `python scripts/check_screening_examples.py` 从 Crossref 获取六篇实际论文，使用固定窗口，六例符合预期。证据输出在 `reports/v6-examples.json`，包括配置哈希，不保存摘要。

| DOI | 预期与结果 | 含义 |
| --- | --- | --- |
| 10.1126/science.aeg3946 | included | Disorder-promoted stability：摘要中的网络异质性和稳定性证据，不依赖标题命中。 |
| 10.1073/pnas.2620995123 | included | 鼠神经系统的网络结构及分析方法，不再特殊排除。 |
| 10.1103/9y9m-q7qj | included | Preferential attachment：网络形成概念，不要求 network 字面。 |
| 10.1126/science.adz5300 | review | 体内通信系统：networking 名称不足以判定，保留待核查；这不是已证实无关的负例。 |
| 10.1126/science.aef8268 | review | 高光谱成像的重建网络，仅有 topology/reconstruction 弱词不足以自动收录。 |
| 10.1126/science.aei8090 | review | 人工神经网络用于重建任务，缺少网络科学证据，保留核查。 |

这些案例是目的性选取的回归样本，不是随机评估集，不能据此声称总体准确率或召回率。

## 首轮发现与修正

首轮 `reports/v6-trial` 取得 10,835 条候选，自动收录 259 条、待核查 10,294 条、排除 282 条。没有分页截断，但这不是已确认的 259 篇网络科学文章。抽查发现上述成像和重建任务被 network 加 topology/reconstruction 等弱词误收。

第二轮“网络对象＋机制”路径要求额外的图证据或明确机制证据；只有泛结构／稳定性词的候选进入 review，而不是排除。保留首轮报告，第二轮独立写入 `reports/v6-revised`。Science 目标论文仍可通过摘要中的节点和异质性—稳定性证据；PNAS 目标论文通过 rich-club 方法证据。

第二轮获得 10,890 条候选：158 条自动通过、10,449 条待核查、283 条排除。对旧版 82 条逐项比较后发现 14 条转入 review，包括标题明确的 Robustness of small networks、网络流行病等。这表明额外证据限制应适用于摘要泛词，而不是压制明确标题。最终修正据此保留标题证据，结果写入 `reports/v6-final-trial`。第二轮与最终轮使用相同配置，但筛选代码不同，因此仅比较配置哈希不足以保证实现相同；各轮解释以本记录为准。

额外阅读两篇真实摘要（只在内存中）：

- `10.1103/lfwy-bbmv`：非互易相互作用的双物种 Vicsek 群集模型，研究集体状态及失稳；标题、摘要未使用 network，隐式相互作用动力学路径有实际依据。
- `10.1038/s42005-026-02750-0`：均场生成输运与群体协调，自动命中 interacting agents/diffusion，但是否属于站点的网络动力学范围仍需边界核查；不能以自动命中认定已验证。

## 复现

```sh
python -m unittest discover -s tests -v
node --test tests/test_app.cjs
python scripts/check_screening_examples.py
python scripts/collect.py --out reports/v6-trial --date 2026-09-29
python scripts/summarize_screening_trial.py
python scripts/collect.py --out reports/v6-revised --date 2026-09-29
python scripts/summarize_screening_trial.py --trial reports/v6-revised
python scripts/collect.py --out reports/v6-final-trial --date 2026-09-29
python scripts/summarize_screening_trial.py --trial reports/v6-final-trial
```

## 发布前仍需完成

### 最终试采集结果（2026-09-30）

`reports/v6-final-trial`：27 刊请求均成功，接口窗口记录无分页截断。10,892 条去重候选：181 条自动通过、10,428 条待核查、283 条排除（280 条通知类、3 条普通机器学习规则命中）。待核查含 4,904 条摘要缺失、3,656 条无线索、1,341 条语境不明、527 条日期不完整。

与线上 v5 的 82 条相比，原有条目全部仍在自动通过集合中，新增 99 条；新增既受覆盖扩大影响，也受规则和上游元数据变化影响，不应全部归功于新规则。《Disorder-promoted stability》和鼠神经系统 PNAS 均在最终集合；Science 自动通过 1 条，即前者。

配置哈希一致、DOI 唯一性、日期范围、摘要不落盘检查通过；47 项 Python 测试、9 项前端回归和 6 篇在线样例检查通过。没有改动 `site/` 和部署配置，没有提交、推送或发布。

**181 是自动规则输出，不是人工确认的准确论文数。** 自动通过中仍有均场生成输运等边界项，且 10,428 条待核查尚未完成语义检查；本轮已实现和验证候选分流，但没有完成“90 天全部论文逐条核实”的任务。当前实现仍是词表证据系统，不是自动全文语义审定。

### 剩余工作

- 检查试采集新增收录中的背景误命中，语义检查待核查记录；当前没有自动全文核查。
- 对照出版方目录检查 Crossref 未登记或日期缺失记录，尤其返回零条的期刊。
- 已按用户要求将最终试验快照复制至 `site/data`，前端门槛同步 v6，公开中英规则文章已更新，用户已授权发布；部署状态以 GitHub Actions 为准。原始试采集目录在本地保留不改，发布基线与审计报告在 `site/data` 追溯，自动通过不等同于人工语义确认。
- 每日增量、迟到补录和周期性全窗口对账尚未实现；本次试验仍全窗口采集。
