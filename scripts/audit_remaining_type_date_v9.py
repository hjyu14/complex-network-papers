"""Apply publisher-format evidence and append browser date audits, not topic review."""
import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports/v9-2026-09'
INPUTS = ('material-master-v1.json', 'browser-remaining-recheck-v1.json',
          'browser-date-conflict-recheck-v1.json', 'publisher-type-guide-audit-v1.json')
OUTPUTS = ('material-type-date-audit-v1.json', 'material-type-date-audit-v1.md',
           'material-master-v2.json', 'material-master-v2.md')


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed(rows):
    result = {r['doi']: r for r in rows}
    assert len(rows) == len(result), 'Duplicate DOI'
    return result


def iso_date(value):
    return datetime.strptime(value.replace(',', ''), '%d %B %Y').date().isoformat()


def main():
    for name in OUTPUTS:
        if (TRIAL / name).exists():
            raise FileExistsError(f'Refusing to overwrite {name}')
    hashes = {name: fingerprint(TRIAL / name) for name in INPUTS}
    data = {name: json.loads((TRIAL / name).read_text(encoding='utf8')) for name in INPUTS}
    original = data['material-master-v1.json']
    old_rows = indexed(original['results'])
    missing = data['browser-remaining-recheck-v1.json']
    dates = data['browser-date-conflict-recheck-v1.json']
    assert missing['complete'] and dates['complete']
    assert len(missing['results']) == 62 and len(dates['results']) == 11
    assert set(indexed(missing['results'])) == {d for d, r in old_rows.items()
                                             if r['material_state'] == 'needs_material'}
    assert set(indexed(dates['results'])) == {d for d, r in old_rows.items()
                                           if r['material_state'] == 'date_conflict'}
    guides = {s['publisher']: s for s in data['publisher-type-guide-audit-v1.json']['sources']}
    assert set(guides) == {'PNAS', 'Science'}
    type_rows = []
    for r in missing['results']:
        assert r['doi_match'] and r['status'] == 'identity_confirmed'
        assert not r['abstract_available']
        publisher = ('PNAS' if r['doi'].startswith('10.1073/') else
                     'Science' if r['doi'].startswith('10.1126/') else 'APS')
        label = r.get('visible_article_type')
        definition = guides.get(publisher, {}).get('definitions', {}).get(label)
        issue_summary = publisher == 'PNAS' and label == 'This Week in PNAS' and r['title'] == 'In This Issue'
        non_target = bool(definition or issue_summary)
        row = {'doi': r['doi'], 'title': r['title'], 'publisher': publisher,
               'publisher_visible_type': label, 'publisher_metadata_type': r.get('article_type'),
               'publisher_status': r.get('publisher_status'),
               'type_evidence_url': r['source_url'], 'retrieved_at': r['retrieved_at'],
               'abstract_available': False, 'full_text_used_for_screening': False,
               'type_check_result': 'non_target_format_documented' if non_target else 'type_or_evidence_unresolved',
               'hard_check_disposition': 'excluded_non_target_format' if non_target else 'review',
               'type_definition': definition,
               'type_definition_url': guides[publisher]['url'] if definition else None,
               'reason': ('publisher_label_and_official_column_definition' if definition else
                          'publisher_issue_summary_label_and_title' if issue_summary else
                          'accepted_paper_is_status_not_article_type' if publisher == 'APS' else
                          'column_definition_not_confirmed'),
               'subject_scope_classification_deferred': True}
        if publisher == 'APS' and r['doi'] == '10.1103/qbxp-7cbs':
            row['note'] = 'Reply in title alone does not establish a non-target publisher format.'
        type_rows.append(row)
    assert Counter(r['hard_check_disposition'] for r in type_rows) == {
        'excluded_non_target_format': 57, 'review': 5}
    date_rows = []
    for r in dates['results']:
        assert r['doi_match'] and r['status'] == 'identity_confirmed'
        assert r['publisher_status'] == 'published'
        published, accepted = iso_date(r['online_date']), iso_date(r['accepted_date'])
        old_date = old_rows[r['doi']]['material']['crossref_preferred_date']
        assert published == '2026-10-01' and accepted == old_date and accepted.startswith('2026-09-')
        date_rows.append({'doi': r['doi'], 'title': r['title'], 'journal': r['journal'],
                          'publisher_status': r['publisher_status'],
                          'crossref_preferred_date': old_date,
                          'crossref_date_label': old_rows[r['doi']]['material']['crossref_date_source'],
                          'publisher_published_date': published, 'publisher_accepted_date': accepted,
                          'publisher_received_date': iso_date(r['received_date']) if r.get('received_date') else None,
                          'source_url': r['source_url'], 'retrieved_at': r['retrieved_at'],
                          'published_date_window_relation': 'after_window',
                          'accepted_date_window_relation': 'in_window',
                          'date_check_result': 'publisher_timeline_browser_confirmed',
                          'crossref_date_matches_acceptance': True,
                          'hard_check_disposition': 'review',
                          'reason': 'source_conflict_retained_under_v9',
                          'explanation': 'Crossref date equals acceptance date. Current publisher Published date is October 1. This does not prove a Crossref error or rule out an earlier Accepted Paper page.',
                          'window_decision_deferred': True})
    now = datetime.now(timezone.utc).isoformat()
    audit = {'created_at': now, 'window': original['window'], 'input_sha256': hashes,
             'protocol_version': 'v9',
             'policy_sha256': fingerprint(ROOT / 'config/screening-policy-v9.json'),
             'protocol_sha256': fingerprint(ROOT / 'docs/screening-protocol-v9.md'),
             'audit_script_sha256': fingerprint(Path(__file__)),
             'method': 'Publisher-specific format mapping, DOI-verified browser timelines, and explicit unresolved cases; not a topic classifier.',
             'assistant_model': {'family': 'GPT-6', 'exact_runtime_model_id': None,
                                 'limitation': 'Exact runtime model identifier is not exposed in this session.'},
             'counts': {'type_checked': 62, 'non_target_format_documented': 57,
                        'type_review': 5, 'date_browser_checked': 11, 'date_conflict_review': 11,
                        'remaining_review_in_audited_group': 16},
             'type_results': type_rows, 'date_results': date_rows,
             'policy': 'v9 unchanged. Publisher-specific non-target formats can fail the type hard check without an abstract. No body or title-only topic review. Date conflicts remain review.',
             'not_claimed': ['Letter exclusion across journals', 'No scientific data in correspondence',
                             'All metadata conflicts resolved', 'Complete topic screening']}
    master = copy.deepcopy(original)
    master['version'] = 'material-master-v2'
    master['created_at'] = now
    master['parent_material_master'] = {'file': 'material-master-v1.json', 'sha256': hashes['material-master-v1.json']}
    master['current_type_date_audit'] = audit['counts']
    master['supplemental_audit_input_sha256'] = hashes
    type_index, date_index = indexed(type_rows), indexed(date_rows)
    for row in master['results']:
        doi = row['doi']
        if doi in type_index:
            row['type_hard_check_audit'] = type_index[doi]
            row['previous_material_state'] = row['material_state']
            if type_index[doi]['hard_check_disposition'] == 'excluded_non_target_format':
                row['material_state'] = 'non_research_type_documented'
            row['source_references'].append({'file': 'material-type-date-audit-v1.json', 'doi': doi})
        if doi in date_index:
            row['date_browser_audit'] = date_index[doi]
            row['source_references'].append({'file': 'browser-date-conflict-recheck-v1.json', 'doi': doi})
    master['counts'] = dict(sorted(Counter(r['material_state'] for r in master['results']).items()))
    assert master['counts'] == {'abstract_and_date_collected': 3507,
                                'non_research_type_documented': 352, 'needs_material': 5,
                                'date_conflict': 11, 'historical_exclusion_not_recollected': 112}
    assert len(master['results']) == len(indexed(master['results'])) == 3987
    assert set(indexed(master['results'])) == set(old_rows)
    audit_ids = set(type_index) | set(date_index)
    assert len(audit_ids) == 73
    for row in master['results']:
        old = old_rows[row['doi']]
        for key, value in old.items():
            if key not in ('material_state', 'source_references'):
                assert row[key] == value, f'Prior field changed: {row["doi"]} {key}'
        if row['doi'] not in audit_ids:
            assert row == old, 'Unaudited record changed'
    audit['validation'] = {'doi_set_preserved': True, 'all_prior_fields_preserved_except_documented_state_and_appended_sources': True,
                           'unaudited_records_byte_equivalent_as_json_values': 3914,
                           'source_files_sha256_unchanged': all(fingerprint(TRIAL / n) == h for n, h in hashes.items())}
    assert audit['validation']['source_files_sha256_unchanged']
    md = ['# 无摘要文章类型与日期冲突复核', '', f'生成时间：{now}', '',
          '本次覆盖 62 篇类型核对和 11 篇日期浏览器复查；没有开展新的主题审读。', '',
          '## 类型结果', '',
          '57 篇具有非目标栏目格式证据，可通过 v9 文章类型硬检查排除；5 篇保留 review。', '',
          '| 期刊 | 栏目 | 篇数 | 处理 |', '|---|---|---:|---|']
    for (pub, label, decision), count in sorted(Counter((r['publisher'], r['publisher_visible_type'] or '未明确类型', r['hard_check_disposition']) for r in type_rows).items()):
        md.append(f'| {pub} | {label} | {count} | {decision} |')
    md += ['', 'PNAS/Science 的 Letter 按各自官方读者来信定义处理；这不适用于 PRL 的研究 Letter，也不表示来信没有科学论点或数据。Accepted Paper 仅为状态。PNAS 的 Introduction、Science 的 Association Affairs 缺少已核实栏目定义，3 篇 APS Accepted Paper 缺摘要且缺明确类型，均不直接排除。', '',
           f'官方类型来源：[PNAS 作者指南]({guides["PNAS"]["url"]})；[Science 作者指南]({guides["Science"]["url"]})。', '',
           '## 日期结果', '', '11 篇全部浏览器确认：出版社 Published 为 2026-10-01，Crossref 九月日期等于出版社 Accepted 日期。', '',
           '| DOI | Crossref online / Accepted | Publisher Published |', '|---|---|---|']
    md += [f'| [{r["doi"]}]({r["source_url"]}) | {r["publisher_accepted_date"]} | {r["publisher_published_date"]} |' for r in date_rows]
    md += ['', '十月发表日期已经核实；不能由此断言 Crossref 错误，也未证明此前未出现 Accepted Paper 页面。按 v9 的来源冲突规则，这 11 篇仍为 review，未直接删除或静默改日期。若按当前明确 Published 日期取窗口，它们均不属于九月。', '',
           '## 合并与验证', '', '补充总表 material-master-v2.json 保留 3,987 个 DOI 和全部旧材料，仅追加审计证据，57 篇资料状态更新为已记录非目标类型；当前这组 review 从 73 篇缩为 16 篇（5 类型/摘要，11 日期冲突）。', '',
           '旧报告、原始数据、生产网站和 v9 规则保持原样。来源 SHA256、DOI 集合、3,914 条未审计记录不变及所有旧字段保留已实际校验。']
    master_md = ['# 完整材料总表 v2', '', f'生成时间：{now}', '',
                 '本轮追加 62 篇类型审计及 11 篇日期浏览器时间线，保留 v1 与全部历史字段；未进行统一主题筛选。', '',
                 '| 材料状态 | 篇数 |', '|---|---:|']
    master_md += [f'| {k} | {v} |' for k, v in master['counts'].items()]
    master_md += ['', '合计 3,987 个唯一 DOI。原 needs_material 状态剩 5 篇已核查但类型或摘要证据不足的记录，并非尚未访问；11 篇日期冲突保留 review。', '',
                  '逐篇新增结论见 material-type-date-audit-v1.json；解释与来源见 material-type-date-audit-v1.md。旧 review_disposition 保留为历史记录，当前类型硬检查结果在 type_hard_check_audit；日期在 date_browser_audit。']
    for name, payload in (('material-type-date-audit-v1.json', audit), ('material-master-v2.json', master)):
        with (TRIAL / name).open('x', encoding='utf8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write('\n')
    for name, lines in (('material-type-date-audit-v1.md', md), ('material-master-v2.md', master_md)):
        with (TRIAL / name).open('x', encoding='utf8') as f:
            f.write('\n'.join(lines) + '\n')
    print(json.dumps({'audit_counts': audit['counts'], 'master_counts': master['counts'],
                      'validation': audit['validation']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
