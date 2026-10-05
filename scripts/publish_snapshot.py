"""Export only current, resolved inclusions to the public website; no network requests."""
import argparse
from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlparse
from screen_candidates import digest, now, validate_short_comment_review
from publication_view import PublicationView, publication_workflow, publisher_url, verify_original

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'newflow-1'


def editorial_reference(decision, record, candidate_sha, events):
    basis = decision.get('editorial_basis')
    if not basis:
        return None
    verdict = next((e['data'] for e in events if e['kind'] == 'user_editorial_verdict'
                    and digest(e['data']) == basis.get('verdict_sha256')), None)
    if (not verdict or verdict.get('doi') != record['doi'] or verdict.get('verdict') != 'include'
            or verdict.get('authority') != 'human user in current conversation'
            or not verdict.get('user_statement')):
        raise ValueError('Inclusion lacks a bound user editorial verdict')
    bindings = {'title': record['title'], 'record_sha256': digest(record), 'candidate_sha256': candidate_sha}
    if any(key in verdict and verdict[key] != value for key, value in bindings.items()):
        raise ValueError('Editorial verdict inventory identity mismatch')
    if basis.get('scope_exception'):
        if (decision['category'] != 'transferable_application' or not verdict.get('scope_exception')
                or not set(bindings) <= set(verdict)
                or basis.get('entry_kind') != 'editorial_related_reading'
                or verdict.get('entry_kind') != basis['entry_kind']
                or not basis.get('not_a_global_scope_rule') or not verdict.get('not_a_global_scope_rule')):
            raise ValueError('Editorial scope exception must remain non-core related reading')
    return verdict


def publication_evidence(w):
    """Read explicitly audited supplemental references; never rewrite frozen coverage flags."""
    path = w.out/'publication-evidence.json'
    if not path.exists():
        return None
    evidence = json.loads(path.read_text(encoding='utf8'))
    if (evidence.get('candidate_sha256') != w.input_sha
            or not any(e['kind'] == 'publication_evidence_selected'
                       and e['data'].get('evidence_sha256') == digest(evidence) for e in w.log.events)):
        raise ValueError('Publication evidence lacks inventory/audit binding')
    for ref in evidence['files']:
        source = (w.out/ref['path']).resolve()
        if (not source.is_relative_to(w.out.resolve())
                or hashlib.sha256(source.read_bytes()).hexdigest() != ref['sha256']):
            raise ValueError('Pinned publication evidence changed')
    return evidence


def merge_coverage(parts):
    """Deduplicate equal windows; sum only disjoint, contiguous journal inventories."""
    merged = []
    for journal, windows in parts.items():
        ordered = sorted(windows.items())
        previous_end = None
        for (start, end), _ in ordered:
            if previous_end is not None and date.fromisoformat(start) != date.fromisoformat(previous_end)+timedelta(days=1):
                raise ValueError('Journal coverage windows must be disjoint and contiguous: '+journal)
            previous_end = end
        rows = [c for _, (c, _) in ordered]
        dois = set().union(*(ds for _, (_, ds) in ordered))
        merged.append({'journal': journal, 'candidate_count': len(dois),
            'publisher_verified_inventory_count': sum(c['publisher_verified_inventory_count'] for c in rows),
            'candidate_inventory_complete': all(c['candidate_inventory_complete'] for c in rows),
            'metadata_reconciliation_complete': all(c['metadata_reconciliation_complete'] for c in rows),
            'windows': [{'window_start': key[0], 'window_end': key[1], **c} for key, (c, _) in ordered]})
    return merged


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



def build_snapshot(out, notes=None):
    w = publication_workflow(out)
    legacy = w.out == (ROOT/'reports/2026-09').resolve()
    if w.active():
        raise ValueError('Finish the active assessment before publishing')
    status = w.status()
    if status['not_assessed'] or any(d['category'] == 'review' for d in w.assessments()):
        raise ValueError('Selected run must finish classification before publishing')
    closed = {e['data']['batch_id'] for e in w.log.events if e['kind'] == 'supplement_batch_closed'}
    if any(e['data']['batch_id'] not in closed for e in w.log.events if e['kind'] == 'supplement_batch_started'):
        raise ValueError('Close supplement batch before publishing')
    if not isinstance(w, PublicationView):
        verify_original(w)
    if notes is None:
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
    evidence_events = w.evidence_events if isinstance(w, PublicationView) else w.log.events
    history = {digest(e['data']): e['data'] for e in evidence_events
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
            short_review = next((e['data'] for e in reversed(evidence_events)
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
            verdict = editorial_reference(lineage, r, w.input_sha, evidence_events)
            if lineage.get('user_verdict') == 'include' or lineage.get('scope_authority') == 'human user in current conversation':
                authority = 'human user in current conversation'
                authority_hash = digest(lineage)
                break
            if verdict:
                authority = verdict['authority']
                authority_hash = digest(verdict)
                break
            previous = history.get(lineage.get('previous_assessment_sha256'))
            if not previous or previous['category'] != d['category'] or previous['material_sha256'] != d['material_sha256']:
                break
            lineage = previous
        evidence_url = short_review['source_url'] if short_review else d['material_source']
        url = publisher_url(r, d)
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
            'retrieved_by': [('Fixed September journal inventory; DOI-bound ' if legacy else 'Explicit journal inventory run; DOI-bound ')+('authorized online short-comment review' if short_review else 'explicit abstract excerpt review' if evidence_kind=='abstract_excerpt' else 'abstract review')],
            'screening_version': VERSION})
        if d.get('editorial_basis', {}).get('scope_exception'):
            papers[-1].update(scope_exception=True, entry_kind='editorial_related_reading',
                scope_class_semantics=d['editorial_basis']['category_semantics'])
    papers.sort(key=lambda p: (p['date'], p['doi']), reverse=True)
    inventory_out = w.sources[0].out if isinstance(w, PublicationView) else w.out
    coverage = json.loads((inventory_out/'coverage.json').read_text(encoding='utf-8'))
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
        'window_end': w.pool['window_end'],
        'window_days': (date.fromisoformat(w.pool['window_end'])-date.fromisoformat(w.pool['window_start'])).days+1,
        'release_kind': 'reviewed_september_snapshot' if legacy else 'reviewed_journal_snapshot',
        'screening_version': VERSION, 'config_sha256': digest(w.config), 'current_rule_sha256': w.rule_sha,
        'screening_log_sha256': w.log.head, 'reading_notes_sha256': digest(notes),
        'author_metadata_sha256': author_hash,
        'author_available_count': sum(p['author_metadata_status'] == 'available' for p in papers),
        'source': ('Fixed nine-journal September inventory and traced abstract, short-comment and editorial assessments'
                   if legacy else 'Explicit journal inventory and traced screening assessments'),
        'categories': notes['categories'], 'featured_journals': w.config['featured_journals'],
        'journals': [{'name': j['name'], 'short': j['short'], 'issns': j['issns']} for j in w.config['journals']],
        'coverage': compact_coverage, 'candidate_count': candidate_count,
        'screening_counts': dict(counts), 'published_count': sum(p['publication_status']=='published' for p in papers),
        'accepted_count': sum(p['publication_status']=='accepted' for p in papers),
        'candidate_inventory_complete': coverage.get('selected_journal_inventory_complete', coverage.get('nine_journal_inventory_complete', False)),
        'metadata_reconciliation_complete': coverage.get('selected_journal_reconciliation_complete', coverage.get('nine_journal_reconciliation_complete', False)),
        'limitations': (['September 2026 trial, not a current 90-day feed.',
            'Nature Communications directory pagination remains unstable; complete publisher coverage is not established.']
            if legacy else ['Fixed date-window trial, not a current 90-day feed.',
                            'Coverage flags preserve source-relative enumeration limits.'])+ [
            f'{candidate_count} fixed candidates assessed; {counts["review"]} unresolved and {deferred} unassessed.',
            'Assistant screening from explicit abstracts/excerpts or authorized online short comments, plus explicit user scope decisions; not full-text expert review.',
            'Author names are supplemented from matched Crossref metadata or explicit official accepted-page bylines; no authors inferred.'], 'papers': papers}
    if isinstance(w, PublicationView):
        snapshot['assessment_sources'] = w.manifest
    extra_evidence = publication_evidence(w)
    if extra_evidence:
        snapshot['publication_evidence'] = extra_evidence
    audit = {k: snapshot[k] for k in ['generated_at', 'window_start', 'window_end', 'screening_version',
        'config_sha256', 'current_rule_sha256', 'screening_log_sha256', 'reading_notes_sha256',
        'author_metadata_sha256', 'author_available_count',
        'screening_counts', 'candidate_count', 'published_count', 'accepted_count',
        'candidate_inventory_complete', 'metadata_reconciliation_complete', 'limitations']}
    if isinstance(w, PublicationView):
        audit['assessment_sources'] = w.manifest
    if extra_evidence:
        audit['publication_evidence'] = extra_evidence
    audit['included_assessments'] = [{k: p[k] for k in ['doi', 'scope_class', 'publication_status',
        'assessment_sha256', 'input_sha256', 'material_sha256', 'review_evidence_kind', 'review_evidence_sha256', 'rule_sha256', 'scope_authority', 'author_metadata_status', 'author_metadata_sha256']} for p in papers]
    status = {'attempted_at': generated_at, 'ok': True, 'operation': 'publish_existing_reviewed_snapshot',
        'new_collection_performed': False, 'candidate_inventory_complete': snapshot['candidate_inventory_complete'],
        'metadata_reconciliation_complete': snapshot['metadata_reconciliation_complete'],
        'pending_material': counts['review'], 'deferred_unassessed': deferred}
    return {'papers.json': snapshot, 'screening-report.json': audit, 'status.json': status}


def selected_runs(selection):
    paths = json.loads(Path(selection).read_text(encoding='utf-8'))['runs']
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('Release requires distinct, explicitly selected runs')
    runs = [(ROOT/p).resolve() for p in paths]
    for path in runs:
        if not path.is_relative_to((ROOT/'reports').resolve()) or path == (ROOT/'reports').resolve():
            raise ValueError('Release run must be a directory under reports')
    if len(runs) != len(set(runs)):
        raise ValueError('Duplicate resolved run path')
    return runs


def build_release(runs):
    if not runs or len(runs) != len({Path(p).resolve() for p in runs}):
        raise ValueError('Select distinct runs')
    if len(runs) == 1:
        return build_snapshot(runs[0])
    notes = json.loads((ROOT/'config/publication-notes.json').read_text(encoding='utf-8'))
    display = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
    papers, candidates, coverage, inputs = {}, {}, {}, []
    coverage_parts = {}
    windows = []
    for run in runs:
        w = publication_workflow(run)
        current_window = (w.pool['window_start'], w.pool['window_end'])
        windows.append(current_window)
        latest = {d['doi']: d for d in w.assessments()}
        own = {doi for doi, d in latest.items() if d['category'] in {'core', 'transferable_application'}}
        if not own <= set(notes['papers']):
            raise ValueError('Missing reading note for selected inclusion')
        scoped = {**notes, 'papers': {doi: notes['papers'][doi] for doi in sorted(own)}}
        part = build_snapshot(run, scoped)['papers.json']
        for doi, record in w.records.items():
            if record['window_membership'] != 'in_window':
                continue
            value = {'record': record, 'decision': latest[doi]}
            if doi in candidates and candidates[doi] != value:
                raise ValueError('Conflicting candidate/assessment across runs: '+doi)
            candidates[doi] = value
        for paper in part['papers']:
            doi = paper['doi']
            if doi in papers and papers[doi] != paper:
                raise ValueError('Conflicting inclusion across runs: '+doi)
            papers[doi] = paper
        for c in part['coverage']:
            dois = {doi for doi, r in w.records.items() if r['journal'] == c['journal'] and r['window_membership'] == 'in_window'}
            previous = coverage_parts.setdefault(c['journal'], {}).get(current_window)
            if previous is not None and previous != (c, dois):
                raise ValueError('Conflicting journal coverage across runs: '+c['journal'])
            coverage_parts[c['journal']][current_window] = (c, dois)
        input_manifest = w.manifest_path if isinstance(w, PublicationView) else w.out/'inputs/manifest.json'
        inputs.append({'run': w.out.relative_to(ROOT).as_posix(), 'config_sha256': part['config_sha256'],
                       'window_start': current_window[0], 'window_end': current_window[1],
                       'rule_sha256': w.rule_sha, 'screening_log_sha256': w.log.head,
                       'candidate_sha256': w.input_sha, 'author_metadata_sha256': part['author_metadata_sha256'],
                       'run_manifest_sha256': hashlib.sha256(input_manifest.read_bytes()).hexdigest(),
                       **({'assessment_sources': w.manifest} if isinstance(w, PublicationView) else {}),
                       **({'publication_evidence': part['publication_evidence']} if 'publication_evidence' in part else {}),
                       'candidate_inventory_complete': part['candidate_inventory_complete'],
                       'metadata_reconciliation_complete': part['metadata_reconciliation_complete']})
    window = (min(v[0] for v in windows), max(v[1] for v in windows))
    merged_coverage = merge_coverage(coverage_parts)
    # Every displayed journal must span the advertised range, without an uncollected gap.
    for c in merged_coverage:
        if (c['windows'][0]['window_start'], c['windows'][-1]['window_end']) != window:
            raise ValueError('Journal coverage does not span the release window: '+c['journal'])
    coverage = {c['journal']: c for c in merged_coverage}
    if set(notes['papers']) != set(papers):
        raise ValueError('Notes must match exactly the selected release inclusion union')
    journals = {j['short']: j for j in display['journals']}
    used = {v['record']['journal'] for v in candidates.values()} | set(coverage)
    if not used <= set(journals):
        raise ValueError('Selected release journal missing from display whitelist')
    for p in papers.values():
        j = journals[p['journal_short']]
        if not set(p['issns']) & set(j['issns']) or p['journal'] != j['name']:
            raise ValueError('Display journal conflicts with frozen identity')
        p['featured'] = j['short'] if j['short'] in display['featured_journals'] else None
        p['retrieved_by'] = ['Explicitly selected journal inventories; DOI-bound reviewed evidence']
    rows = sorted(papers.values(), key=lambda p: (p['date'], p['doi']), reverse=True)
    counts = Counter(v['decision']['category'] for v in candidates.values())
    counts.update({'review': 0, 'deferred_unassessed': 0, 'included': len(rows)})
    generated = now()
    complete = all(i['candidate_inventory_complete'] for i in inputs)
    reconciled = all(i['metadata_reconciliation_complete'] for i in inputs)
    snapshot = {'generated_at': generated, 'window_start': window[0], 'window_end': window[1],
        'window_days': (date.fromisoformat(window[1])-date.fromisoformat(window[0])).days+1,
        'release_kind': 'reviewed_multi_run_snapshot', 'screening_version': VERSION,
        'config_sha256': digest(display), 'current_rule_sha256': None,
        'screening_log_sha256': None, 'reading_notes_sha256': digest(notes),
        'author_metadata_sha256': digest([i['author_metadata_sha256'] for i in inputs]),
        'run_inputs': inputs, 'author_available_count': sum(p['author_metadata_status']=='available' for p in rows),
        'source': 'Explicit journal inventory runs and traced screening decisions',
        'categories': notes['categories'], 'featured_journals': display['featured_journals'],
        'journals': [{k: j[k] for k in ['name','short','issns']} for j in display['journals'] if j['short'] in used],
        'coverage': list(coverage.values()), 'candidate_count': len(candidates), 'screening_counts': dict(counts),
        'published_count': sum(p['publication_status']=='published' for p in rows),
        'accepted_count': sum(p['publication_status']=='accepted' for p in rows),
        'candidate_inventory_complete': complete, 'metadata_reconciliation_complete': reconciled,
        'limitations': ['Fixed date-window trial, not a current 90-day feed.',
            'Coverage flags preserve original source-relative enumeration limits; separately pinned supplemental evidence is retained in run_inputs.',
            'Assistant screening of authorized evidence and explicit user decisions; not full-text expert review.'],
        'papers': rows}
    audit = {k:v for k,v in snapshot.items() if k not in {'papers','categories','journals','coverage','featured_journals','source'}}
    audit['included_assessments'] = [{k:p[k] for k in ['doi','scope_class','publication_status',
        'assessment_sha256','input_sha256','material_sha256','review_evidence_kind','review_evidence_sha256',
        'rule_sha256','scope_authority','author_metadata_status','author_metadata_sha256']} for p in rows]
    status = {'attempted_at': generated, 'ok': True, 'operation': 'publish_existing_reviewed_snapshot',
        'new_collection_performed': False, 'candidate_inventory_complete': complete,
        'metadata_reconciliation_complete': reconciled, 'pending_material': 0, 'deferred_unassessed': 0}
    return {'papers.json': snapshot, 'screening-report.json': audit, 'status.json': status}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='site/data')
    parser.add_argument('--release', default='config/release.json', help='Explicit list of completed run directories')
    parser.add_argument('--check', action='store_true', help='Verify public snapshot matches the audited inputs without rewriting it')
    args = parser.parse_args()
    artifacts = build_release(selected_runs(ROOT/args.release))
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
            (target/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
        print('Exported '+str(len(artifacts['papers.json']['papers']))+' reviewed papers.')

if __name__ == '__main__':
    main()
