# NetSci Observatory

[English](README.md) | 中文

一个公开、免注册的网络科学文献网站。集中浏览有关网络结构、网络上的动力学，以及可迁移网络科学理论与方法的研究，减少在不同期刊间逐一检索的负担。

**[浏览文献 →](https://netsciobs.com/)**

## 网站提供什么

- 在同一页面浏览十三本期刊中的相关文献。
- 按研究主题、期刊、日期或 Spotlight 期刊范围筛选，并搜索标题、作者、期刊和 DOI。
- 阅读简短的中英文说明，了解每篇文献与网络科学的联系。
- 通过链接访问原文，并区分已接收稿件和特殊文章类型。
- 在中英文界面之间切换，不改变论文标题、作者姓名或当前筛选条件。

网站首次访问默认英文，并记住用户选择的语言。

## 关注哪些研究

我们关注网络的形成与演化、网络结构的推断，以及相互作用如何影响传播、同步、集体行为、鲁棒性和控制。

具体系统中的研究也可以收录，条件是网络组织本身是主要研究问题，或文章提供可迁移到其他系统的网络科学理论与方法。仅使用网络指标开展常规领域分析，或缺乏明确网络科学贡献的一般非线性动力学研究，不在收录范围内。相关的综述、观点与科学评论也可收录。

## 收录期刊与 Spotlight

Spotlight 展示来自以下九本期刊的收录文献。首页显示最新六篇，点击 Spotlight 入口可以浏览该组的完整列表。分组仅表示展示位置，不是质量排名；所有文献采用相同的收录标准。

- Nature
- Science
- Nature Communications
- Nature Machine Intelligence
- Nature Computational Science
- Physical Review X
- Physical Review Letters
- Science Advances
- Proceedings of the National Academy of Sciences

完整列表还收录以下四本期刊中的相关文献：

- Communications Physics
- Physical Review Research
- Physical Review E
- Chaos: An Interdisciplinary Journal of Nonlinear Science

## 当前覆盖与局限

网站显示当前收录窗口与文献数量，最新审核快照请查看[在线列表](https://netsciobs.com/)。

日期筛选以页面注明的数据截止日为基准，而不是当天日期；选择“全部收录日期”可浏览完整列表。目前按完成审核的批次更新，尚未自动日更。发表日期优先采用首次在线发表日；已接收但尚未正式发表的稿件单独标注，并以接收日期显示。不收录预印本。

选文主要依据摘要和书目证据，使用 AI 辅助，并由维护者裁定范围疑难项。阅读说明用于帮助发现文献，不作质量评级，也不代表全文专家评审。列表不保证涵盖所有符合范围的文章。网站展示书目信息、简短阅读说明和原文链接，不转载完整摘要或正文。

详细说明见网站的[选文范围与局限](https://netsciobs.com/rules.html)。

## 反馈

发现遗漏、书目信息错误或需要修正的阅读说明？欢迎[提交 Issue](https://github.com/hjyu14/complex-network-papers/issues)，最好附上 DOI 或出版方链接，并简要说明问题。也欢迎提出网站改进建议。

## 开发与维护

网站由 GitHub Pages 托管，为静态页面，无需注册或额外运行依赖。在仓库根目录运行以下命令即可本地预览：

```sh
python -m http.server 8003 --directory site
```

随后打开 `http://localhost:8003/`。采集、选文与发布的详细工作流独立保存在：

- [采集与覆盖核对](docs/collection-workflow.md)
- [文献筛选规程](docs/screening-protocol.md)
- [证据要求与已知误区](docs/evidence-data-features.md)
- [发布与验证](docs/publication.md)
- [正式审核记录](reports/)与[维护约束](AGENTS.md)
