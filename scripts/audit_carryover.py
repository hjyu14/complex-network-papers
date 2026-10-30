"""Trace daily overlap candidates to effective history; never classify scientific content."""
import argparse
from collections import Counter
import json
from pathlib import Path
from collect_candidates import normalized_title
from publication_view import publication_workflow, verify_assessments
from report_io import file_sha, run_directory, checked_path
from screen_candidates import Workflow, digest, ROOT


def publication_status(decision):
    check = decision['hard_checks']['date']
    return check.get('publication_status') or ('accepted' if check.get('basis','').startswith('publisher.accepted') else 'published')


def compare_history(records, decisions, history, authorized_start, authorized_end, identity_notes=None, revisions=None):
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
            note = identity_notes.get(doi)
            if normalized_title(record['title']) != normalized_title(old_record['title']):
                if (not note or note.get('record_sha256') != digest(record)
                        or note.get('previous_record_sha256') != digest(old_record) or not note.get('reason')):
                    blockers.append({'doi':doi,'reason':'Title change needs explicit identity review'})
                else:
                    row['identity_review'] = note
            elif (note and note.get('record_sha256') == digest(record)
                    and note.get('previous_record_sha256') == digest(old_record)
                    and note.get('reason')):
                # Preserve a previously recorded identity review when a later,
                # presentation-only title normalizer recognizes the same pair.
                # Published carryover audits are immutable evidence.
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
                        revision = (revisions or {}).get(doi)
                        if revision:
                            row['editorial_revision'] = revision
                        else:
                            blockers.append({'doi':doi,'reason':'Scientific category change needs explicit revision'})
        elif not previous:
            blockers.append({'doi':doi,'reason':'Out-of-window candidate has no effective historical assessment'})
        rows.append(row)
    return rows, blockers


def editorial_revisions(current, history):
    """Validate explicit cross-run adjudications without changing sealed sources."""
    result = {}
    decisions = {d['doi']:d for d in current.assessments()}
    for event in current.log.events:
        if event['kind'] != 'carryover_editorial_revision_selected':
            continue
        ref = event['data']
        path = checked_path(ROOT, ref['path'])
        if (not path.is_relative_to((ROOT/'reports/reviews').resolve())
                or path.name != 'revision.json' or path.parent.name != 'evidence'
                or file_sha(path) != ref['sha256']):
            raise ValueError('Cross-run revision file binding mismatch')
        revision = json.loads(path.read_text(encoding='utf8'))
        doi = revision['doi']
        if doi in result or doi not in history or doi not in decisions:
            raise ValueError('Cross-run revision target mismatch')
        previous, decision, record = history[doi], decisions[doi], current.records[doi]
        delegated = revision.get('version') == 'cross-run-delegated-revision-1'
        expected = {
            'version':'cross-run-delegated-revision-1' if delegated else 'cross-run-editorial-revision-1', 'doi':doi,
            'previous_run':previous['run'],
            'previous_record_sha256':digest(previous['record']),
            'previous_assessment_sha256':digest(previous['decision']),
            'previous_input_sha256':previous['decision']['input_sha256'],
            'current_run':current.out.relative_to(ROOT).as_posix(),
            'record_sha256':digest(record), 'candidate_sha256':current.input_sha,
            'assessment_sha256':digest(decision), 'input_sha256':decision['input_sha256']}
        verdict = revision.get('user_verdict', {})
        bindings = {k:expected[k] for k in ['doi','previous_run','previous_assessment_sha256',
                    'previous_input_sha256','record_sha256','candidate_sha256']}
        bindings.update(title=record['title'], verdict='exclude' if decision['category']=='excluded' else 'include')
        if (any(revision.get(k)!=v for k,v in expected.items())
                or decision['category'] not in {'core','transferable_application','excluded'}
                or previous['decision']['category']==decision['category']
                or record['window_membership']!='in_window'):
            raise ValueError('Cross-run revision identity/assessment binding mismatch')
        if delegated:
            authorization = next((e['data'] for e in current.log.events
                if e['kind']=='user_delegated_adjudication'
                and digest(e['data'])==revision.get('authorization_sha256')), None)
            review = next((e['data'] for e in current.log.events
                if e['kind']=='delegated_scientific_decision'
                and digest(e['data'])==revision.get('delegated_decision_sha256')), None)
            review_bindings = {k:expected[k] for k in
                ['doi','record_sha256','candidate_sha256','assessment_sha256','input_sha256']}
            review_bindings.update(title=record['title'],category=decision['category'],
                material_sha256=decision.get('material_sha256'),rule_sha256=decision['rule_sha256'],
                authorization_sha256=revision.get('authorization_sha256'))
            if (not authorization or authorization.get('authority')!='human user in current conversation'
                    or authorization.get('statement_kind')!='explicit_delegation_to_primary_agent'
                    or not authorization.get('user_statement') or doi not in authorization.get('scope',[])
                    or not review or any(review.get(k)!=v for k,v in review_bindings.items())
                    or not review.get('reason') or not review.get('reviewer')
                    or not decision.get('material_sha256') or not decision.get('abstract_sha256')
                    or decision.get('exclusion_basis')=='user_editorial_decision'):
                raise ValueError('Cross-run delegated revision needs scoped user authorization and bound abstract assessment')
        elif (any(verdict.get(k)!=v for k,v in bindings.items())
                or verdict.get('authority')!='human user in current conversation'
                or verdict.get('statement_kind') not in {'explicit_individual_verdict','explicit_group_verdict'}
                or not verdict.get('user_statement')
                or revision.get('verdict_sha256')!=digest(verdict)
                or not any(e['kind']=='user_editorial_verdict' and e['data']==verdict for e in current.log.events)):
            raise ValueError('Cross-run revision lacks an explicit bound user verdict')
        result[doi] = ref
    return result


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
                                    min(v[0] for ws in windows.values() for v in ws),current.pool['window_end'],notes,
                                    editorial_revisions(current, history))
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
