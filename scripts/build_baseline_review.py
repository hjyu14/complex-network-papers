"""Serialize the assistant's recorded 2026-09-30 evidence review, not a classifier.

Indices refer only to the immutable f521ae3 baseline. No abstracts are stored.
No decisions are applied to the collector or public feed.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Individually read title/abstract assessments. Wording below is paraphrase.
NOTES = {
    2: '跨物种功能网络分析，比较枢纽中心性、社区整合及拓扑差异。',
    9: '实际用脑网络拓扑进行疾病阶段分组，而非只在背景提及网络。',
    16: '实际进行基因调控网络分析以识别分化调控因子，符合方法应用口径。',
    18: '共同平台介导振子耦合，空间排列与耦合对称性决定同步模式。',
    20: '摘要以同位素推断饮食组成，食物网与级联主要出现在意义说明；需核实是否重建和分析营养关系结构，不能仅因是生态应用排除。',
    22: '研究宿主—寄生蜂间毒素转移及适应；网络级联在背景出现，需核实实际关系结构或集体动力学分析。',
    24: '研究节点异质性、非互易作用和高维节点动力学如何改变网络稳定性。',
    30: '由细胞轨迹推断二体与三体相互作用并比较动力学，属于隐式高阶关系推断。',
    39: '研究均场相互作用下群体引导与协同输运；具有真实耦合，但网络结构/方法定位仍属边界，需查具体相互作用模型。',
    44: '长程抑制性投射介导多脑区同步，直接研究连接方式对集体动力学的影响。',
    46: '两物种 Vicsek 模型中非互易相互作用驱动集体旋转、失稳与时空混沌。',
    49: '924 节点有向加权网络；分析模块、富人俱乐部、小世界结构和局部扰动传播。',
    50: '动态因果建模与动态功能连接用于识别并比较脑区定向路径及网络重组。',
    52: '静电相互作用的复杂网络表述出现在凝聚机制描述中；摘要未说明图构建或网络分析，需核实计算方法。',
    54: '生成脑连接网络，比较通信、计算可靠性及枢纽攻击下的鲁棒性。',
    61: '明确研究环耦合脉冲神经元网络中的同步和奇美拉态，不是仅用神经网络预测。',
    62: '以耦合矩阵和拉普拉斯构建资产网络，研究同步模式与因子维数。',
    65: '加权基因共表达网络分析识别模块及上游调控因子，属于实际方法应用。',
    66: '以 VAE 潜空间替代传统序列相似性网络；高阶作用主要在既有方法局限中出现，需确认网络比较是实际分析还是背景。',
    70: '给定有向图的节点相位博弈，比较图结构对稳定相位分配的影响。',
    71: '主体为超混沌驱动—响应同步控制，多节点网络主要作为应用动机；需核实是否研究网络耦合而非一般同步通信。',
    78: '综述超图、单纯复形和关系算子如何表征多尺度、高阶结构。',
    79: '由反应物图通过等变扩散模型生成三维过渡态；需区分一般图输入机器学习与真正网络方法研究，现有摘要不足以裁决边界。',
    82: '在 ER 网络上比较渗流连通性、级联输入输出与信息流。',
    84: '构建医院共享患者网络、模拟传播并优化哨点选取。',
    86: '比较拓扑、路由和连接度对端到端安全与密钥率的影响，使用修改的 Dijkstra 方法。',
    87: '空间网络分析及电路理论识别非法贸易路径，属于网络方法应用。',
    88: '比较食物选择与能量转移路径的历史变化；需核实是否量化关系结构，不能把食物网一词当充分证据。',
    91: '动态网络分析识别蛋白残基间的长程变构通信路径，并有实验验证。',
    92: '摘要描述微凝胶界面弹性、聚合物缠结及射流稳定性，未给出图意义或网络科学分析；按当前摘要建议不收录，未读全文。',
    93: '光子神经计算硬件实现四种拓扑并比较推理性能；需确定拓扑研究是否超出一般神经网络硬件实现。',
    94: '多尺度材料关系拓扑特征用于预测；有潜在网络方法证据，但需核实具体拓扑量与关系表示，不能按材料领域直接排除。',
    95: '用电阻距离定义节点扩散指数，在人工与真实网络上比较瓶颈和节点角色。',
    96: '实际以共表达网络和功能模块分析棉花驯化中的调控变化。',
    101: '构建分子近邻网络，用社区、空模型、最小生成树和介数识别药物候选。',
    105: '混合正负反馈网络模体的结构与随机动力学对应关系。',
    107: '构建营养网络，分析模块度、嵌套性和鲁棒性与生态稳定性的关系。',
    108: '实际用网络分析关联 RSK1 与疾病基因模块；方法贡献较小也符合范围。',
    115: '从逻辑网络中识别不可逆转变的反馈回路并设计控制策略。',
    117: '研究攻击节点的连接位置如何影响整个网络的共识和同步稳定性。',
    118: '分子动力学揭示受限水的氢键排列及扩散；需核实是否实际分析氢键图或拓扑，而非材料结构描述。',
    122: '通过代谢依赖网络重建酶折叠出现顺序，明确网络分析应用。',
    124: '比较星形及更复杂拓扑中的远程信号传播，并分析机制。',
    135: '由多元时间序列构造单纯复形，用持续同调研究布尔网络耦合与临界性。',
    136: '摘要主体是去神经支配实验、感觉功能和感染反应；复杂网络仅为开头背景，未支持结构或耦合动力学分析，建议不收录但未读全文。',
    138: '以条件互信息构建金融最小生成树，比较中心性、路径和核心—边缘结构。',
    146: '一般非平衡热力学框架，耦合振子仅列为应用之一；需查应用部分是否实质研究相互作用组织与集体动力学。',
    148: '二部基因共享网络生成模型，推导度分布并与真实数据比较。',
    149: '学习模型明确覆盖复杂网络结构及高阶结构性质，属于关系结构学习研究。',
    150: '明确利用网络拓扑改进蛋白功能注释，符合网络方法应用口径。',
    151: '保持度与强度序列的二部加权网络随机化算法及空模型验证。',
    154: '比较硬件图拓扑、连通性和受挫相互作用对自旋玻璃弛豫的影响。',
    155: '实际报告功能连接、脑社区结构与模块度的变化，不因生物医学应用排除。',
    156: '从调控网络拓扑进行组合与数值动力学分析，研究平衡及分岔。',
    157: '直接识别自振单元间长程耦合与同步距离，符合隐式相互作用动力学。',
    158: '跨物种共表达网络分析并推断调控网络，是明确方法应用。',
    163: '实际进行通路层面的网络推断，分析线粒体、翻译和突触程序间的耦合。',
    165: '非互易耦合双量子比特实现纠缠稳定；属于耦合动力学候选，但需明确与一般量子器件协议的范围边界。',
    168: '以 Vicsek 交互网络的连通子图研究度、路径、聚类系数及跨尺度拓扑。',
    172: '实际用基因调控网络分析识别细胞命运调控与药物扰动。',
    175: '以实测连接约束皮层网络模型，比较节点异质性对同步及信息流的作用。',
    178: '构建空间活动驱动时间网络，解析联系结构并模拟传播。',
    179: '研究跨区域神经—胶质信号传递；需确认存在网络结构或耦合集体行为分析，而不仅是分子信号机制。',
}

MISSING = {
    6: '标题直接研究人工网络模块化与脑架构对应，标题足以支持范围内判定；当前 Crossref 无摘要。',
    12: '材料网络拓扑存在歧义，Crossref 重试后仍无摘要，需出版方证据。',
    26: 'GAN 稳定训练不自动等于网络动力学；现有标题和无摘要状态不足以支持收录。',
    48: '量子网络相位稳定可能是链路硬件问题；无摘要，需核实是否有网络级分析。',
    74: '氢键碳点材料网络及器件稳定性，缺少图意义证据且无摘要，需核查。',
    142: '标题直接研究网络韧性的攻防博弈；范围内，Crossref 无摘要。',
    147: '跨图 RNA 设计涉及图方法但无摘要，需判别具体方法与研究对象。',
    177: '标题直接研究反应网络的可稳定性和可控性；范围内，Crossref 无摘要。',
}

PENDING = {12,20,22,26,39,48,52,66,71,74,79,88,93,94,118,146,147,165,179}
EXCLUDE_RECOMMENDATIONS = {92,136}

# Explicit title-by-title assessment groups; not regex screening or default inclusion.
TITLE_GROUPS = {
    '标题明确研究网络/图/高阶关系的结构、生成或结构指标。': [10,17,35,45,58,60,76,99,111,113,129,130,134,144,152,160,167,174],
    '标题明确研究网络、超图或耦合单元上的传播、同步、博弈或其他动力学。': [0,1,3,4,8,11,14,15,19,25,27,31,32,33,36,37,38,40,41,42,43,47,51,53,55,56,57,59,63,67,68,69,72,73,75,80,81,85,89,90,97,98,100,102,103,104,106,109,110,114,116,121,123,125,126,127,128,131,132,133,137,139,140,143,145,153,159,161,162,164,166,169,170,171,173,176,180],
    '标题明确提出或应用网络分析、推断、图方法或网络控制。': [5,7,13,21,23,28,29,34,64,77,83,112,119,120,141],
}

SPECIAL_EXCLUDED = {
    '10.1038/s41467-026-77930-1': ('retain_exclusion', '图像分割分辨率与模型性能研究；摘要未研究关系结构、网络方法或耦合集体动力学。'),
    '10.1038/s41467-026-76677-z': ('retain_exclusion', '语音识别与大模型管线的可用性及误差评估；摘要未显示网络科学研究。'),
    '10.1038/s41467-026-75881-1': ('recommend_reconsider_inclusion', '摘要明确学习自适应图结构并动态稀疏化、识别跨变量关系；按已同意的网络推断应用口径，不能因异常检测应用直接排除。'),
    '10.1126/sciadv.aec0494': ('retain_exclusion_correct_reason', '这是编辑和同行评审过程的实证研究，不是社论；摘要分析投稿评价及选择效应，没有明确网络方法。需纠正词首 Editorial 误分类。'),
    '10.1103/9n96-whkp': ('retain_exclusion_correct_reason', '自身 DOI 的 correction 关联不足以判为通知；摘要研究聚合物链缠结和扩散，未见图意义或网络方法，按内容暂维持不收录。'),
    '10.1103/rx1v-3cpc': ('retain_exclusion_correct_reason', '自身 DOI 的 correction 关联不足以判为通知；摘要研究分子纳磁体量子性检验，未见网络结构或方法研究。'),
    '10.1103/mclp-9db8': ('review_publication_identity', 'Bethe 晶格渗流与相互作用的标题支持相关性；自身 DOI 更正关联不能证明是独立通知。优先核实出版方文章身份，确认后可考虑补入。'),
    '10.1103/jlvb-t2xl': ('review_insufficient_evidence', '自身 DOI 更正关联；当前无摘要。量子投票标题不能确定网络相关性，撤销确定性通知判断、保留待核实。'),
    '10.1103/hxzf-nmpx': ('review_insufficient_evidence', '自身 DOI 更正关联；当前无摘要。量子纠缠标题不足以证明网络相关性。'),
    '10.1103/j8wg-6d9d': ('review_insufficient_evidence', '自身 DOI 更正关联；当前无摘要。超导晶格标题不足以判定网络科学内容。'),
    '10.1103/sjqy-gnvp': ('review_insufficient_evidence', '自身 DOI 更正关联；当前无摘要。量子热力学纠缠标题不足以判定网络科学内容。'),
    '10.1103/xs83-z5nk': ('review_insufficient_evidence', '自身 DOI 更正关联；当前无摘要。湍流摩擦标题不足以确认或排除隐式网络方法。'),
    '10.1103/wb7q-78gb': ('review_insufficient_evidence', '自身 DOI 更正关联；当前无摘要。不平等指标标题不足以判定是否使用网络研究。'),
}


def main():
    papers_path = ROOT / 'site/data/papers.json'
    audit_path = ROOT / 'site/data/screening-report.json'
    data = json.loads(papers_path.read_text(encoding='utf-8'))
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    assert hashlib.sha256(papers_path.read_bytes()).hexdigest() == 'deb4a2d9fb26c31a6e86f06948470bc49fe149113efb23a718a1818379afbfbe', 'Review indices belong to the frozen baseline only'
    assert hashlib.sha256(audit_path.read_bytes()).hexdigest() == '3a27681020a428944d390e38c6b6456754581516fa04ebf65ed75f1f03455171', 'Excluded cohort changed'
    assert data['window_end'] == '2026-09-29' and len(data['papers']) == 181
    notes = dict(NOTES)
    notes.update(MISSING)
    for note, indices in TITLE_GROUPS.items():
        for i in indices:
            assert i not in notes, i
            notes[i] = note
    assert set(notes) == set(range(181)), sorted(set(range(181)) - set(notes))
    records = []
    for i, paper in enumerate(data['papers']):
        decision = 'review_insufficient_evidence' if i in PENDING else 'recommend_exclude' if i in EXCLUDE_RECOMMENDATIONS else 'retain_inclusion'
        records.append({'doi': paper['doi'], 'title': paper['title'], 'original_decision': 'included',
                        'review_decision': decision, 'evidence_level': 'title_and_current_abstract' if i in NOTES else 'title_only',
                        'rationale': notes[i], 'source_url': paper['metadata_url'],
                        'source_checked': '2026-09-30' if i in NOTES or i in MISSING else 'saved_baseline',
                        'full_text_reviewed': False})
    excluded = [row for row in audit['decisions'] if row['decision'] == 'excluded']
    for row in excluded:
        doi = row['doi']
        special = SPECIAL_EXCLUDED.get(doi)
        decision, rationale = special or ('retain_exclusion_notice', '标题明确为更正、撤稿、关注声明、编委名单或社论；按既定类型边界不作为研究文章收录。')
        records.append({'doi': doi, 'title': row['title'], 'original_decision': 'excluded',
                        'original_reason': row['reason'], 'review_decision': decision,
                        'evidence_level': 'current_crossref_metadata' if special else 'notice_title',
                        'rationale': rationale, 'source_url': 'https://api.crossref.org/works/' + doi,
                        'source_checked': '2026-09-30' if special else 'saved_baseline', 'full_text_reviewed': False})
    assert len(excluded) == 283 and len(records) == 464
    assert len({r['doi'] for r in records}) == 464
    result = {'review_date': '2026-09-30', 'reviewer': 'AI assistant; not human expert certification',
              'baseline_commit': 'f521ae3', 'window_start': data['window_start'], 'window_end': data['window_end'],
              'papers_sha256': hashlib.sha256(papers_path.read_bytes()).hexdigest(),
              'audit_sha256': hashlib.sha256(audit_path.read_bytes()).hexdigest(),
              'scope': '181 displayed and 283 explicitly excluded; no review of the 10428 pending candidates',
              'limitations': 'Title-level review for clear titles and notices; 63 current abstracts inspected among included papers. No full-text review. Recommendations not applied to site or rules.',
              'counts': {group: dict(Counter(r['review_decision'] for r in records if r['original_decision'] == group)) for group in ['included', 'excluded']},
              'records': records}
    output = ROOT / 'reports/baseline-review-2026-09-30.json'
    if output.exists():
        raise FileExistsError('Preserve prior review; inspect changes before replacing it.')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['counts'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
