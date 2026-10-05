# 现行规则回溯校准（2026-10-05）

## 结论与边界

本轮完成固定的 114 篇样本核对：112 篇实际回读身份匹配、哈希核验的已有完整摘要；2 篇没有可用缓存摘要，不声称完成 AI 摘要复核，保留用户亲自复核后的原排除。

| 校准意见 | 数量 | 含义 |
|---|---:|---|
| `maintain` | 103 | 97 篇维持排除，6 篇维持纳入对照 |
| `discuss` | 9 | 保留原排除，提请用户复议，不是正式纳入 |
| `unassessed_no_material` | 2 | 无摘要再审证据，保留历史用户裁决 |

本轮不修改科学规则、历史裁决、发布配置或网站，不新增正式收录。判断基于已有摘要，不是新在线取证或全文专家审查；可能纳入的论文仍须在正式新审核轮完成必要身份、日期与类型检查，不能用本校准意见代替发布判断。

## 样本与可追溯性

当前发布输入三个轮次共有 3,768 篇正式判断，其中 3,622 篇排除、146 篇纳入。此数字是库存，不是本轮逐篇复核数量。

本轮样本各组互不重复：

- 九月四刊原 131 篇疑难裁决中全部 53 篇排除项。
- 根据题名或旧理由人工定向选择 29 篇其他排除项；选样线索不作为语义判断。
- 十三刊各 2 篇排除样本，共 26 篇。按 `sha256("calibration-2026-10-05|" + DOI)` 排序选取尚未入样且有缓存材料的项，便于复现，不称为统计随机抽样。
- 6 篇已纳入对照，检查实证网络组织与领域附带网络分析的边界是否一致。

这不是全部 3,622 篇排除项重审，也不是新整刊发现或召回率估计。不能据此声称没有遗漏。标题、哈希、关键词、摘要长度及渠道成功均不能替代实际审读。

正式产物仅三份：本说明、`manifest.json` 和 `review-log.jsonl`。前者固定样本、现行规程哈希与受保护文件哈希；后者逐篇保存校准理由、原判断哈希、候选哈希及精确材料版本哈希。完整摘要继续仅留在 Git 忽略的私有摘要缓存，不复制进此目录。

## 建议优先讨论的三篇

1. **[A structure–function neuronal network model of the rat nervous system](https://doi.org/10.1073/pnas.2620995123)** — PNAS，历史日期 2026-09-08。
   主要问题就是神经系统的加权有向连接组织，涉及层级模块、rich club、整合及局部扰动传播。与网络指标服务于另一个疾病问题不同，现行规则不要求实证组织研究提出新算法。原排除为用户固定边界裁决，建议编辑复议，不称为助手漏抓。

2. **[Global warming drives connectivity loss among climate tipping elements](https://doi.org/10.1103/mnvf-tq6g)** — Physical Review Research，历史日期 2026-09-28。
   主要结果是临界要素连接随强迫变化及失相干，贝叶斯连接分析明确处理观察和抽样不确定性；不是只用中心性诊断特定气候量。限制：相关连接不等于因果影响。原为用户 G 组编辑排除。

3. **[Gate control improves routing efficiency for periodic traffic](https://doi.org/10.1103/m6s5-r1cq)** — Physical Review E，历史记录为 2026-09-30 已接收。
   路由中的局域双队列门控改变拥堵跃迁性质，摘要明确提出交通网络及互联网包路由的迁移场景，有网络动力学方法主线。原为用户 G 组编辑排除；本轮未补核之后的正式发表状态。

## 六篇次优边界复议

| 论文 | 复议理由 | 保留的限制／旧判断性质 |
|---|---|---|
| [Functional brain networks underlying approach–avoidance conflict processing in humans and rats](https://doi.org/10.1073/pnas.2601203123)（PNAS） | 跨物种枢纽、跨社区整合和拓扑差异是主要问题与结果，不能仅因成熟指标排除 | 任务特定功能相关网；摘要不证明因果动力学。旧代理理由可能对实证网络组织要求过严 |
| [Metabolite correlation networks reveal complex phenotypes of adaptation-driving mutations](https://doi.org/10.1038/s41467-026-77850-0)（Nature Communications） | 网络协方差组织作为系统表型，主要结果是外围节点变成簇间连接者及系统重组 | 单一细菌适应系统；相关边不等于因果反应连接。原用户固定边界裁决 |
| [Inferring three-body interactions in cell migration dynamics](https://doi.org/10.1103/xsg5-cb6l)（Physical Review Research） | 从轨迹同时识别成对和三体相互作用，有高阶相互作用推断的方法价值 | 不证明普适超图重构，三体修正有限；是否达到可迁移门槛待讨论。原 G 组编辑取舍 |
| [Mass media interventions and social reinforcements drive rumor propagation](https://doi.org/10.1103/vxkg-41kp)（Physical Review E） | 多层耦合传播、强化、干预与阈值是主问题 | 摘要未充分说明具体接触网络拓扑，拟合不证明干预因果；历史已接收状态未新核验。原 G 组编辑取舍 |
| [Branch-and-bound tensor networks for exact characterization of classical ground states](https://doi.org/10.1103/g76v-wxz7)（Physical Review Research） | 新精确方法求解图最大独立集，值得与已收录图优化方法对齐边界 | 通用张量求解器未必是网络专用方法；性能是作者报告，未复现。旧代理方法边界判断 |
| [Liquid and solid layers in a thermal deep-learning machine](https://doi.org/10.1103/twww-yj1y)（Physical Review E） | 研究深层网络本身的分层动力学、时间尺度分离及老化，不是用神经网络预测另一系统 | 学习理论与网络科学的编辑边界；不推广为所有神经网络论文纳入。原 D 组取舍 |

以上按讨论优先级分组，不代表新增分类规则，也不是九篇确定误排。此前用户明确的单篇取舍可以复议，但不能被改写成自动筛选错误。

## 本轮经验

- 实证网络组织不要求新算法；应具体问主要结果是否解释连接组织，而非仅检查用了什么指标。
- 单篇或组内编辑取舍不是领域黑名单；脑网络、气候网络、量子系统、神经网络或生物应用都需按具体贡献判断。
- “有趣”“用了 graph/network”“对网络研究者有用”不单独构成收录理由。
- 尚不能把多层人口传播直接认成接触网络，也不能把三体作用识别直接认成通用超图重构；保留证据限制。
- 已纳入对照支持接触簇组织、空间防御网络和通用 Markov 边流设计等主贡献，但不自动豁免其他领域应用。

## 验证

使用本地私有审计辅助程序检查样本逐篇记录齐备、原判断及材料绑定一致、旧 reports/site/config/docs 文件哈希未变、完整摘要未进入正式产物。另执行 `python scripts/publish_snapshot.py --check` 检查网站与既有发布输入一致。具体执行结果见本次交付说明；仅本目录为新正式产物，未提交、未推送。
