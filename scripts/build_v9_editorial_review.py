import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
trial = root / 'reports/v9-2026-09'
payload = json.loads((trial / 'papers.json').read_text(encoding='utf-8'))
excluded = {
    '10.1073/pnas.2601203123': '脑科学中的趋避冲突为主要问题，功能脑网络分析是领域应用，不是可迁移网络科学主贡献。',
    '10.1007/s11071-026-13058-7': '人体运动与呼啦圈是主要问题，单一动作集合的网络分析属于常规领域应用。',
    '10.1126/sciadv.aef3787': '阿尔茨海默病生物过程为主要问题，脑网络拓扑仅作为疾病分组工具。',
    '10.1073/pnas.2603770123': '细胞分化和基因调控是主要问题，gene regulatory network 分析不足以构成网络科学主贡献。',
    '10.1038/s41467-026-75453-3': '罗马道路史研究是主要问题，网络指标用于常规历史网络描述。',
    '10.1038/s41586-026-10876-y': '皮层抑制神经元和睡眠机制是主要问题，神经网络同步只是生物机制分析。',
    '10.1073/pnas.2620995123': '大鼠神经解剖连接图谱是主要问题，网络统计描述未形成可迁移网络方法贡献。',
    '10.1073/pnas.2611584123': '音乐诱导压力恢复和脑机制是主要问题，功能网络用于领域解释。',
    '10.1126/sciadv.aef2894': '人类皮层通信和计算可靠性是主要问题，网络模型服务于神经科学问题。',
    '10.1063/5.0343851': '忆阻器和脉冲神经元模型是主体，附加同步分析不足以纳入。',
    '10.1038/s41467-026-77302-9': '酒精成瘾和杏仁核分子机制是主要问题，基因共表达网络分析不足以纳入。',
    '10.1063/5.0336997': 'Hindmarsh–Rose 神经元模型和记忆效应是主体，耦合网络同步分析不足以形成可迁移网络贡献。',
}
rows = []
for paper in payload['papers']:
    doi = paper['doi']
    rows.append({'doi': doi, 'title': paper['title'], 'automated_class': paper['class'],
                 'editorial_class': 'excluded' if doi in excluded else paper['class'],
                 'reason': excluded.get(doi, '摘要显示网络结构、网络动力学或可迁移网络方法是主要贡献。')})
result = {'version': 'v9', 'scope': 'September 2026 isolated trial', 'input_count': len(rows),
          'excluded_count': len(excluded), 'retained_count': len(rows) - len(excluded), 'decisions': rows,
          'note': '这是基于标题与摘要的编辑复核，不是全文专家认证；自动初筛原始结果保存在 screening-report.json。'}
(trial / 'editorial-review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'input': len(rows), 'excluded': len(excluded), 'retained': len(rows)-len(excluded)}, ensure_ascii=False))
