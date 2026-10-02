"""Audit saved material and merge verified publication status; never store prose."""
import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports/v9-2026-09'
CODES = {'pre': 'Physical Review E', 'prl': 'Physical Review Letters',
         'prresearch': 'Physical Review Research', 'prx': 'Physical Review X',
         'rmp': 'Reviews of Modern Physics'}


def read(name):
    return json.loads((TRIAL / name).read_text(encoding='utf-8'))


def write(name, data):
    path = TRIAL / name
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def run():
    material = read('material-after-browser-round1.json')
    rows = {r['doi']: dict(r) for r in material['results'] if r['abstract_level_material']}
    retained = read('papers-editorial.json')['papers']
    for r in retained:
        assert r['doi'] not in rows
        rows[r['doi']] = dict(r, previously_retained=True)
    evidence = {}
    for r in read('browser-round1-50-evidence.json')['results']:
        p = r['publication_evidence']
        evidence[r['doi']] = {'source_file': 'browser-round1-50-evidence.json',
            'source_url': r['source_url'], 'status': 'published' if p['publication_confirmed'] else 'accepted',
            'published_date': p['publisher_published_date'], 'accepted_date': p['publisher_accepted_date'],
            'doi_and_issn_verified': True}
    for suffix, code, route, pub, acc in read('status-backfill-browser-observations.json')['observations']:
        doi = '10.1103/' + suffix
        assert doi in rows and doi not in evidence
        journal = rows[doi].get('journal') or rows[doi]['retrieved_by'][0].removeprefix('journal: ')
        assert journal == CODES[code]
        assert route in ('abstract', 'accepted') and (pub if route == 'abstract' else acc)
        for date in (pub, acc):
            if date:
                datetime.strptime(date, '%Y-%m-%d')
        evidence[doi] = {'source_file': 'status-backfill-browser-observations.json',
            'source_url': f'https://journals.aps.org/{code}/{route}/{doi}',
            'status': 'published' if pub else 'accepted', 'published_date': pub,
            'accepted_date': acc, 'doi_and_issn_verified': True}
    for url, group in read('status-backfill-listing-observations.json')['sources'].items():
        code = group['journal_code']
        assert url.startswith(f'https://journals.aps.org/{code}/issues/')
        for pub, suffixes in group['published_dates'].items():
            datetime.strptime(pub, '%Y-%m-%d')
            for suffix in suffixes:
                doi = '10.1103/' + suffix
                assert doi in rows and doi not in evidence
                journal = rows[doi].get('journal') or rows[doi]['retrieved_by'][0].removeprefix('journal: ')
                assert journal == CODES[code]
                evidence[doi] = {'source_file': 'status-backfill-listing-observations.json',
                    'source_url': url, 'article_link_on_source': f'https://journals.aps.org/{code}/abstract/{doi}',
                    'status': 'published', 'published_date': pub, 'accepted_date': None,
                    'doi_and_issn_verified': True, 'basis': 'Own Published label in publisher issue entry, not issue date.'}
    metadata = {}
    for filename in ('publisher-structured-v2.json', 'publisher-canonical-v2.json'):
        for r in read(filename)['results']:
            b = r.get('bibliographic_metadata', {})
            if r['doi'] in rows and b and b.get('citation_doi', '').lower() == r['doi']:
                metadata.setdefault(r['doi'], []).append({'source_file': filename, 'fields': b})
    queue = []
    for doi, r in rows.items():
        is_aps = doi.startswith('10.1103/')
        p = evidence.get(doi)
        if p:
            r['article_status'] = p['status']
            r['article_status_evidence'] = p
            r['status_badge'] = {'zh': '已接收', 'en': 'Accepted Paper'} if p['status'] == 'accepted' else None
            r['display_date'] = p['published_date'] or p['accepted_date']
            r['display_date_kind'] = 'publication' if p['published_date'] else 'acceptance'
            r['window_date'] = r['display_date']
            r['date_status_evidence_complete_under_updated_rule'] = True
            r['in_september_window_by_updated_rule'] = '2026-09-01' <= r['window_date'] <= '2026-09-30'
            original = r.get('preferred_date', r.get('date'))
            r['date_reconciliation'] = 'same_value' if original == r['display_date'] else 'different_or_missing_original_date'
        else:
            r['article_status'] = 'unverified'
            r['date_status_evidence_complete_under_updated_rule'] = False if is_aps else None
            r['status_badge'] = None
            r['saved_publisher_metadata'] = metadata.get(doi, [])
            r['requires_explicit_status_backfill'] = is_aps
            r['status_audit_note'] = ('No saved explicit status evidence; APS backfill required.' if is_aps else
                'Version not individually audited; no blanket version audit required. Keep existing publication-date provenance and metadata checks; no badge inferred.')
            if is_aps:
                queue.append({'doi': doi, 'title': r['title'],
                              'previously_retained': r.get('previously_retained', False)})
        r['scope_assessment_unchanged'] = True
    counts = {'existing_material_and_retained': len(rows),
              'aps_target': sum(d.startswith('10.1103/') for d in rows),
              'aps_status_complete': len(evidence),
              'aps_published': sum(p['status'] == 'published' for p in evidence.values()),
              'aps_accepted': sum(p['status'] == 'accepted' for p in evidence.values()),
              'aps_still_needing_browser_evidence': len(queue),
              'aps_reused_previous_browser_evidence': 50,
              'aps_new_article_page_observations': len(read('status-backfill-browser-observations.json')['observations']),
              'aps_new_issue_entry_observations': sum(len(s) for g in read('status-backfill-listing-observations.json')['sources'].values() for s in g['published_dates'].values()),
              'non_aps_saved_publisher_metadata': sum(d in metadata and not d.startswith('10.1103/') for d in rows),
              'non_aps_explicit_status_not_recorded': sum(not d.startswith('10.1103/') and d not in evidence for d in rows),
              'non_aps_blanket_version_audit_required': 0}
    assert counts['aps_status_complete'] + len(queue) == counts['aps_target'] == 439
    input_files = ('material-after-browser-round1.json', 'papers-editorial.json', 'browser-round1-50-evidence.json',
                   'status-backfill-browser-observations.json', 'status-backfill-listing-observations.json',
                   'publisher-structured-v2.json', 'publisher-canonical-v2.json')
    write('article-status-backfill.json', {'version': 'v9', 'updated_at': datetime.now(timezone.utc).isoformat(),
        'counts': counts, 'aps_complete': not queue,
        'audit_scope': 'Existing APS records: complete status/date backfill; non-APS: saved metadata inventory only.',
        'input_sha256': {n: hashlib.sha256((TRIAL / n).read_bytes()).hexdigest() for n in input_files},
        'policy_sha256': hashlib.sha256((ROOT / 'config/screening-policy-v9.json').read_bytes()).hexdigest(),
        'notes': ['Status-only audit; existing topic evidence and scope decisions preserved.',
                  'Non-APS version inventory is not a pending task or a screening gate; first online publication is sufficient. Do not claim individual publisher confirmation.',
                  'Accepted date is used as acceptance, never renamed publication.',
                  'Original material and editorial reports remain unchanged.'],
        'results': sorted(rows.values(), key=lambda r: r['doi'])})
    write('article-status-backfill-pending.json', {'counts': counts,
        'aps': sorted(queue, key=lambda r: (not r['previously_retained'], r['doi'])),
        'non_aps_blanket_version_audit': [],
        'non_aps_inventory_reference': 'article-status-backfill-inventory.json',
        'note': 'No blanket non-APS version audit. Existing missing/conflicting metadata queues remain applicable.'})
    write('article-status-backfill-inventory.json', {'is_pending_task': False,
        'non_aps_explicit_version_not_audited': [{'doi': r['doi'], 'title': r['title'],
            'has_saved_publisher_metadata': bool(r.get('saved_publisher_metadata'))}
            for r in rows.values() if not r['doi'].startswith('10.1103/')]})
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    run()
