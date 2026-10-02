"""Merge actual closed-loop decisions with the previous immutable progress."""
import json
from collections import Counter
from datetime import datetime, timezone

from private_abstract_cache import ROOT, digest
from review_routes_v9 import TRIAL, load


def main():
    source = TRIAL/'final-screening-progress-v1.json'
    prior = load(source)
    rows = {r['doi']: dict(r) for r in prior['results']}
    inputs = {source.name: digest(source.read_text(encoding='utf-8'))}
    closed = []
    for path in sorted((TRIAL/'closed-loop-decisions-v1').glob('*.json')):
        record = load(path)
        doi = record['doi']
        assert doi in rows and prior['results']
        assert rows[doi]['decision'] == 'review', 'Unexpected repeat or out-of-queue decision'
        assert 'abstract' not in record
        row = rows[doi]
        row.update(decision=record['class'], reason=record['reason'],
                   subject_scope_assessed_this_run=record['subject_scope_assessed'],
                   latest_closed_loop_record=record,
                   latest_closed_loop_file=path.relative_to(TRIAL).as_posix())
        if record.get('screening_summary'):
            row['screening_summary'] = record['screening_summary']
        inputs[path.relative_to(TRIAL).as_posix()] = digest(path.read_text(encoding='utf-8'))
        closed.append(record)
    counts = dict(Counter(r['decision'] for r in rows.values()))
    assert len(rows) == 3987 == sum(counts.values())
    pending = [r['doi'] for r in rows.values() if r['reason'] == 'semantic_review_pending']
    unresolved = [r['doi'] for r in rows.values() if r['decision']=='review' and r['reason']!='semantic_review_pending']
    stamp = datetime.now(timezone.utc)
    payload = dict(created_at=stamp.isoformat(), final_screening_complete=False,
                   window=['2026-09-01','2026-09-30'], cohort_count=len(rows), counts=counts,
                   closed_loop_count=len(closed), closed_loop_counts=dict(Counter(r['class'] for r in closed)),
                   prior_fresh_abstracts_reviewed=prior['fresh_abstracts_reviewed'],
                   subject_scope_assessed=sum(r['subject_scope_assessed_this_run'] for r in rows.values()),
                   semantic_review_not_started=len(pending), pending_dois=pending,
                   unresolved_review_dois=unresolved, input_sha256=inputs,
                   policy_sha256=digest((ROOT/'config/screening-policy-v9.json').read_text(encoding='utf-8')),
                   results=list(rows.values()))
    stem='screening-progress-closed-loop-'+stamp.strftime('%Y%m%dT%H%M%SZ')
    path=TRIAL/(stem+'.json')
    with path.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    md=TRIAL/(stem+'.md')
    with md.open('x',encoding='utf-8') as stream:
        stream.write('\n'.join([
            '# v9 筛选进度（未完成）', '', f'生成时间：{stamp.isoformat()}', '',
            '| 状态 | 篇数 |','|---|---:|',
            f"| 已确认收录 | {counts.get('core',0)+counts.get('transferable_application',0)} |",
            f"| 已排除（含日期及类型硬检查） | {counts.get('excluded',0)} |",
            f'| 尚未主题审读 | {len(pending)} |',
            f'| 已知缺材料或审读判断未决 | {len(unresolved)} |','',
            f"累计完成主题审读 {payload['subject_scope_assessed']} 篇。新闭环流程已保存 {len(closed)} 篇结论。",'',
            '尚未开始全池未决项第二轮复核。仅最终仍无法裁定的文章交由用户判断。',
            '网页尚未发布本批结果；全池筛选、第二轮复核、问答规则页及部署仍待完成。','',
            '恢复工作使用 review_workflow_v9.py next/show/submit；该入口自动跳过已保存的逐篇结论。',''
        ]))
    print(json.dumps({'report':str(md),'counts':counts,'subject_scope_assessed':payload['subject_scope_assessed'],
                      'pending':len(pending),'unresolved':len(unresolved)},ensure_ascii=False))


if __name__ == '__main__':
    main()
