"""Trace daily overlap candidates to effective history; never classify scientific content."""
import argparse
from collections import Counter
import json
from pathlib import Path
from collect_candidates import normalized_title
from publication_view import publication_workflow, verify_assessments
from report_io import file_sha, run_directory
from screen_candidates import Workflow, digest, ROOT


def publication_status(decision):
    check = decision['hard_checks']['date']
    return check.get('publication_status') or ('accepted' if check.get('basis','').startswith('publisher.accepted') else 'published')


def compare_history(records, decisions, history, authorized_start, authorized_end, identity_notes=None):
    rows, blockers = [], []
    identity_notes = identity_notes or {}
    for doi, record in sorted(records.items()):
        if not doi:
            blockers.append({'doi':doi,'reason':'Unresolved DOI identity'}); continue
        inside = record['window_membership'] == 'in_window'
        if not inside and not (record.get('date') and authorized_start <= record['date'] <= authorized_end):
            rows.append({'doi':doi,'history_status':'outside_authorized_dates'}); continue
        previous, current = history.get(doi), decisions.get(doi)
        row = {'doi':doi,'window_membership':record['window_membership'],
               'record_sha256':digest(record),'date':record.get('date'),
               'history_status':'assessed' if previous else 'missing_history'}
        if previous:
            old_record, old = previous['record'], previous['decision']
            row.update(previous_run=previous['run'],previous_record_sha256=digest(old_record),
                       previous_assessment_sha256=digest(old),previous_input_sha256=old['input_sha256'],
                       previous_category=old['category'],previous_publication_status=publication_status(old))
            if old['category'] == 'review':
                blockers.append({'doi':doi,'reason':'Historical assessment unresolved'})
            if record['journal'] != old_record['journal'] or not set(record['issns']) & set(old_record['issns']):
                blockers.append({'doi':doi,'reason':'Historical journal identity mismatch'})
            if normalized_title(record['title']) != normalized_title(old_record['title']):
                note = identity_notes.get(doi)
                if (not note or note.get('record_sha256') != digest(record)
                        or note.get('previous_record_sha256') != digest(old_record) or not note.get('reason')):
                    blockers.append({'doi':doi,'reason':'Title change needs explicit identity review'})
                else:
                    row['identity_review'] = note
        if inside:
            if not current or current['category'] == 'review':
                blockers.append({'doi':doi,'reason':'Current candidate needs actual resolved review'})
            else:
                row.update(assessment_sha256=digest(current),input_sha256=current['input_sha256'],
                           category=current['category'],publication_status=publication_status(current))
                if previous:
                    row['publication_status_changed'] = row['publication_status'] != row['previous_publication_status']
                    if previous['decision']['category'] != current['category']:
                        blockers.append({'doi':doi,'reason':'Scientific category change needs explicit revision'})
        elif not previous:
            blockers.append({'doi':doi,'reason':'Out-of-window candidate has no effective historical assessment'})
        rows.append(row)
    return rows, blockers


def build_audit(current, previous_runs, *, _memo=None):
    memo = {} if _memo is None else _memo
    verify_assessments(current)
    history, refs, windows = {}, {}, {}
    for index, path in enumerate(previous_runs):
        old = publication_workflow(path)
        relative = old.out.relative_to(ROOT).as_posix()
        if old.out == current.out or not (old.out/'publication.json').exists():
            raise ValueError('History requires distinct sealed publication sources')
        refs[relative] = file_sha(old.out/'publication.json')
        prior_audit = load_audit(old, previous_runs[:index], _memo=memo)
        replacements = {r['doi']:r for r in prior_audit['records'] if r.get('assessment_sha256') and r['history_status']=='assessed'} if prior_audit else {}
        for journal in old.config['journals']:
            windows.setdefault(journal['short'], []).append([old.pool['window_start'],old.pool['window_end']])
        for d in old.assessments():
            entry = {'run':relative,'record':old.records[d['doi']],'decision':d}
            if d['doi'] in history and (history[d['doi']]['record'] != entry['record'] or history[d['doi']]['decision'] != d):
                target = replacements.get(d['doi'])
                if (not target or target['previous_run'] != history[d['doi']]['run']
                        or target['previous_assessment_sha256'] != digest(history[d['doi']]['decision'])
                        or target['assessment_sha256'] != digest(d)):
                    raise ValueError('History contains unresolved duplicate DOI conflict')
            history[d['doi']] = entry
    coverage = json.loads((current.out/'coverage.json').read_text(encoding='utf8'))
    notes = {e['data']['doi']:e['data'] for e in current.log.events if e['kind']=='carryover_identity_reviewed'}
    rows, blockers = compare_history(current.records,{d['doi']:d for d in current.assessments()},history,
                                    min(v[0] for ws in windows.values() for v in ws),current.pool['window_end'],notes)
    selected_journals = {j['short'] for j in current.config['journals']}
    for doi, previous in history.items():
        record = previous['record']
        if (record['journal'] in selected_journals and publication_status(previous['decision'])=='published'
                and current.pool['window_start'] <= (previous['decision']['hard_checks']['date'].get('value') or '') <= current.pool['window_end']
                and doi not in current.records):
            blockers.append({'doi':doi,'reason':'Previously published overlap DOI absent from current full inventory'})
    for journal in current.config['journals']:
        short = journal['short']
        cutoff = max((v[1] for v in windows.get(short,[])), default=None)
        if not cutoff or not current.pool['window_start'] <= cutoff <= current.pool['window_end']:
            blockers.append({'journal':short,'reason':'Overlap must scan previous cutoff through current cutoff'})
        if not coverage['journals'][short]['candidate_inventory_complete']:
            blockers.append({'journal':short,'reason':'Incomplete current journal inventory'})
    return {'version':'daily-carryover-audit-1','current_run':current.out.relative_to(ROOT).as_posix(),
            'candidate_sha256':current.input_sha,'rule_sha256':current.rule_sha,
            'previous_publications':refs,'previous_windows':windows,
            'window_start':current.pool['window_start'],'window_end':current.pool['window_end'],
            'records':rows,'blockers':blockers,
            'counts':{'in_window':sum(r.get('window_membership')=='in_window' for r in rows),
                'newly_reviewed':sum(r.get('window_membership')=='in_window' and r['history_status']=='missing_history' for r in rows),
                'historically_reviewed':sum(r['history_status']=='assessed' for r in rows),
                'state_updates':sum(r.get('publication_status_changed',False) for r in rows),
                'categories':dict(Counter(d['category'] for d in current.assessments()))},
            'limitations':['Coverage ends at recorded source retrieval times; short overlap does not guarantee detection of arbitrarily old backfills.']}


def load_audit(w, previous_runs, *, _memo=None):
    memo = {} if _memo is None else _memo
    ref = w.manifest.get('carryover_audit')
    if not ref:
        return None
    if ref['file'] != 'evidence/cross-run-audit.json' or file_sha(w.out/ref['file']) != ref['sha256']:
        raise ValueError('Carryover audit file binding mismatch')
    key = (w.out, ref['sha256'], tuple(Path(p).resolve() for p in previous_runs))
    if key in memo:
        return memo[key]
    saved = json.loads((w.out/ref['file']).read_text(encoding='utf8'))
    if saved != build_audit(w.sources[0], previous_runs, _memo=memo) or saved['blockers']:
        raise ValueError('Carryover audit is stale or blocked')
    if not any(e['kind']=='carryover_audit_completed' and e['data'].get('audit_sha256')==digest(saved) for e in w.log.events):
        raise ValueError('Carryover audit lacks log binding')
    memo[key] = saved
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--release',default='config/release.json',type=Path)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    out = run_directory(args.run, ROOT, writable=not args.check)
    selection = json.loads((ROOT/args.release).read_text(encoding='utf8'))
    previous = [ROOT/p for p in selection['runs'] if (ROOT/p).resolve()!=out]
    w = Workflow(out)
    audit = build_audit(w,previous)
    if audit['blockers']:
        raise ValueError(json.dumps(audit['blockers'],ensure_ascii=False))
    path = out/'evidence/cross-run-audit.json'
    if args.check:
        if json.loads(path.read_text(encoding='utf8')) != audit:
            raise ValueError('Saved carryover audit is stale')
    else:
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            raise ValueError('Audit exists; use --check or explicitly preserve a revision')
        path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
        w.log.add('carryover_audit_completed',{'file':'evidence/cross-run-audit.json','audit_sha256':digest(audit),
                  'file_sha256':file_sha(path),'counts':audit['counts']})
    print(json.dumps(audit['counts'],ensure_ascii=False))


if __name__=='__main__':
    main()
