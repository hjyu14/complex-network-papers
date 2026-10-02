"""Serialize explicit AI editorial assessments of the fixed v6 cohort.

Not an automatic classifier. Indices are valid only for the SHA256-bound
181-paper baseline. Evidence is title/abstract level, never full-text review.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_HASH = 'deb4a2d9fb26c31a6e86f06948470bc49fe149113efb23a718a1818379afbfbe'

# Each group was inspected title by title. No complement/default inclusion.
CORE = [
    0,1,3,4,5,8,10,11,15,17,18,19,24,25,27,28,32,33,36,37,38,
    40,41,42,43,45,47,51,53,55,56,57,59,60,63,67,68,69,70,72,73,
    75,76,78,80,81,82,85,89,90,95,97,98,99,100,102,103,104,106,
    109,110,111,112,113,114,116,117,119,120,121,123,124,125,126,127,
    128,129,130,131,132,133,134,135,137,139,140,142,143,145,151,152,
    153,154,156,157,159,160,162,164,166,167,168,169,170,173,174,
    176,177,178,180,
]

APPLICATION = {
    13: '从感染网络提出热核节点曲率指标，比较其他曲率定义；可迁移内容是动态网络结构变化的度量，而非疾病分型。',
    30: '从三细胞轨迹发展二体与三体作用推断方案；可迁移内容是从轨迹数据识别高阶相互作用。仅三个细胞的证据范围有限。',
    31: '从实测脑网络提出远程同步检测方法；摘要明确扩展到振子网络并给出理论解释，而非仅报告具体脑区功能。',
    35: '提出最大熵基准及假设检验，将多元时间序列映射为带符号网络；脑网络只是演示对象，推断框架可用于其他系统。',
    62: '金融资产背景下提出耦合映射与拉普拉斯零空间模型，因子维数对应同步模态；可迁移内容是耦合矩阵与降维机制。',
    138: '条件互信息、共同市场效应剔除与置换显著性检验构建依赖网络；四市场比较。暂收第二类，但一般推断性能仍需独立核验。',
    148: '基因共享二部网络背景下构建生成模型，解析推导两侧度分布并用模拟验证；可迁移内容是二部网络生成机制。',
}

REVIEW = {
    6: '出版方摘要研究认知任务驱动人工 RNN 模块化并与脑结构比较；不能仅由模块化词放行。需核实主要贡献是否为可迁移网络形成机制。',
    21: '标题涉及有限亲和力稳态电流的网络分析，但 Crossref 无摘要；需核实是否是一般状态转移图方法及其网络科学意义。',
    61: '新忆阻突触、脉冲传输和信息编码是主体，另有环网络同步分析；摘要不足以确定网络动力学贡献是否构成主要结果。',
    86: '摘要包含拓扑族、连通度相变与修改的 Dijkstra 路由，但核心目标是 QKD 安全—密钥率；可迁移到一般网络的方法意义需核实。',
    115: 'ROOT 从逻辑网络识别不可逆转变反馈回路并给出控制策略，但证据验证集中于细胞过程；需核实一般网络控制适用范围。',
    141: '土壤重金属预警应用，Crossref 无摘要；标题不足以证明可迁移网络方法，暂不进入两类收录。',
}

EXCLUDED_GROUPS = {
    '用户明确排除的领域网络文章；这是本站选文边界，不是否认其学术价值或网络科学关联。': [2,9,14,16,23,34,49,50,54,64],
    '主要结果是具体生物、医学或认知系统的机制、功能或干预；现有证据不支持可迁移网络方法为主要贡献。': [7,22,44,52,65,83,91,96,105,108,122,149,150,155,158,161,163,171,172,175,179],
    '网络分析用于领域数据描述或决策；没有明确的可迁移网络方法或一般网络机制贡献。': [20,29,58,77,84,87,88,107,144],
    '材料、分子、器件或模型任务为主体；network、拓扑或图表示本身不足以满足新边界。': [12,26,48,66,74,79,92,93,94,118,147,165],
    '主要是一般非线性动力学、主动粒子或随机控制问题；未体现网络结构或网络上动力学作为主要研究问题。': [39,46,71,146],
    '复杂网络仅出现在背景；实际摘要为感觉神经功能与感染实验，不能据背景放行。': [136],
    '网络方法被用于具体疾病药物候选识别；没有一般网络方法贡献的充分证据。': [101],
}

ABSTRACT_REVIEWED = {
    7,13,18,24,28,29,30,31,35,38,39,46,55,58,61,62,70,71,77,78,
    82,84,86,87,94,95,102,104,105,107,111,115,117,119,120,124,128,
    132,135,138,144,146,148,149,156,157,171,175,178,
}
NOTES = {
    11: '标题直接研究耦合 β 细胞网络中的行进奇美拉与集体协调；按网络模型动力学收录，未核实期刊版本摘要。',
    18: '空间排列与共同平台耦合的对称性决定同步模式；实验及模型研究耦合振子集体动力学。',
    24: '主要结论是一般网络中节点异质性与非厄米结构如何提升稳定性；生物、材料和电网仅为适用例子。',
    28: '提出一般超图聚类演化算子；医学数据只是示例，不构成生物医学应用排除。',
    38: '在任意度分布的稠密随机网络上推导催化动力学精确均场解；主要贡献是拓扑—动力学理论。',
    55: '建立连续介质谱与离散耦合矩阵的主稳定函数对应；一般网络同步稳定性理论。',
    78: '综述单纯复形、超图和关系算子的结构诊断；跨领域例子不改变网络表示与方法主题。',
    95: '定义基于电阻距离的节点扩散指数，比较人工图族及实测网络；一般网络动态度量。',
    102: '解析降维理论联系连接复杂度、延迟与振荡阈值；电子电路验证，领域例子不是主要对象。',
    104: '研究方向性、稀疏性及嵌入结构如何影响有向环的信息处理；一般网络模体机制。',
    109: '标题直接提出从级联失效进行相依基础设施网络重构的 Bayesian 方法；按一般重构方法暂收第一类，未声称跨领域性能已验证。',
    111: '定义非均匀超图上的同配指标并建立约束；一般高阶网络结构方法。',
    117: '推导一般线性及 Kuramoto 网络的入侵节点失稳机制；不是某一行业安全案例。',
    119: '提出从不规则到达时序构造网络并识别社区的通用框架；标准随机过程与不同数据作演示。',
    120: '将样本熵拓展为拓扑感知图信号指标；交通流只是验证案例。',
    124: '研究星形及更复杂振子网络中的远程信号传播并解释机制；脑功能仅为动机。',
    128: '证明一类相互作用网络的结构收缩、非扩张与周期输入响应；细胞通路是例子。',
    132: '研究成对连接如何产生冗余与协同信息，含数值和电子振子网络；神经记录是补充验证。',
    135: '提出从多元时序关系构造滤波单纯复形的持续同调方法，并研究布尔网络临界性。',
    156: '提出给定调控拓扑的组合—数值全局平衡与分岔分析算法；一般网络动力学方法。',
    157: '实验研究空间分离自振单元的频率锁定、耦合距离与群体同步；属于耦合动力学。',
    177: '出版方摘要证明一类催化反应网络局部可稳定性蕴含化学计量相容类内全局可控性；一般定理，非具体生物机制案例。',
    178: '提出可解析空间活动驱动时间网络模型，分析结构与传播；社交距离是演示。',
}

PUBLISHER_EVIDENCE = {
    6: 'https://www.nature.com/articles/s42256-026-01306-9',
    161: 'https://www.nature.com/articles/s41467-026-75843-7',
    177: 'https://www.nature.com/articles/s42005-026-02727-z',
}


def main():
    raw = (ROOT / 'site/data/baseline-v6.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASELINE_HASH:
        raise ValueError('Baseline differs from reviewed cohort')
    baseline = json.loads(raw)
    out = ROOT / 'reports/v8-trial'
    # Preserve the rejected heuristic result; never represent it as semantic review.
    prototype = out / 'automated-initial-report.json'
    if not prototype.exists():
        initial = json.loads((out / 'classification-report.json').read_text(encoding='utf-8'))
        initial['assessment_status'] = 'rejected_keyword_prototype_not_final'
        prototype.write_text(json.dumps(initial, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    initial = json.loads(prototype.read_text(encoding='utf-8'))
    evidence = {x['doi']: x for x in initial['decisions']}
    decisions_by_index = {}
    def add(indices, category, reason):
        for i in indices:
            if i in decisions_by_index:
                raise ValueError('Duplicate assessment index')
            decisions_by_index[i] = (category, reason)
    add(CORE, 'core', '标题明确研究网络结构、网络生成、网络方法或网络上动力学；具体领域仅为模型背景或验证案例。')
    for i, reason in APPLICATION.items():
        add([i], 'transferable_application', reason)
    for i, reason in REVIEW.items():
        add([i], 'review', reason)
    for reason, indices in EXCLUDED_GROUPS.items():
        add(indices, 'excluded', reason)
    if set(decisions_by_index) != set(range(len(baseline['papers']))):
        raise ValueError('Missing or extra assessments')
    prior_path = ROOT / 'reports/baseline-review-2026-09-30.json'
    rows = []
    for i, paper in enumerate(baseline['papers']):
        category, reason = decisions_by_index[i]
        old = evidence[paper['doi']]
        level = ('publisher_abstract' if i in PUBLISHER_EVIDENCE else
                 'crossref_abstract' if i in ABSTRACT_REVIEWED else 'title')
        rows.append({
            'baseline_index': i, 'doi': paper['doi'], 'title': paper['title'],
            'date': paper['date'], 'journal': paper['journal'],
            'v8_category': category, 'reason': NOTES.get(i, reason),
            'evidence_level': level, 'abstract_available': old['abstract_available'],
            'metadata_sha256': old['metadata_sha256'], 'metadata_url': old['metadata_url'],
            'publisher_evidence_url': PUBLISHER_EVIDENCE.get(i),
            'prior_review_reference': str(prior_path.relative_to(ROOT)).replace('\\', '/'),
            'decision_author': 'AI assistant; user-confirmed scope; not expert certification',
        })
    counts = dict(Counter(x['v8_category'] for x in rows))
    report = {
        'trial': 'v8_scope_editorial_review', 'assessment_method': 'explicit_title_and_abstract_review',
        'source_snapshot_sha256': BASELINE_HASH, 'input_count': len(rows), 'counts': counts,
        'window_start': baseline['window_start'], 'window_end': baseline['window_end'],
        'positive_categories': ['core', 'transferable_application'],
        'limitations': ['No full texts read.', 'Title-only assessments are provisional.',
                       'No general v8 automatic classifier implemented.',
                       'Rejected keyword run is preserved separately; latest repeat failed SSL and did not replace evidence.',
                       'No new papers; public snapshot and production rules unchanged.'],
        'decisions': rows,
    }
    (out / 'classification-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out / 'summary.json').write_text(json.dumps({k: v for k,v in report.items() if k!='decisions'}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    labels = {'core': '第一类：核心复杂网络科学', 'transferable_application': '第二类：具有可迁移网络贡献的应用研究', 'excluded': '不收录', 'review': '待核查，暂不收录'}
    lines = ['# v8 固定池试筛结果', '', '输入：原有 181 篇，2026-07-02 至 2026-09-29。未修改线上名单。', '',
             '这是 AI 对标题与选定摘要的显式审读，不是自动分类器输出，也不是全文专家审定。', '',
             '第一类包括一般网络理论/方法及以合成网络、耦合振子为对象的研究；第二类要求领域起点之外明确的可迁移贡献。生物、脑科学背景不作为自动排除词。', '',
             '摘要仅在内存处理。对 181 个 DOI 完成元数据读取，49 篇边界摘要在本轮语义阅读，另补充 3 篇出版方摘要；其余以标题或先前复核为依据。标题层面判断仍可能需要复核。', '',
             '用户所列 10 篇均移出本次建议名单。没有要求第二类满足固定数量配额。', '',
             '| 判定 | 篇数 |', '| --- | ---: |']
    for cat,label in labels.items():
        lines.append(f'| {label} | {counts[cat]} |')
    for cat,label in labels.items():
        lines += ['', f'## {label}', '', '| 序号 | 文章 | 期刊 | 证据层级 | 判定依据 |', '| ---: | --- | --- | --- | --- |']
        for n,x in enumerate((r for r in rows if r['v8_category']==cat),1):
            title=x['title'].replace('|','\\|')
            lines.append(f"| {n} | [{title}](https://doi.org/{x['doi']}) | {x['journal']} | {x['evidence_level']} | {x['reason']} |")
    (out / 'review.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'input':len(rows),'counts':counts},ensure_ascii=False))


if __name__ == '__main__':
    main()
