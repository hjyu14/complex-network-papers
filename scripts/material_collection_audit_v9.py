"""Audit the fixed queue and date evidence; do not perform topic screening."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TRIAL = Path(__file__).resolve().parents[1] / 'reports' / 'v9-2026-09'


def read(name):
    return json.loads((TRIAL / name).read_text(encoding='utf8'))


def main():
    original_name = 'material-pending-after-elsevier-verification-corrected.json'
    original = read(original_name)
    original_rows = original['missing_abstract'] + original['missing_preferred_date_with_abstract']
    merged = read('material-after-programmatic-v1.json')
    rows = merged['results']
    ids = {r['doi'] for r in rows}
    assert len(rows) == len(ids) == 1264
    assert ids == {r['doi'] for r in original_rows}
    browser = read('browser-material-batch-v1.json')['results']
    navigation = read('browser-navigation-queue-v1.json')
    navigation_rows = navigation if isinstance(navigation, list) else navigation.get('results', navigation.get('rows', []))
    assert len(browser) == len({r['doi'] for r in browser}) == 378
    assert {r['doi'] for r in browser} == {r['doi'] for r in navigation_rows}
    browser_index = {r['doi']: r for r in browser}
    elsevier = [r for r in rows if r['doi'].startswith('10.1016/')]
    assert len(elsevier) == 297
    date_records = []
    for row in elsevier:
        evidence = browser_index[row['doi']]
        assert row['collection_state'] == 'abstract_and_date_collected'
        assert row['date_source'] == 'publisher-online'
        assert all(evidence.get(k) for k in ('doi_match', 'abstract_available', 'online_date', 'issn', 'journal', 'article_type'))
        date = row['preferred_date']
        window = 'before_window' if date < '2026-09-01' else 'in_window' if date <= '2026-09-30' else 'after_window'
        date_records.append({'doi': row['doi'], 'journal_queries': row['retrieved_by'],
                             'publisher_online_date': date, 'window_relation': window,
                             'source_url': evidence['source_url'], 'source_file': 'browser-material-batch-v1.json'})
    window_counts = dict(Counter(r['window_relation'] for r in date_records))
    assert window_counts == {'before_window': 280, 'in_window': 17}
    payload = {'created_at': datetime.now(timezone.utc).isoformat(),
               'window': {'start': '2026-09-01', 'end': '2026-09-30'},
               'counts': window_counts,
               'online_months': dict(sorted(Counter(r['publisher_online_date'][:7] for r in date_records).items())),
               'results': date_records,
               'note': 'Date evidence only. Original queue retained; no topic classification or production changes.'}
    (TRIAL / 'elsevier-online-date-audit-v1.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    priority_ids = {r['doi'] for r in original['missing_preferred_date_with_abstract']}
    assert len(priority_ids) == 105
    assert all(r.get('preferred_date') and r['collection_state'] == 'abstract_and_date_collected' for r in rows if r['doi'] in priority_ids)
    conflicts = [r for r in rows if r['collection_state'] == 'date_conflict']
    assert len(conflicts) == 11
    for row in conflicts:
        assert row['date_conflict_explanation']['status'] == 'crossref_online_date_matches_publisher_acceptance_date'
        assert row['publisher_online_date'] == '2026-10-01'
        assert row['publisher_accepted_date'].startswith('2026-09-')
    missing = [r for r in rows if r['collection_state'] == 'needs_material']
    recheck_name = 'browser-remaining-recheck-v1.json'
    recheck_payload = read(recheck_name) if (TRIAL / recheck_name).exists() else None
    recheck = {}
    if recheck_payload and recheck_payload.get('complete'):
        recheck_rows = recheck_payload['results']
        recheck = {r['doi']: r for r in recheck_rows}
        assert len(recheck_rows) == len(recheck) == len(missing)
        assert set(recheck) == {r['doi'] for r in missing}
        assert all(r.get('doi_match') and r['status'] == 'identity_confirmed' and
                   not r['abstract_available'] and r['abstract_not_archived']
                   for r in recheck_rows)
    epmc_payload = read('remaining-europepmc-refresh-v3.json')
    epmc = {r['doi']: r for r in epmc_payload['results']}
    assert {r['doi'] for r in missing}.issubset(epmc)
    assert epmc_payload['complete_response']
    crossref = {r['doi']: r for r in read('crossref-refresh-v2.json')['results']}
    openalex = {r['doi']: r for r in read('openalex-material-batch-v1.json')['results']}
    graph_payload = read('remaining-openaire-graph-probe-v3.json')
    graph = {r['doi']: r for r in graph_payload['results']}
    assert graph_payload['complete'] and {r['doi'] for r in missing}.issubset(graph)
    nih_payload = read('remaining-nih-pmc-id-audit-v1.json')
    nih = {r['doi']: r for r in nih_payload['results']}
    oai_payload = read('remaining-nih-oai-front-probe-v1.json')
    oai = {r['doi']: r for r in oai_payload['results']}
    assert nih_payload['complete_response'] and nih_payload['public_status_fields_checked']
    assert oai_payload['complete']
    assert set(oai) == {r['doi'] for r in nih.values() if r.get('pmcid') and r['doi_match']}
    assert all(r['http_status'] == 200 and r['doi_match'] and
               not r['abstract_available'] and r['body_present_in_metadata'] is False
               for r in oai.values())
    control = read('nih-oai-format-control-v1.json')
    assert control['control_only'] and control['fixed_queue_not_modified']
    assert control['europepmc_xml_abstract_available'] and control['oai_abstract_available']
    assert control['oai_doi_match'] and control['body_present'] is False
    pubmed_old = {r['doi']: r for r in read('pubmed-batch-v2.json')['results']}
    pubmed_new_payload = read('remaining-pubmed-xml-completion-v3.json')
    pubmed_new = {r['doi']: r for r in pubmed_new_payload['results']}
    assert pubmed_new_payload['complete_response'] and pubmed_new_payload['http_status'] == 200
    assert all(r['doi_match'] and not r['abstract_available'] for r in pubmed_new.values())
    reviews = []
    for row in missing:
        evidence = browser_index[row['doi']]
        assert evidence.get('doi_match') and not evidence.get('abstract_available')
        assert evidence.get('status') == 'identity_confirmed'
        assert not epmc[row['doi']].get('abstract_available')
        assert crossref[row['doi']]['status'] == 'ok' and not crossref[row['doi']]['abstract_available']
        assert openalex[row['doi']]['doi_match'] and not openalex[row['doi']]['abstract_available']
        assert graph[row['doi']]['status'] == 'not_indexed'
        reviews.append({
            'doi': row['doi'], 'title': row['title'], 'journal_queries': row['retrieved_by'],
            'material_state': 'standalone_abstract_unavailable_on_checked_sources',
            'screening_disposition': 'review', 'reason': 'missing_abstract',
            'publisher_visible_type': evidence.get('visible_article_type'),
            'publisher_metadata_type': evidence.get('article_type'),
            'publisher_source_url': evidence['source_url'],
            'publisher_identity_confirmed': True,
            'publisher_abstract_heading_present': evidence.get('abstract_section_heading_present'),
            'publisher_abstract_section_empty': evidence.get('abstract_section_empty'),
            'europepmc_status': epmc[row['doi']]['status'],
            'europepmc_source_url': epmc[row['doi']].get('source_url'),
            'europepmc_publication_types': epmc[row['doi']].get('publication_types'),
            'nih_pmc_identifier': nih[row['doi']].get('pmcid'),
            'nih_pmc_mapping_doi_match': nih[row['doi']]['doi_match'],
            'nih_archive_live': nih[row['doi']].get('live'),
            'nih_archive_release_date': nih[row['doi']].get('release_date'),
            'nih_archive_release_is_publication_date': False,
            'nih_oai_metadata_status': oai.get(row['doi'], {}).get('status', 'no_pmc_identifier'),
            'nih_oai_source_url': oai.get(row['doi'], {}).get('source_url'),
            'nih_archive_article_type': oai.get(row['doi'], {}).get('archive_article_type'),
            'nih_oai_abstract_coverage_control_passed': True,
            'pubmed_xml_abstract_check': 'matched_without_abstract' if row['doi'] in pubmed_old or row['doi'] in pubmed_new else 'no_confirmed_pubmed_identifier',
            'preferred_date': row['preferred_date'], 'date_source': row['date_source'],
            'checked_channels': {'publisher_page': 'identity_confirmed_without_standalone_abstract',
                                 'crossref': 'matched_without_abstract',
                                 'openalex': 'matched_without_abstract',
                                 'europepmc': epmc[row['doi']]['status'],
                                 'openaire_graph_v3': graph[row['doi']]['status']},
            'evidence_files': ['browser-material-batch-v1.json', 'remaining-europepmc-refresh-v3.json',
                               'crossref-refresh-v2.json', 'openalex-material-batch-v1.json',
                               'remaining-openaire-graph-probe-v3.json',
                               'remaining-nih-pmc-id-audit-v1.json',
                               'remaining-nih-oai-front-probe-v1.json',
                               'remaining-pubmed-xml-completion-v3.json'],
            'full_text_used_for_screening': False,
            'subject_scope_classification_deferred': True,
        })
    for row in conflicts:
        reviews.append({
            'doi': row['doi'], 'title': row['title'], 'journal_queries': row['retrieved_by'],
            'material_state': 'complete_publisher_timeline_with_crossref_conflict',
            'screening_disposition': 'review', 'reason': 'metadata_date_conflict',
            'abstract_level_material': row['abstract_level_material'],
            'timeline': row['date_conflict_explanation'],
            'evidence_files': ['aps-date-conflict-http-v1.json'],
            'subject_scope_classification_deferred': True,
        })
    for review in reviews:
        latest = recheck.get(review['doi'])
        if latest:
            review['browser_recheck'] = {
                'source_file': recheck_name,
                'retrieved_at': latest['retrieved_at'],
                'source_url': latest['source_url'],
                'doi_match': latest['doi_match'],
                'status': latest['status'],
                'abstract_available': latest['abstract_available'],
                'abstract_section_empty': latest['abstract_section_empty'],
                'visible_article_type': latest.get('visible_article_type'),
            }
            review['evidence_files'].append(recheck_name)
    assert len(reviews) == len({r['doi'] for r in reviews}) == len(missing) + len(conflicts)
    disposition = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'policy': 'v9 unchanged; user confirmed missing abstracts with insufficient evidence remain review',
        'counts': {'missing_abstract_review': len(missing), 'date_conflict_review': len(conflicts)},
        'results': sorted(reviews, key=lambda r: r['doi']),
        'notes': ['No Letter or Commentary was excluded solely by type.',
                  'Absence on checked sources does not prove an abstract can never become available.',
                  'Complete publisher timelines are kept separately from window eligibility decisions.',
                  'No full text, PDF or substitute abstract was used for semantic screening.'],
    }
    (TRIAL / 'remaining-material-disposition-v1.json').write_text(json.dumps(disposition, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    audit = {'created_at': datetime.now(timezone.utc).isoformat(),
             'original_input_sha256': hashlib.sha256((TRIAL / original_name).read_bytes()).hexdigest(),
             'fixed_queue_unique': len(ids), 'browser_queue_set_verified': len(browser),
             'priority_dates_completed': len(priority_ids), 'elsevier_fields_completed': len(elsevier),
             'remaining_browser_recheck_verified': len(recheck),
             'merged_counts': merged['counts'],
             'remaining_abstract_by_journal': dict(Counter(' '.join(r['retrieved_by']) for r in rows if r['collection_state'] == 'needs_material')),
             'aps_conflicts_with_complete_timeline': len(conflicts),
             'aps_conflict_dois': [r['doi'] for r in conflicts],
             'goal_complete': False,
             'limitations': [f'{len(missing)} records still lack a standalone abstract; absence is not semantic exclusion.',
                             '11 complete publisher timelines remain recorded as metadata conflicts under v9.',
                             'Availability hashes and counts do not prove semantic screening or stored abstract prose.']}
    (TRIAL / 'material-collection-audit-v1.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k:v for k,v in audit.items() if k not in ('aps_conflict_dois', 'limitations')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
