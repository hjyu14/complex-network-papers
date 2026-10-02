"""Merge the full original v9 cohort with later material; no new screening."""
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports/v9-2026-09'
INPUTS = (
    'screening-report.json', 'papers.json', 'papers-editorial.json',
    'editorial-review.json', 'material-after-elsevier-verification-corrected.json',
    'material-after-programmatic-v1.json', 'article-status-backfill.json',
    'springer-nature-coverage-v1.json', 'browser-remaining-recheck-v1.json',
    'remaining-material-disposition-v1.json',
)
OUTPUTS = ('material-master-v1.json', 'material-master-v1.md',
           'material-master-audit-v1.json')


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index(rows):
    result = {r['doi'].lower(): r for r in rows}
    assert len(result) == len(rows), 'Duplicate DOI in input'
    return result


def main():
    for name in OUTPUTS:
        if (TRIAL / name).exists():
            raise FileExistsError(f'Refusing to overwrite {name}')
    hashes = {name: fingerprint(TRIAL / name) for name in INPUTS}
    data = {name: json.loads((TRIAL / name).read_text(encoding='utf8'))
            for name in INPUTS}
    initial = index(data['screening-report.json']['decisions'])
    prior = index(data['material-after-elsevier-verification-corrected.json']['results'])
    supplement = index(data['material-after-programmatic-v1.json']['results'])
    trial_papers = index(data['papers.json']['papers'])
    retained = index(data['papers-editorial.json']['papers'])
    editorial = index(data['editorial-review.json']['decisions'])
    status = index(data['article-status-backfill.json']['results'])
    springer = index(data['springer-nature-coverage-v1.json']['records'])
    recheck_payload = data['browser-remaining-recheck-v1.json']
    recheck = index(recheck_payload['results'])
    reviews = index(data['remaining-material-disposition-v1.json']['results'])
    assert len(initial) == 3987 and len(prior) == 3850 and len(supplement) == 1264
    assert set(prior) == {d for d, r in initial.items() if r['decision'] == 'review'}
    assert set(supplement) <= set(prior)
    assert len(retained) == 25 and len(trial_papers) == len(editorial) == 37
    assert set(editorial) == set(trial_papers)
    assert set(retained) == {d for d, r in editorial.items()
                             if r['editorial_class'] != 'excluded'}
    assert recheck_payload['complete'] and len(recheck) == 62
    assert set(recheck) == {d for d, r in supplement.items()
                           if r['collection_state'] == 'needs_material'}
    assert all(r['doi_match'] and r['status'] == 'identity_confirmed' and
               not r['abstract_available'] for r in recheck.values())
    for mapping in (trial_papers, retained, editorial, status, springer, reviews):
        assert set(mapping) <= set(initial), 'Evidence outside original cohort'

    rows = []
    changed_dates = []
    status_keys = ('article_status', 'article_status_evidence', 'status_badge',
                   'display_date', 'display_date_kind', 'window_date',
                   'date_status_evidence_complete_under_updated_rule',
                   'in_september_window_by_updated_rule', 'date_reconciliation',
                   'requires_explicit_status_backfill', 'status_audit_note',
                   'saved_publisher_metadata')
    for doi, origin in sorted(initial.items()):
        old = prior.get(doi)
        new = supplement.get(doi)
        paper = trial_papers.get(doi)
        material = copy.deepcopy(old or {})
        if new:
            material.update(copy.deepcopy(new))
            for key in ('abstract_sources', 'metadata_sources'):
                material[key] = list(dict.fromkeys((old or {}).get(key, []) +
                                                   new.get(key, [])))
            if (old.get('preferred_date'), old.get('date_source')) != (
                    new.get('preferred_date'), new.get('date_source')):
                changed_dates.append(doi)
        if not old and paper:
            material = {
                'abstract_level_material': paper.get('abstract_available', False),
                'abstract_sources': ['papers.json'] if paper.get('abstract_available') else [],
                'preferred_date': paper.get('date'), 'date_source': paper.get('date_source'),
                'abstract_and_complete_preferred_date': bool(
                    paper.get('abstract_available') and paper.get('date')),
            }
        historical_exclusion = (origin['decision'] == 'excluded' or
                                editorial.get(doi, {}).get('editorial_class') == 'excluded')
        if historical_exclusion:
            state = 'historical_exclusion_not_recollected'
        elif new:
            state = new['collection_state']
        elif old and old.get('further_abstract_collection_required') is False:
            assert old.get('publisher_type_evidence')
            state = 'non_research_type_documented'
        elif material.get('abstract_level_material') and material.get('preferred_date'):
            state = 'abstract_and_date_collected'
        else:
            state = 'needs_material'
        date = material.get('preferred_date')
        if state == 'date_conflict':
            window_relation = 'date_conflict_review'
        elif date and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            window_relation = ('before_window' if date < '2026-09-01' else
                               'after_window' if date > '2026-09-30' else 'in_window')
        else:
            window_relation = 'date_unavailable_in_saved_record'
        references = ['screening-report.json']
        for name, mapping in (
            ('material-after-elsevier-verification-corrected.json', prior),
            ('material-after-programmatic-v1.json', supplement),
            ('papers.json', trial_papers), ('papers-editorial.json', retained),
            ('editorial-review.json', editorial), ('article-status-backfill.json', status),
            ('springer-nature-coverage-v1.json', springer),
            ('browser-remaining-recheck-v1.json', recheck),
            ('remaining-material-disposition-v1.json', reviews),
        ):
            if doi in mapping:
                references.append(name)
        row = {
            'doi': doi, 'title': material.get('title') or origin['title'],
            'retrieved_by': origin.get('retrieved_by', []),
            'material_state': state, 'material': material,
            'material_basis': ('latest_fixed_queue_supplement' if new else
                               'previous_material_snapshot' if old else
                               'previous_trial_paper' if paper else 'initial_decision_only'),
            'initial_screening_record': copy.deepcopy(origin),
            'previous_editorial_record': copy.deepcopy(editorial.get(doi)),
            'previous_trial_paper': copy.deepcopy(paper),
            'previous_retained_record': copy.deepcopy(retained.get(doi)),
            'previous_material_date': {
                'value': old.get('preferred_date'), 'source': old.get('date_source'),
                'source_file': 'material-after-elsevier-verification-corrected.json',
            } if old else None,
            'publication_status_backfill': {
                k: copy.deepcopy(status[doi][k]) for k in status_keys if k in status[doi]
            } if doi in status else None,
            'springer_nature_evidence': copy.deepcopy(springer.get(doi)),
            'latest_browser_recheck': copy.deepcopy(recheck.get(doi)),
            'review_disposition': copy.deepcopy(reviews.get(doi)),
            'window_relation_on_recorded_date': window_relation,
            'window_relation_is_final_eligibility': False,
            'source_references': [{'file': name, 'doi': doi} for name in references],
            'unified_v9_classification_deferred': True,
        }
        rows.append(row)

    merged_index = index(rows)
    assert set(merged_index) == set(initial)
    assert all(merged_index[d]['material']['preferred_date'] == r.get('preferred_date')
               for d, r in supplement.items())
    assert all(merged_index[d]['material']['date_conflict_explanation'] ==
               r['date_conflict_explanation'] for d, r in supplement.items()
               if r['collection_state'] == 'date_conflict')
    assert all(merged_index[d]['latest_browser_recheck'] == r for d, r in recheck.items())
    assert all(merged_index[d]['initial_screening_record'] == r for d, r in initial.items())
    counts = dict(Counter(r['material_state'] for r in rows))
    assert counts == {'abstract_and_date_collected': 3507,
                      'non_research_type_documented': 295,
                      'needs_material': 62, 'date_conflict': 11,
                      'historical_exclusion_not_recollected': 112}
    assert sum(counts.values()) == len(rows)
    assert all(hashes[name] == fingerprint(TRIAL / name) for name in INPUTS)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        'version': 'v9-material-master-v1', 'created_at': now,
        'window': ['2026-09-01', '2026-09-30'],
        'original_candidate_count': len(initial), 'original_review_count': len(prior),
        'latest_supplement_count': len(supplement), 'counts': counts,
        'previous_material_and_date_records': 2605,
        'supplement_material_and_date_records': 902,
        'latest_browser_recheck_count': len(recheck),
        'previous_editorially_retained': len(retained),
        'window_relation_counts': dict(Counter(r['window_relation_on_recorded_date'] for r in rows)),
        'input_sha256': hashes,
        'policy_sha256': fingerprint(ROOT / 'config/screening-policy-v9.json'),
        'scope': 'All original candidates preserved; merge only, no new screening or production promotion.',
        'notes': [
            '3507 records carry earlier abstract-level availability and a complete recorded date. '
            'This preserves historical availability, including earlier description-based evidence; '
            'it does not prove all records have a newly verified standalone abstract or pass v9.',
            '112 historical exclusions preserved with their old decisions; their metadata was not recollected.',
            '295 non-research-type evidence records combine 289 supplement records and 6 earlier records; '
            'they are material states, not newly executed exclusion decisions.',
            '62 browser reads completed without new standalone abstracts; 11 date conflicts stay review.',
            'Previous status backfill is separately labelled and cannot overwrite newer publisher evidence.',
            'Recorded date-window relations are diagnostic only; no DOI is removed by date or type here.',
            'No raw abstract prose, HTML, PDF, cookies or credentials are added. No external requests made.',
        ],
        'results': rows,
    }
    master_path = TRIAL / OUTPUTS[0]
    master_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    audit = {
        'created_at': now, 'source_inputs_unchanged': True,
        'exact_original_doi_set_preserved': True, 'duplicate_doi_count': 0,
        'original_unique_dois': len(initial), 'prior_review_rows': len(prior),
        'supplement_rows_merged': len(supplement), 'browser_recheck_rows_merged': len(recheck),
        'previous_retained_records_preserved': len(retained),
        'historical_exclusions_preserved': counts['historical_exclusion_not_recollected'],
        'date_conflicts_preserved': counts['date_conflict'],
        'date_value_or_provenance_updated_from_supplement': len(changed_dates),
        'updated_date_dois': changed_dates, 'counts': counts,
        'input_sha256': hashes, 'master_sha256': fingerprint(master_path),
        'collection_goal_complete': False, 'unified_screening_complete': False,
    }
    (TRIAL / OUTPUTS[2]).write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    labels = {
        'abstract_and_date_collected': '已有摘要级材料与完整记录日期',
        'non_research_type_documented': '已记录非研究类型证据',
        'needs_material': '浏览器核查完成，但无独立摘要',
        'date_conflict': '日期来源冲突',
        'historical_exclusion_not_recollected': '此前排除记录，本轮未重采',
    }
    lines = ['# v9 九月资料合并总表', '', '本次仅合并资料，不执行新的文章类型或主题筛选。', '',
             f'完整初始候选池 **{len(initial):,} 个 DOI**，其中此前 review {len(prior):,} 篇；'
             f'最近补采的 {len(supplement):,} 篇是其子集。全部 DOI 保留，无重复。', '',
             '| 资料状态 | 篇数 |', '|---|---:|']
    lines += [f'| {labels[key]} | {value:,} |' for key, value in counts.items()]
    lines += ['', '3,507 篇由此前已有材料的 2,605 篇和最近补齐的 902 篇组成。'
              '“摘要级材料”保留历史口径，部分早期材料含文章描述；不能据此宣称全部已验证为独立摘要或完成 v9 审读。', '',
              '295 篇类型证据来自最近 289 篇及此前 6 篇；本次不把 Letter、Reply、Commentary 一概排除。', '',
              '62 篇浏览器核查结果和 11 篇日期冲突逐 DOI 并入。此前 25 篇保留、112 篇排除的记录作为历史审读证据保存，'
              '不当作新一轮 v9 结论。', '',
              '保留原始日期、更新后的日期、来源、APS 状态补证、出版社类型差异、来源文件哈希。'
              '按记录日期计算的窗口关系只供后续核对，不删除记录。', '',
              '合并输出：`material-master-v1.json`；校验记录：`material-master-audit-v1.json`。'
              '输入报告与生产网站未修改，没有重新联网采集。', '']
    (TRIAL / OUTPUTS[1]).write_text('\n'.join(lines), encoding='utf8')
    print(json.dumps({k: v for k, v in audit.items() if k not in
                      ('input_sha256', 'updated_date_dois')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
