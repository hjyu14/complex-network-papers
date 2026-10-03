"""Export only current, resolved inclusions to the public website; no network requests."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from screen_candidates import Workflow, digest, now

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'newflow-1'


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
    history = {digest(e['data']): e['data'] for e in w.log.events
               if e['kind'] in {'assessment', 'assessment_corrected'}}
    theme_ids = {c['id'] for c in notes['categories']}
    journals = {j['short']: j for j in w.config['journals']}
    papers = []
    for d in included:
        r = w.records[d['doi']]
        n = notes['papers'][d['doi']]
        if n['assessment_sha256'] != digest(d):
            raise ValueError('Reading note refers to a superseded assessment: '+d['doi'])
        if d['input_sha256'] != digest({'record': r, 'material_sha256': d['material_sha256'],
                'hard_checks': d['hard_checks'], 'rule_sha256': d['rule_sha256']}):
            raise ValueError('Assessment input hash mismatch')
        if not d['material_sha256'] or any(d['hard_checks'][k]['status'] != 'verified'
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
        authority = d.get('scope_authority', 'assistant_abstract_screening')
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
        official_url = check.get('source_url') or d['material_source']
        url = official_url if accepted else 'https://doi.org/'+d['doi']
        papers.append({'doi': d['doi'], 'url': url, 'title': r['title'], 'authors': [],
            'author_metadata_status': 'not_collected', 'journal': journal['name'],
            'journal_short': journal['short'], 'issns': r['issns'],
            'date': value, 'date_source': 'publisher.accepted' if accepted else 'published-online',
            'date_provenance': check, 'publication_status': 'accepted' if accepted else 'published',
            'accepted_date': value if accepted else None, 'published_date': None if accepted else value,
            'article_type': d['hard_checks']['type'].get('value'),
            'type_provenance': d['hard_checks']['type'], 'categories': cats,
            'scope_class': d['category'], 'note_en': n['note_en'], 'note_zh': n['note_zh'],
            'scope_authority': authority, 'editorial_support_sha256': authority_hash,
            'assessment_sha256': digest(d), 'input_sha256': d['input_sha256'],
            'material_sha256': d['material_sha256'], 'rule_sha256': d['rule_sha256'],
            'featured': journal['short'] if journal['short'] in w.config['featured_journals'] else None,
            'evidence': [d['evidence_summary']], 'metadata_url': 'https://api.crossref.org/works/'+quote(d['doi'], safe=''),
            'evidence_url': d['material_source'], 'source': 'Crossref and verified publisher/user evidence',
            'retrieved_by': ['Fixed September journal inventory; DOI-bound abstract review'],
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
    counts.update({'deferred_unassessed': deferred, 'included': len(papers)})
    generated_at = now()
    snapshot = {'generated_at': generated_at, 'window_start': w.pool['window_start'],
        'window_end': w.pool['window_end'], 'window_days': 30, 'release_kind': 'reviewed_september_snapshot',
        'screening_version': VERSION, 'config_sha256': digest(w.config), 'current_rule_sha256': w.rule_sha,
        'screening_log_sha256': w.log.head, 'reading_notes_sha256': digest(notes),
        'source': 'Fixed nine-journal September inventory and traced abstract/editorial assessments',
        'categories': notes['categories'], 'featured_journals': w.config['featured_journals'],
        'journals': [{'name': j['name'], 'short': j['short'], 'issns': j['issns']} for j in w.config['journals']],
        'coverage': compact_coverage, 'candidate_count': candidate_count,
        'screening_counts': dict(counts), 'published_count': sum(p['publication_status']=='published' for p in papers),
        'accepted_count': sum(p['publication_status']=='accepted' for p in papers),
        'candidate_inventory_complete': coverage['nine_journal_inventory_complete'],
        'metadata_reconciliation_complete': coverage['nine_journal_reconciliation_complete'],
        'limitations': ['September 2026 trial, not a current 90-day feed.',
            'Nature Communications directory pagination remains unstable; complete publisher coverage is not established.',
            '55 material-insufficient and 325 unassessed records remain undisplayed.',
            'Abstract-based assistant screening and explicit user scope decisions; not full-text expert review.',
            'Authors were not collected by the minimal bibliographic query; no authors inferred.'], 'papers': papers}
    audit = {k: snapshot[k] for k in ['generated_at', 'window_start', 'window_end', 'screening_version',
        'config_sha256', 'current_rule_sha256', 'screening_log_sha256', 'reading_notes_sha256',
        'screening_counts', 'candidate_count', 'published_count', 'accepted_count',
        'candidate_inventory_complete', 'metadata_reconciliation_complete', 'limitations']}
    audit['included_assessments'] = [{k: p[k] for k in ['doi', 'scope_class', 'publication_status',
        'assessment_sha256', 'input_sha256', 'material_sha256', 'rule_sha256', 'scope_authority']} for p in papers]
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
