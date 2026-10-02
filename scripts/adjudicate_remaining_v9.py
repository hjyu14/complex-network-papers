"""Resolve the authorized 16-record audit; preserve prior masters and source dates."""
import copy
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports/v9-2026-09'
INPUTS = ('material-master-v2.json', 'material-type-date-audit-v1.json',
          'browser-date-conflict-recheck-v1.json', 'crossref-refresh-v2.json',
          'aps-crossref-date-verification-v1.json', 'remaining-three-type-verification-v1.json')
OUTPUTS = ('remaining-adjudication-v2.json', 'remaining-adjudication-v2.md',
           'material-master-v4.json', 'material-master-v4.md')


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed(rows):
    result = {r['doi']: r for r in rows}
    assert len(result) == len(rows), 'Duplicate DOI'
    return result


def browser_date(value):
    return datetime.strptime(value.replace(',', ''), '%d %B %Y').date().isoformat()


def resolve_aps_date(doi, previous_online, accepted, published, fresh_online):
    """Apply the user-authorized, publisher-labelled acceptance/date condition."""
    if not doi.startswith('10.1103/') or not accepted or not published:
        return {'status': 'review', 'reason': 'missing_required_aps_timeline'}
    try:
        date.fromisoformat(accepted)
        date.fromisoformat(published)
    except ValueError:
        return {'status': 'review', 'reason': 'incomplete_or_invalid_publisher_date'}
    if previous_online != accepted:
        return {'status': 'review', 'reason': 'historical_online_date_not_acceptance'}
    if fresh_online == published:
        status = 'resolved_fresh_crossref_publisher_agreement'
    elif fresh_online in (None, accepted):
        status = 'resolved_authorized_publisher_date_priority'
    else:
        return {'status': 'review', 'reason': 'new_online_date_conflict_requires_review'}
    return {'status': status, 'effective_date': published,
            'effective_date_source': 'publisher-Published',
            'historical_crossref_online_equals_accepted': True,
            'original_date_preserved': True}


def main():
    for name in OUTPUTS:
        if (TRIAL / name).exists():
            raise FileExistsError(f'Refusing to overwrite {name}')
    hashes = {name: fingerprint(TRIAL / name) for name in INPUTS}
    data = {name: json.loads((TRIAL / name).read_text(encoding='utf8')) for name in INPUTS}
    parent = data['material-master-v2.json']
    old = indexed(parent['results'])
    current = data['aps-crossref-date-verification-v1.json']
    browser = data['browser-date-conflict-recheck-v1.json']
    historical = indexed(data['crossref-refresh-v2.json']['results'])
    timeline = indexed(browser['results'])
    refreshed = indexed(current['results'])
    assert current['complete'] and browser['complete'] and len(refreshed) == len(timeline) == 11
    assert set(refreshed) == set(timeline) == {d for d, r in old.items() if r['material_state'] == 'date_conflict'}
    types = indexed(data['remaining-three-type-verification-v1.json']['results'])
    expected_types = {'10.1103/qbxp-7cbs': 'Reply',
                      '10.1073/pnas.2537180123': 'Introduction',
                      '10.1126/science.aem6084': 'Association Affairs'}
    assert {d: r['confirmed_type'] for d, r in types.items()} == expected_types
    assert all(r['identity_confirmed'] and not r['abstract_available'] for r in types.values())
    assert all(old[d]['material_state'] == 'needs_material' for d in types)
    rules = json.loads((ROOT / 'config/screening-policy-v9.json').read_text(encoding='utf8'))
    assert rules['article_type_policy']['confirmed_reply'] == 'exclude'
    assert rules['date_policy']['aps_crossref_online_equals_acceptance']['decision'] == 'use_publisher_published_date'
    decisions = []
    for doi in sorted(timeline):
        r, b, h = refreshed[doi], timeline[doi], historical[doi]
        assert r['status'] == 'ok' and b['doi_match'] and b['publisher_status'] == 'published'
        accepted, published = browser_date(b['accepted_date']), browser_date(b['online_date'])
        raw_parts = r['dates']['published-online']
        assert len(raw_parts) == 3 and h['date_source'] == 'published-online'
        fresh_date = date(*raw_parts).isoformat()
        resolution = resolve_aps_date(doi, h['date'], accepted, published, fresh_date)
        assert resolution['status'] == 'resolved_fresh_crossref_publisher_agreement'
        assert fresh_date == published == '2026-10-01' and h['date'] == accepted
        decisions.append({'doi': doi, 'title': old[doi]['title'],
                          'decision': 'excluded', 'reason': 'outside_2026_09_window',
                          'subject_scope_assessed': False, 'window_relation': 'after_window',
                          'previous_crossref_published_online': h['date'],
                          'current_crossref_published_online': fresh_date,
                          'current_crossref_date_parts': raw_parts,
                          'publisher_accepted_date': accepted, 'publisher_published_date': published,
                          'crossref_source_url': r['url'], 'crossref_retrieved_at': r['retrieved_at'],
                          'publisher_source_url': b['source_url'], 'publisher_retrieved_at': b['retrieved_at'],
                          'date_resolution': resolution,
                          'note': 'Crossref dates changed after the previous snapshot. This records agreement, not proof of a prior metadata error.'})
    for doi, r in sorted(types.items()):
        decisions.append({'doi': doi, 'title': r['publisher_title'], 'decision': 'excluded',
                          'reason': 'confirmed_reply' if r['confirmed_type'] == 'Reply' else 'confirmed_non_target_format',
                          'confirmed_type': r['confirmed_type'],
                          'type_evidence': r, 'subject_scope_assessed': False,
                          'decision_basis': 'user-confirmed Reply exclusion' if r['confirmed_type'] == 'Reply' else 'v9 non-target format hard check using publisher classification'})
    pending_ids = {'10.1103/lvpn-gblk', '10.1103/qz1m-4942'}
    assert pending_ids == {d for d, r in old.items() if r['material_state'] == 'needs_material'} - set(types)
    for doi in sorted(pending_ids):
        decisions.append({'doi': doi, 'title': old[doi]['title'], 'decision': 'review',
                          'reason': 'publisher_accepted_paper_abstract_empty',
                          'publisher_source_url': old[doi]['latest_browser_recheck']['source_url'],
                          'subject_scope_assessed': False, 'further_collection_attempted': False})
    assert len(decisions) == len(indexed(decisions)) == 16
    assert Counter(r['decision'] for r in decisions) == {'excluded': 14, 'review': 2}
    now = datetime.now(timezone.utc).isoformat()
    audit = {'created_at': now, 'protocol_version': 'v9', 'input_sha256': hashes,
             'policy_sha256': fingerprint(ROOT / 'config/screening-policy-v9.json'),
             'protocol_sha256': fingerprint(ROOT / 'docs/screening-protocol-v9.md'),
             'script_sha256': fingerprint(Path(__file__)),
             'authorization': '2026-10-02 user authorized publisher Published date after checking Crossref/Accepted equality, confirmed Reply exclusion, and further verification of the PNAS/Science formats; two empty-abstract Accepted Papers remain review.',
             'counts': {'audited': 16, 'date_resolved_outside_window': 11,
                        'confirmed_non_target_formats': 3, 'review': 2},
             'scope': 'Metadata hard checks for the original 16 records only; no full-body scientific assessment or cohort topic screening.',
             'results': decisions}
    master = copy.deepcopy(parent)
    master['version'] = 'material-master-v4'
    master['created_at'] = now
    master['parent_material_master'] = {'file': 'material-master-v2.json', 'sha256': hashes['material-master-v2.json']}
    master['current_remaining_adjudication'] = audit['counts']
    master['adjudication_input_sha256'] = hashes
    master['policy_sha256'] = audit['policy_sha256']
    master['protocol_sha256'] = audit['protocol_sha256']
    decision_index = indexed(decisions)
    for row in master['results']:
        doi = row['doi']
        if doi not in decision_index:
            continue
        d = decision_index[doi]
        row['material_state_before_v3'] = row['material_state']
        row['current_hard_check_decision'] = copy.deepcopy(d)
        row['source_references'].append({'file': 'remaining-adjudication-v2.json', 'doi': doi})
        if doi in timeline:
            row['current_material'] = copy.deepcopy(row['material'])
            row['current_material'].update({'preferred_date': d['publisher_published_date'],
                                            'date_source': 'publisher-online',
                                            'crossref_current_preferred_date': d['current_crossref_published_online'],
                                            'crossref_preferred_date': d['current_crossref_published_online'],
                                            'publisher_date_conflict': False,
                                            'abstract_and_complete_preferred_date': True,
                                            'collection_state': 'abstract_and_date_collected',
                                            'date_conflict_explanation': {
                                                'status': 'resolved_fresh_crossref_publisher_agreement',
                                                'crossref_preferred_date': d['current_crossref_published_online'],
                                                'publisher_accepted_date': d['publisher_accepted_date'],
                                                'publisher_online_date': d['publisher_published_date'],
                                                'window_decision_deferred': False},
                                            'current_date_resolution': d['date_resolution']})
            row['material_state'] = 'abstract_and_date_collected'
            row['window_relation_before_v3'] = row['window_relation_on_recorded_date']
            row['window_relation_on_recorded_date'] = 'after_window'
            row['window_relation_is_final_eligibility'] = True
            row['source_references'].append({'file': 'aps-crossref-date-verification-v1.json', 'doi': doi})
        elif doi in types:
            row['current_material'] = copy.deepcopy(row['material'])
            row['current_material'].update({'documented_non_research_type': True,
                                            'article_type': types[doi]['confirmed_type'],
                                            'collection_state': 'non_research_type_documented',
                                            'current_type_evidence': types[doi]})
            row['material_state'] = 'non_research_type_documented'
            row['source_references'].append({'file': 'remaining-three-type-verification-v1.json', 'doi': doi})
    master['counts'] = dict(sorted(Counter(r['material_state'] for r in master['results']).items()))
    expected_counts = {'abstract_and_date_collected': 3518, 'historical_exclusion_not_recollected': 112,
                       'needs_material': 2, 'non_research_type_documented': 355}
    assert master['counts'] == expected_counts
    master['window_relation_counts'] = dict(sorted(Counter(r['window_relation_on_recorded_date'] for r in master['results']).items()))
    master['notes'].append('v4: current_hard_check_decision supersedes older review fields for these 16 DOI. Original material/date-conflict reports remain historical; current_material is the resolved material view for 14 adjudicated records. Materials labelled abstract-level can include historical article descriptions, not all verified independent abstracts. v3 is an intermediate output; v4 also updates the nested current Crossref date, conflict explanation and type fields consistently.')
    new = indexed(master['results'])
    assert len(new) == len(old) == 3987 and set(new) == set(old)
    for doi, row in new.items():
        if doi not in decision_index:
            assert row == old[doi], 'Unaudited record changed'
        else:
            for key, value in old[doi].items():
                if key not in {'material_state', 'source_references', 'window_relation_on_recorded_date', 'window_relation_is_final_eligibility'}:
                    assert row[key] == value, f'Historical field changed: {doi}: {key}'
    audit['validation'] = {'unique_doi_count': 3987, 'doi_set_preserved': True,
                           'unaudited_records_unchanged': 3971,
                           'historical_material_and_audit_fields_preserved': True,
                           'source_sha256_unchanged': all(fingerprint(TRIAL / n) == h for n, h in hashes.items())}
    assert audit['validation']['source_sha256_unchanged']
    md = ['# 剩余 16 篇裁定', '', f'生成时间：{now}', '',
          '## 日期：11 篇冲突已解决', '',
          '此前 Crossref published-online 全部等于九月接收日期。本轮逐 DOI 重新请求 Crossref，11 篇 published-online 均已更新为 2026-10-01，与先前逐篇浏览器核实的出版社 Published 日期一致。原始九月日期、接收日期和来源继续保存；不声称此前 Crossref 一定填错。', '',
          '裁定日期均为 2026-10-01，排除出九月窗口。这是日期排除，不是网络科学主题排除。文章保留在总表中，可供十月任务使用。', '',
          '| DOI | 旧 Crossref / Accepted | 新 Crossref / Published |', '|---|---|---|']
    md += [f'| [{r["doi"]}]({r["publisher_source_url"]}) | {r["previous_crossref_published_online"]} | {r["publisher_published_date"]} |' for r in decisions if r['doi'] in timeline]
    md += ['', '## 类型：3 篇核实后排除', '',
           '| DOI | 类型 | 直接证据 |', '|---|---|---|']
    md += [f'| [{doi}]({r["source_url"]}) | {r["confirmed_type"]} | {r["type_confirmation_basis"]} |' for doi, r in sorted(types.items())]
    md += ['', 'APS 未出现独立 article-type 标签；Reply 依据同一 DOI 的出版社正式标题明确回应具名 Comment，并与 PRE 作者指南及 APS Reply 政策定义核对，不是推断 Accepted Paper 类型。PNAS 官方 Introduction 分类页列出该 DOI；Science 当期目录独立列于 Association Affairs，页面元数据为 other。以上仅判定文章格式，不用正文代替摘要，也不作主题结论。', '',
           '## 保留 review：2 篇', '']
    md += [f'- [{doi}]({old[doi]["latest_browser_recheck"]["source_url"]})：{old[doi]["title"]}；Accepted Paper 摘要栏为空。' for doi in sorted(pending_ids)]
    md += ['', '## 资料总表 v4', '', '原 16 篇处理为 14 篇排除（11 时间范围、3 文章类型）、2 篇 review。完整 3,987 DOI 保留；3,971 条未涉及记录未改变。原始数据、旧报告与生产网站未改。v3 为本轮中间输出；v4 同步更新当前材料视图中的 Crossref 日期、冲突解释及类型字段，避免当前字段互相矛盾。', '',
           '总表材料状态：3,518 篇摘要级材料与确定记录日期，355 篇有非目标类型证据，2 篇摘要证据不足，112 篇历史排除未重采。3,518 中的历史摘要级材料仍含文章描述，不能等同全部已有独立摘要；全体主题筛选尚未完成。']
    master_md = ['# 完整材料总表 v4', '', f'生成时间：{now}', '',
                 '| 材料状态 | 数量 |', '|---|---:|']
    master_md += [f'| {key} | {value} |' for key, value in master['counts'].items()]
    master_md += ['', '共 3,987 个唯一 DOI。原 16 篇未决组现在只剩两篇 APS 摘要为空的接收文章；11 篇日期冲突已由刷新后的 Crossref 与出版社一致日期解决，归十月；另 3 篇有直接类型核实证据后排除。', '',
                  '旧 material、review_disposition 与审计字段作为历史保留。上述 16 篇的当前硬检查裁定在 current_hard_check_decision；14 篇的当前日期/类型视图在 current_material。报告：remaining-adjudication-v2.md。', '',
                  '摘要级材料沿用历史口径，部分含文章描述；尚未开展全体主题审读。112 篇历史排除仍需在下一轮复核。']
    for name, obj in [('remaining-adjudication-v2.json', audit), ('material-master-v4.json', master)]:
        with (TRIAL / name).open('x', encoding='utf8') as stream:
            json.dump(obj, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    for name, lines in [('remaining-adjudication-v2.md', md), ('material-master-v4.md', master_md)]:
        with (TRIAL / name).open('x', encoding='utf8') as stream:
            stream.write('\n'.join(lines) + '\n')
    print(json.dumps({'adjudication_counts': audit['counts'], 'master_counts': master['counts'],
                      'validation': audit['validation']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
