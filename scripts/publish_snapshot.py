"""Export only current, resolved inclusions to the public website; no network requests."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlparse
from screen_candidates import Workflow, digest, now, validate_short_comment_review

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'newflow-1'


def author_record(row, record):
    if row['doi'] != record['doi'] or row['record_sha256'] != digest(record):
        raise ValueError('Author metadata record mismatch')
    if row['metadata_sha256'] != digest({k: v for k, v in row.items()
            if k not in {'attempts', 'metadata_sha256'}}):
        raise ValueError('Author metadata hash mismatch')
    authors = row['authors']
    if not isinstance(authors, list) or any(not isinstance(a, str) or not a.strip()
            or a.casefold().strip() in {'anonymous', 'unknown', 'author', 'authors', 'et al.', 'et al'} for a in authors):
        raise ValueError('Invalid or placeholder author')
    if row['status'] == 'available':
        if not authors or not row.get('basis') or not row.get('retrieved_at') or urlparse(row.get('source_url', '')).scheme != 'https':
            raise ValueError('Author list lacks source evidence')
    elif row['status'] not in {'unresolved', 'not_started_rate_limit'} or authors:
        raise ValueError('Invalid author metadata status')
    return row



def build_snapshot(out):
    w = Workflow(out)
    if w.active():
        raise ValueError('Finish the active assessment before publishing')
    original = w.log.events[0]['data']['original_sha256']
    for name, expected in original.items():
        if hashlib.sha256((w.out/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Original collection file changed: '+name)
    notes = json.loads((ROOT/'config/publication-notes.json').read_text(encoding='utf-8'))
    latest = w.assessments()
    included = [d for d in latest if d['category'] in {'core', 'transferable_application'}]
    if set(notes['papers']) != {d['doi'] for d in included}:
        raise ValueError('Notes must match exactly the current included DOI set')
    author_data = json.loads((w.out/'author-metadata.json').read_text(encoding='utf-8'))
    if author_data['candidate_sha256'] != w.input_sha or set(author_data['records']) != {d['doi'] for d in included}:
        raise ValueError('Author metadata must match the fixed inventory and included DOI set')
    author_hash = digest(author_data)
    if not any(e['kind'] == 'author_metadata_completed' and e['data']['metadata_sha256'] == author_hash for e in w.log.events):
        raise ValueError('Author metadata lacks matching audit event')
    history = {digest(e['data']): e['data'] for e in w.log.events
               if e['kind'] in {'assessment', 'assessment_corrected'}}
    theme_ids = {c['id'] for c in notes['categories']}
    journals = {j['short']: j for j in w.config['journals']}
    papers = []
    for d in included:
        r = w.records[d['doi']]
        n = notes['papers'][d['doi']]
        a = author_record(author_data['records'][d['doi']], r)
        if n['assessment_sha256'] != digest(d):
            raise ValueError('Reading note refers to a superseded assessment: '+d['doi'])
        if d['input_sha256'] != digest({'record': r, 'material_sha256': d['material_sha256'],
                'hard_checks': d['hard_checks'], 'rule_sha256': d['rule_sha256']}):
            raise ValueError('Assessment input hash mismatch')
        evidence_kind = n.get('review_evidence_kind', 'abstract')
        if evidence_kind not in {'abstract', 'abstract_excerpt', 'online_short_comment'}:
            raise ValueError('Unknown reviewed evidence kind')
        short_review = None
        if not d['material_sha256']:
            short_review = next((e['data'] for e in reversed(w.log.events)
                if e['kind'] == 'short_comment_reviewed' and e['data']['doi'] == d['doi']), None)
            if not short_review or evidence_kind != 'online_short_comment':
                raise ValueError('Inclusion without an abstract requires a verified online short-comment review')
            validate_short_comment_review(short_review, r, d)
        elif evidence_kind == 'online_short_comment':
            raise ValueError('Do not relabel an abstract assessment as a no-abstract comment review')
        if any(d['hard_checks'][k]['status'] != 'verified'
                for k in ['identity', 'type', 'date']):
            raise ValueError('Inclusion lacks resolved evidence/checks')
        cats = n['categories']
        if not cats or len(cats) != len(set(cats)) or not set(cats) <= theme_ids or ('other' in cats and len(cats) != 1):
            raise ValueError('Invalid topic assignment')
        if not n['note_zh'].strip() or not 8 <= len(n['note_en'].split()) <= 40:
            raise ValueError('Missing or oversized one-sentence reading note')
        check = d['hard_checks']['date']
        value = check['value']
        if not w.pool['window_start'] <= value <= w.pool['window_end'] or value > date.today().isoformat():
            raise ValueError('Invalid inclusion date')
        accepted = check.get('publication_status') == 'accepted' or check.get('basis', '').startswith('publisher.accepted')
        journal = journals[r['journal']]
        if not set(r['issns']) & set(journal['issns']):
            raise ValueError('Whitelist ISSN mismatch')
        authority = d.get('scope_authority', 'assistant_online_short_comment_screening' if short_review else 'assistant_abstract_screening')
        authority_hash = None
        lineage = d
        visited = set()
        while lineage and digest(lineage) not in visited:
            visited.add(digest(lineage))
            if lineage.get('user_verdict') == 'include' or lineage.get('scope_authority') == 'human user in current conversation':
                authority = 'human user in current conversation'
                authority_hash = digest(lineage)
                break
            previous = history.get(lineage.get('previous_assessment_sha256'))
            if not previous or previous['category'] != d['category'] or previous['material_sha256'] != d['material_sha256']:
                break
            lineage = previous
        evidence_url = short_review['source_url'] if short_review else d['material_source']
        official_url = check.get('source_url') or evidence_url
        url = official_url if accepted else 'https://doi.org/'+d['doi']
        papers.append({'doi': d['doi'], 'url': url, 'title': r['title'], 'authors': a['authors'],
            'author_metadata_status': a['status'], 'author_metadata_sha256': a['metadata_sha256'],
            'author_source_url': a.get('source_url'), 'author_retrieved_at': a.get('retrieved_at'),
            'author_basis': a.get('basis'), 'journal': journal['name'],
            'journal_short': journal['short'], 'issns': r['issns'],
            'date': value, 'date_source': 'publisher.accepted' if accepted else n.get('date_source', 'published-online'),
            'date_provenance': check, 'publication_status': 'accepted' if accepted else 'published',
            'accepted_date': value if accepted else None, 'published_date': None if accepted else value,
            'article_type': d['hard_checks']['type'].get('value'),
            'type_provenance': d['hard_checks']['type'], 'categories': cats,
            'scope_class': d['category'], 'note_en': n['note_en'], 'note_zh': n['note_zh'],
            'scope_authority': authority, 'editorial_support_sha256': authority_hash,
            'assessment_sha256': digest(d), 'input_sha256': d['input_sha256'],
            'material_sha256': d['material_sha256'],
            'review_evidence_kind': evidence_kind, 'review_basis': d['review_basis'],
            'review_evidence_sha256': short_review['evidence_sha256'] if short_review else d['material_sha256'], 'rule_sha256': d['rule_sha256'],
            'featured': journal['short'] if journal['short'] in w.config['featured_journals'] else None,
            'evidence': [d['evidence_summary']], 'metadata_url': 'https://api.crossref.org/works/'+quote(d['doi'], safe=''),
            'evidence_url': evidence_url, 'source': 'Crossref and verified publisher/user evidence',
            'retrieved_by': ['Fixed September journal inventory; DOI-bound '+('authorized online short-comment review' if short_review else 'explicit abstract excerpt review' if evidence_kind=='abstract_excerpt' else 'abstract review')],
            'screening_version': VERSION})
    papers.sort(key=lambda p: (p['date'], p['doi']), reverse=True)
    coverage = json.loads((w.out/'coverage.json').read_text(encoding='utf-8'))
    compact_coverage = [{ 'journal': short,
        'candidate_count': c['window_inventory_count'],
        'publisher_verified_inventory_count': c['publisher_verified_inventory_count'],
        'candidate_inventory_complete': c['candidate_inventory_complete'],
        'metadata_reconciliation_complete': c['metadata_reconciliation_complete']}
        for short, c in coverage['journals'].items()]
    counts = Counter(d['category'] for d in latest)
    deferred = w.status()['deferred_unassessed']
    candidate_count = sum(r['window_membership'] == 'in_window' for r in w.records.values())
    if sum(counts.values())+deferred != candidate_count:
        raise ValueError('Candidate accounting incomplete')
    counts.update({'deferred_unassessed': deferred, 'review': counts['review'], 'included': len(papers)})
    generated_at = now()
    snapshot = {'generated_at': generated_at, 'window_start': w.pool['window_start'],
        'window_end': w.pool['window_end'], 'window_days': 30, 'release_kind': 'reviewed_september_snapshot',
        'screening_version': VERSION, 'config_sha256': digest(w.config), 'current_rule_sha256': w.rule_sha,
        'screening_log_sha256': w.log.head, 'reading_notes_sha256': digest(notes),
        'author_metadata_sha256': author_hash,
        'author_available_count': sum(p['author_metadata_status'] == 'available' for p in papers),
        'source': 'Fixed nine-journal September inventory and traced abstract, short-comment and editorial assessments',
        'categories': notes['categories'], 'featured_journals': w.config['featured_journals'],
        'journals': [{'name': j['name'], 'short': j['short'], 'issns': j['issns']} for j in w.config['journals']],
        'coverage': compact_coverage, 'candidate_count': candidate_count,
        'screening_counts': dict(counts), 'published_count': sum(p['publication_status']=='published' for p in papers),
        'accepted_count': sum(p['publication_status']=='accepted' for p in papers),
        'candidate_inventory_complete': coverage['nine_journal_inventory_complete'],
        'metadata_reconciliation_complete': coverage['nine_journal_reconciliation_complete'],
        'limitations': ['September 2026 trial, not a current 90-day feed.',
            'Nature Communications directory pagination remains unstable; complete publisher coverage is not established.',
            f'{candidate_count} fixed candidates assessed; {counts["review"]} unresolved and {deferred} unassessed.',
            'Assistant screening from explicit abstracts/excerpts or authorized online short comments, plus explicit user scope decisions; not full-text expert review.',
            'Author names are supplemented from matched Crossref metadata or explicit official accepted-page bylines; no authors inferred.'], 'papers': papers}
    audit = {k: snapshot[k] for k in ['generated_at', 'window_start', 'window_end', 'screening_version',
        'config_sha256', 'current_rule_sha256', 'screening_log_sha256', 'reading_notes_sha256',
        'author_metadata_sha256', 'author_available_count',
        'screening_counts', 'candidate_count', 'published_count', 'accepted_count',
        'candidate_inventory_complete', 'metadata_reconciliation_complete', 'limitations']}
    audit['included_assessments'] = [{k: p[k] for k in ['doi', 'scope_class', 'publication_status',
        'assessment_sha256', 'input_sha256', 'material_sha256', 'review_evidence_kind', 'review_evidence_sha256', 'rule_sha256', 'scope_authority', 'author_metadata_status', 'author_metadata_sha256']} for p in papers]
    status = {'attempted_at': generated_at, 'ok': True, 'operation': 'publish_existing_reviewed_snapshot',
        'new_collection_performed': False, 'candidate_inventory_complete': snapshot['candidate_inventory_complete'],
        'metadata_reconciliation_complete': snapshot['metadata_reconciliation_complete'],
        'pending_material': counts['review'], 'deferred_unassessed': deferred}
    return {'papers.json': snapshot, 'screening-report.json': audit, 'status.json': status}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='site/data')
    parser.add_argument('--check', action='store_true', help='Verify public snapshot matches the audited inputs without rewriting it')
    args = parser.parse_args()
    artifacts = build_snapshot(ROOT/'reports/2026-09')
    target = ROOT/args.out
    if args.check:
        for name, value in artifacts.items():
            saved = json.loads((target/name).read_text(encoding='utf-8'))
            for key in ['generated_at', 'attempted_at']:
                value.pop(key, None); saved.pop(key, None)
            if value != saved:
                raise ValueError('Public artifact is stale or inconsistent: '+name)
        print('Public snapshot verified against latest decisions, notes and original inputs.')
    else:
        target.mkdir(parents=True, exist_ok=True)
        # Validation finishes before any public file is replaced.
        for name, value in artifacts.items():
            (target/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Exported '+str(len(artifacts['papers.json']['papers']))+' reviewed papers.')

if __name__ == '__main__':
    main()
