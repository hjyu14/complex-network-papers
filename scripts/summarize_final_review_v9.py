"""Validate and combine the explicitly reviewed batch with the full queue."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone

from prepare_final_review_v9 import ROOT, TRIAL


def main():
    output = TRIAL/'final-screening-progress-v1.json'
    markdown = TRIAL/'final-screening-progress-v1.md'
    if output.exists() or markdown.exists():
        raise FileExistsError('Refusing to overwrite a review snapshot')
    inputs = ['final-review-preparation-v1.json', 'semantic-review-batch-001.json',
              'papers-editorial.json', 'final-review-reads-000-v1.json',
              'final-review-reads-008-v1.json', 'final-review-reads-017-v1.json',
              'final-review-reads-010-v1.json']
    hashes = {n: hashlib.sha256((TRIAL/n).read_bytes()).hexdigest() for n in inputs}
    load = lambda n: json.loads((TRIAL/n).read_text(encoding='utf-8'))
    preparation = load(inputs[0])
    batch = load(inputs[1])
    papers = load('papers-editorial.json')['papers']
    reads = {}
    for name in inputs[3:]:
        for read in load(name)['results']:
            if read.get('abstract_available'):
                reads[read['doi']] = dict(read, evidence_file=name)
    source_config = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
    journals = {j['name']: set(j['issns']) for j in source_config['journals']}
    all_rows = {r['doi']: dict(r) for r in preparation['results']}
    included = []
    now = datetime.now(timezone.utc).isoformat()
    assert len(batch['decisions']) == len(set(d['index'] for d in batch['decisions'])) == 25
    for d in batch['decisions']:
        paper = papers[d['index']]
        read = reads[paper['doi']]
        assert read['doi_match'] and read['abstract_available']
        assert read['article_type'] == 'journal-article'
        assert set(read['issns']) & journals[paper['journal']]
        assert read['title'] == paper['title'], 'Changed title requires separate review'
        date_parts = (read.get('published_online') or read.get('published_print'))['date-parts'][0]
        assert len(date_parts) == 3
        date = '-'.join([str(date_parts[0]), f'{date_parts[1]:02d}', f'{date_parts[2]:02d}'])
        assert date == paper['date'] and '2026-09-01' <= date <= '2026-09-30'
        row = all_rows[paper['doi']]
        assert row['decision'] == 'review'
        row.update(decision=d['class'], reason=d['reason'], evidence=d['evidence'],
                   subject_scope_assessed_this_run=True, reviewed_at=now,
                   reviewer=batch['reviewer'], current_review_source=read,
                   review_record_file='semantic-review-batch-001.json')
        if d['class'] in ('core', 'transferable_application'):
            summary = d['screening_summary']
            assert 12 <= len(summary.split()) <= 30
            assert summary.endswith('.') and summary.count('.') == 1
            row['screening_summary'] = summary
            included.append({
                'doi': paper['doi'], 'title': paper['title'], 'journal': paper['journal'],
                'issns': read['issns'], 'date': date, 'date_source': paper['date_source'],
                'class': d['class'], 'screening_summary': summary,
                'url': paper['url'], 'abstract_evidence_url': read['source_url'],
                'evidence': d['evidence'], 'review_input_sha256': read['review_input_sha256'],
            })
    counts = dict(Counter(r['decision'] for r in all_rows.values()))
    pending = [r['doi'] for r in all_rows.values()
               if r['reason'] == 'semantic_review_pending']
    assert len(all_rows) == sum(counts.values()) == 3987
    assert len(pending) == 3239 - 25
    assert all(hashes[n] == hashlib.sha256((TRIAL/n).read_bytes()).hexdigest() for n in inputs)
    payload = {
        'created_at': now, 'final_screening_complete': False,
        'window': preparation['window'], 'cohort_count': len(all_rows),
        'counts': counts, 'fresh_abstracts_reviewed': 25,
        'semantic_review_not_started': len(pending),
        'input_sha256': hashes, 'policy_sha256': preparation['policy_sha256'],
        'sources_config_sha256': preparation['sources_config_sha256'],
        'limitations': preparation['limitations'] + [
            'Counts of eligible papers are a lower bound from one batch, not the final September total.',
            'Two reviewed scope-boundary cases and two known missing abstracts remain review.',
            'No production files were changed. This is not full-text or expert review.',
        ],
        'included': included, 'pending_dois': pending, 'results': list(all_rows.values()),
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = [
        '# v9 最终筛选进度（未完成）', '',
        '窗口：2026-09-01 至 2026-09-30；固定候选池：3,987 个 DOI。', '',
        '**本文件不是九月最终收录结果。多数旧材料只保存摘要可用性、字数、哈希或关键词，不能替代逐篇语义审读。**', '',
        '## 当前进度', '',
        '- 全池硬检查排除 746 篇：日期窗外 293、非目标类型 355、明确通知标题 98。',
        f'- 已重新读取并审读旧候选 25 篇：收录 {len(included)}、主题排除 3、边界待复核 2。',
        '- 全池当前排除 749 篇，review 3,218 篇；其中 3,214 篇尚未主题审读，2 篇边界不确定，2 篇已知缺摘要。',
        '- 20 篇为目前已确认的收录下限，不能作为九月最终数量。', '',
        '## 已确认候选', '', '| DOI | 期刊 | 类别 |', '|---|---|---|',
    ]
    lines += [f"| {p['doi']} | {p['journal']} | {p['class']} |" for p in included]
    lines += ['', '## 恢复工作', '',
              '- 使用 final-screening-progress-v1.json 的 pending_dois，不能重复从旧25篇开始。',
              '- 按 DOI 从已有确认来源临时读取摘要，读取后立即保存分类理由、简短证据、输入哈希和来源。',
              '- 不落盘完整摘要，不以 description、搜索片段或关键词命中替代语义判断。',
              '- 新批次另存文件，保留旧文件；最终必须分别报告未审读、证据缺失和判断不确定。',
              '- 尚未修改或发布生产网页。', '']
    markdown.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'counts': counts, 'included': len(included), 'pending': len(pending),
                      'validated': True, 'final_screening_complete': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
