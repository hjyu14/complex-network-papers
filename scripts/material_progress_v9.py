"""Report availability on the unchanged original queue; no topic classification."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports' / 'v9-2026-09'


def main():
    merged = json.loads((TRIAL / 'material-after-programmatic-v1.json').read_text(encoding='utf-8'))
    browser = json.loads((TRIAL / 'browser-material-batch-v1.json').read_text(encoding='utf-8'))
    index = {r['doi']: r for r in browser['results']}
    assert len(index) == len(browser['results'])
    records = []
    for row in merged['results']:
        evidence = index.get(row['doi'], {})
        state = row['collection_state']
        if state not in ('needs_material', 'date_conflict'):
            continue
        if state == 'date_conflict':
            issue = 'date_conflict_preserved'
        elif evidence.get('abstract_section_empty') and evidence.get('doi_match'):
            issue = 'publisher_abstract_section_empty'
        elif evidence.get('status') == 'blocked':
            issue = 'publisher_access_error'
        elif evidence.get('status') == 'navigation_error':
            issue = 'navigation_error'
        elif evidence.get('doi_match') and not evidence.get('abstract_available'):
            issue = 'no_standalone_abstract_on_inspected_page'
        elif evidence:
            issue = 'publisher_identity_unconfirmed'
        else:
            issue = 'not_yet_browser_collected'
        records.append({
            'doi': row['doi'], 'title': row.get('title'),
            'journal_queries': row.get('retrieved_by'), 'collection_state': state,
            'remaining_issue': issue,
            'visible_article_type': evidence.get('visible_article_type'),
            'metadata_article_type': evidence.get('article_type'),
            'source_url': evidence.get('source_url'),
            'preferred_date': row.get('preferred_date'),
            'date_source': row.get('date_source'),
            'date_conflict_explanation': row.get('date_conflict_explanation'),
            'abstract_level_material': row.get('abstract_level_material'),
            'classification_deferred': True,
        })
    counts = dict(Counter(r['remaining_issue'] for r in records))
    original = json.loads((TRIAL / 'material-pending-after-elsevier-verification-corrected.json').read_text(encoding='utf-8'))
    date_priority = {r['doi'] for r in original['missing_preferred_date_with_abstract']}
    priority_left = sum(r['doi'] in date_priority for r in records)
    payload = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'original_queue': 1264, 'merged_counts': merged['counts'],
        'browser_unique_attempted': len(index),
        'date_conflicts_with_timeline_evidence': sum(bool(r.get('date_conflict_explanation')) for r in records),
        'remaining_issues': counts,
        'priority_date_queue': {'original': len(date_priority), 'remaining': priority_left},
        'results': records,
        'notes': [
            'A missing standalone abstract is not an access failure or a topic exclusion.',
            'Visible publisher type labels are retained alongside conflicting metadata types.',
            'No original DOI was removed. No full abstracts, PDFs, HTML, cookies or credentials are stored.',
            'Collection availability does not establish completed v9 semantic screening.',
        ],
    }
    (TRIAL / 'material-progress-v1.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    md = ['# v9 材料收集进度', '', f"更新：{payload['created_at']}", '',
          '范围：固定原始 1,264 个 DOI；不修改生产网站或原始清单。', '',
          '## 合并结果', '']
    md.extend(f'- `{key}`：{value}' for key, value in merged['counts'].items())
    md.extend(['', f'原 105 篇优先日期待办：已补齐 {105-priority_left} 篇，剩余 {priority_left} 篇。', '',
               '## 仍需处理的具体状态', ''])
    md.extend(f'- `{key}`：{value}' for key, value in counts.items())
    md.extend(['', '空摘要栏目与无独立摘要内容均保留，不虚构摘要，不据此宣称主题筛选完成。',
               '日期冲突保留两边来源，等待按照既定日期规则处理。',
               'Science Careers 网页 DOI 与纸刊 DOI 的关联以页面标注的 Download PDF 链接为证据，仅读取链接，不下载 PDF。', ''])
    (TRIAL / 'material-progress-v1.md').write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({'remaining_issues': counts, 'priority_date_remaining': priority_left, 'browser_attempted':len(index)}))


if __name__ == '__main__':
    main()
