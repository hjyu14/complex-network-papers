"""Read-only, explicitly pinned adjudication references; never manufacture reviews."""
import json
from pathlib import Path
from collections import Counter
import screen_candidates as screen
from collect_candidates import EventLog
from run_inputs import digest
from report_io import file_sha, read_reference, checked_path


def publication_metadata_reference(out):
    """Pin JSON values, not platform-dependent historical line endings."""
    return {name:digest(json.loads((out/name).read_text(encoding='utf8'))) for name in
            ['author-metadata.json','publication-evidence.json'] if (out/name).exists()}


def verify_original(w):
    if w.active() or not w.log.events:
        raise ValueError('Source run is active or uninitialized')
    closed = {e['data']['batch_id'] for e in w.log.events if e['kind'] == 'supplement_batch_closed'}
    if any(e['data']['batch_id'] not in closed for e in w.log.events if e['kind'] == 'supplement_batch_started'):
        raise ValueError('Source supplement batch must be closed')
    for name, expected in w.log.events[0]['data']['original_sha256'].items():
        if file_sha(w.out/name) != expected:
            raise ValueError('Original collection file changed: '+name)


def source_reference(w):
    if isinstance(w, PublicationView):
        files = ['release-view.json', 'publication-log.jsonl', 'author-metadata.json']
        if (w.out/'publication-evidence.json').exists():
            files.append('publication-evidence.json')
        return {'run': w.out.relative_to(screen.ROOT).as_posix(),
                'files': {name: file_sha(w.out/name) for name in files},
                'candidate_sha256': w.input_sha, 'rule_sha256': w.rule_sha,
                'screening_log_sha256': w.log.head}
    files = ['candidates.json', 'coverage.json', 'collection-log.jsonl',
             'screening-log.jsonl', 'inputs/manifest.json', 'inputs/sources.json',
             'inputs/screening-protocol.md']
    if (w.out/'parent-manifest.json').exists():
        files.append('parent-manifest.json')
    return {'run': w.out.relative_to(screen.ROOT).as_posix(),
            'files': {name: file_sha(w.out/name) for name in files},
            'candidate_sha256': w.input_sha, 'rule_sha256': w.rule_sha,
            'screening_log_sha256': w.log.head}


class PublicationView:
    def __init__(self, out, _seen=()):
        self.out = Path(out).resolve()
        if self.out in _seen:
            raise ValueError('Cyclic publication source reference')
        _seen = (*_seen, self.out)
        self.manifest_path = self.out/'release-view.json'
        self.manifest = json.loads(self.manifest_path.read_text(encoding='utf8'))
        if self.manifest['version'] == 'editorial-revision-publication-view-1':
            self._init_revision(_seen)
            return
        if self.manifest['version'] != 'adjudicated-publication-view-1':
            raise ValueError('Unknown publication view version')
        sources = []
        for ref in [self.manifest['parent'], self.manifest['adjudication']]:
            path = (screen.ROOT/ref['run']).resolve()
            if not path.is_relative_to((screen.ROOT/'reports').resolve()) or path == self.out:
                raise ValueError('Invalid publication source path')
            w = screen.Workflow(path)
            verify_original(w)
            if source_reference(w) != ref:
                raise ValueError('Pinned publication source changed')
            sources.append(w)
        parent, child = self.sources = sources
        self.config, self.pool, self.records = parent.config, parent.pool, parent.records
        self.input_sha, self.rule_sha = parent.input_sha, parent.rule_sha
        if (parent.pool['window_start'], parent.pool['window_end']) != (child.pool['window_start'], child.pool['window_end']):
            raise ValueError('Adjudication window mismatch')
        pm = json.loads((child.out/'parent-manifest.json').read_text(encoding='utf8'))
        if pm['parent_run'] != self.manifest['parent']['run'] or pm['parent_log_head'] != parent.log.head or pm['parent_candidate_sha256'] != parent.input_sha:
            raise ValueError('Adjudication parent mismatch')
        old = {d['doi']: d for d in parent.assessments()}
        new = {d['doi']: d for d in child.assessments()}
        targets = {t['doi']: t for t in pm['targets']}
        unresolved = {doi for doi, d in old.items() if d['category'] == 'review'}
        if len(targets) != len(pm['targets']) or set(targets) != unresolved or set(child.records) != unresolved or set(new) != unresolved:
            raise ValueError('Adjudication must resolve exactly the parent review set')
        for doi in unresolved:
            t, d = targets[doi], new[doi]
            if child.records[doi] != parent.records[doi] or d['category'] not in {'core', 'transferable_application', 'excluded'}:
                raise ValueError('Adjudication record mismatch or unresolved verdict')
            if t['previous_assessment_sha256'] != digest(old[doi]) or t['previous_input_sha256'] != old[doi]['input_sha256'] or d['previous_assessment_sha256'] != digest(old[doi]) or d['previous_input_sha256'] != old[doi]['input_sha256']:
                raise ValueError('Adjudication does not bind the previous assessment')
        self.latest = {**old, **new}
        for source in sources:
            for d in source.assessments():
                r = source.records[d['doi']]
                if d['rule_sha256'] != source.rule_sha or d['input_sha256'] != digest({'record': r, 'material_sha256': d['material_sha256'], 'hard_checks': d['hard_checks'], 'rule_sha256': d['rule_sha256']}):
                    raise ValueError('Source assessment input mismatch')
                if d.get('candidate_sha256', source.input_sha) != source.input_sha or d.get('record_sha256', digest(r)) != digest(r):
                    raise ValueError('Source assessment inventory binding mismatch')
        if parent.status()['not_assessed'] or child.status()['not_assessed']:
            raise ValueError('Publication source has unassessed records')
        self.log = EventLog(self.out/'publication-log.jsonl')
        if not self.log.events or self.log.events[0]['kind'] != 'publication_view_started' or self.log.events[0]['data']['manifest_sha256'] != digest(self.manifest):
            raise ValueError('Publication view lacks manifest audit binding')

    def assessments(self):
        return list(self.latest.values())

    def active(self):
        return None

    def status(self):
        return {'not_assessed': 0, 'deferred_unassessed': 0,
                'categories': dict(Counter(d['category'] for d in self.assessments()))}

    @property
    def evidence_events(self):
        return [e for w in self.sources for e in
                (w.evidence_events if isinstance(w, PublicationView) else w.log.events)]

    def candidate_binding(self, decision):
        if self.manifest['version'] == 'editorial-revision-publication-view-1':
            if decision['doi'] in self.revised_dois:
                return self.sources[1].input_sha
            parent = self.sources[0]
            return parent.candidate_binding(decision) if isinstance(parent, PublicationView) else parent.input_sha
        return self.input_sha

    def _init_revision(self, seen):
        sources = []
        for ref in [self.manifest['parent'], self.manifest['adjudication']]:
            path = (screen.ROOT/ref['run']).resolve()
            if not path.is_relative_to((screen.ROOT/'reports').resolve()) or path == self.out:
                raise ValueError('Invalid publication source path')
            w = publication_workflow(path, seen)
            if not isinstance(w, PublicationView):
                verify_original(w)
            if source_reference(w) != ref:
                raise ValueError('Pinned publication source changed')
            sources.append(w)
        parent, child = self.sources = sources
        if isinstance(child, PublicationView):
            raise ValueError('Revision assessments require a frozen screening run')
        expected_metadata = publication_metadata_reference(parent.out)
        if (self.manifest.get('parent_publication_hash_basis') != 'canonical_json'
                or self.manifest.get('parent_publication_files') != expected_metadata):
            raise ValueError('Pinned parent publication metadata changed')
        self.config, self.pool, self.records = parent.config, parent.pool, parent.records
        self.input_sha, self.rule_sha = parent.input_sha, parent.rule_sha
        if (parent.pool['window_start'], parent.pool['window_end']) != (child.pool['window_start'], child.pool['window_end']):
            raise ValueError('Revision window mismatch')
        old = {d['doi']: d for d in parent.assessments()}
        new = {d['doi']: d for d in child.assessments()}
        targets = {t['doi']: t for t in self.manifest['targets']}
        relevant = set(child.records) & set(parent.records)
        if not relevant or len(targets) != len(self.manifest['targets']) or set(targets) != relevant or not relevant <= set(new):
            raise ValueError('Revision must bind exactly its explicit parent target set')
        for source in sources:
            if source.status()['not_assessed'] or source.status()['deferred_unassessed'] or any(d['category']=='review' for d in source.assessments()):
                raise ValueError('Revision source is unresolved')
            if not isinstance(source, PublicationView):
                historical_rules = {source.rule_sha, source.log.events[0]['data']['rule_sha256']}
                for event in source.log.events:
                    if event['kind'] == 'rules_revised':
                        historical_rules.update([event['data']['rule_sha256'], event['data']['previous_rule_sha256']])
                for d in source.assessments():
                    r = source.records[d['doi']]
                    if d['rule_sha256'] not in historical_rules or d['input_sha256'] != digest({
                            'record': r, 'material_sha256': d['material_sha256'],
                            'hard_checks': d['hard_checks'], 'rule_sha256': d['rule_sha256']}):
                        raise ValueError('Source assessment input mismatch')
        for d in child.assessments():
            r = child.records[d['doi']]
            if (d['rule_sha256'] != child.rule_sha or d.get('candidate_sha256') != child.input_sha
                    or d.get('record_sha256') != digest(r)
                    or d['input_sha256'] != digest({'record': r, 'material_sha256': d['material_sha256'],
                        'hard_checks': d['hard_checks'], 'rule_sha256': child.rule_sha})):
                raise ValueError('Revision assessment input or inventory binding mismatch')
        for doi in relevant:
            t, d = targets[doi], new[doi]
            if child.records[doi] != parent.records[doi] or d['category'] not in {'core','transferable_application','excluded'}:
                raise ValueError('Revision record mismatch or unresolved verdict')
            if (t['previous_assessment_sha256'] != digest(old[doi]) or t['previous_input_sha256'] != old[doi]['input_sha256']
                    or d.get('previous_assessment_sha256') != digest(old[doi]) or d.get('previous_input_sha256') != old[doi]['input_sha256']):
                raise ValueError('Revision does not bind the previous assessment')
            verdict = next((e['data'] for e in child.log.events if e['kind']=='user_editorial_verdict'
                and digest(e['data']) == d.get('editorial_basis',{}).get('verdict_sha256')), None)
            if (not verdict or verdict.get('authority') != 'human user in current conversation'
                    or verdict.get('statement_kind') not in {'explicit_individual_verdict','explicit_group_verdict'}
                    or not verdict.get('user_statement') or verdict.get('doi') != doi
                    or verdict.get('title') != child.records[doi]['title']
                    or verdict.get('record_sha256') != digest(child.records[doi])
                    or verdict.get('candidate_sha256') != child.input_sha
                    or verdict.get('verdict') != ('include' if d['category'] in {'core','transferable_application'} else 'exclude')):
                raise ValueError('Revision lacks an explicit bound user verdict')
        self.revised_dois = relevant
        self.latest = {**old, **{doi:new[doi] for doi in relevant}}
        self.log = EventLog(self.out/'publication-log.jsonl')
        if not self.log.events or self.log.events[0]['kind'] != 'publication_view_started':
            raise ValueError('Publication view lacks manifest audit binding')
        manifest_hash = self.log.events[0]['data']['manifest_sha256']
        for event in self.log.events:
            if event['kind'] == 'publication_view_manifest_revised':
                revision = event['data']
                if revision.get('previous_manifest_sha256') != manifest_hash or not revision.get('reason'):
                    raise ValueError('Publication manifest revision chain mismatch')
                manifest_hash = revision['manifest_sha256']
        if manifest_hash != digest(self.manifest):
            raise ValueError('Publication view lacks manifest audit binding')


def publication_workflow(out, _seen=()):
    if (Path(out)/'publication.json').exists():
        return FlatPublicationView(out)
    if (Path(out)/'release-view.json').exists():
        return PublicationView(out, _seen)
    return screen.Workflow(out)


def verify_assessments(w):
    """Check historical rule/input bindings without reinterpreting old decisions."""
    verify_original(w)
    if w.status()['not_assessed'] or w.status()['deferred_unassessed']:
        raise ValueError('Source has unassessed records')
    rules = {w.rule_sha, w.log.events[0]['data']['rule_sha256']}
    for e in w.log.events:
        if e['kind'] == 'rules_revised':
            rules.update([e['data']['rule_sha256'], e['data']['previous_rule_sha256']])
    for d in w.assessments():
        r = w.records[d['doi']]
        if (d['rule_sha256'] not in rules or d['input_sha256'] != digest({
                'record':r, 'material_sha256':d['material_sha256'],
                'hard_checks':d['hard_checks'], 'rule_sha256':d['rule_sha256']})
                or d.get('record_sha256', digest(r)) != digest(r)
                or d.get('candidate_sha256', w.input_sha) != w.input_sha):
            raise ValueError('Source assessment input mismatch')


class FlatPublicationView(PublicationView):
    """One inventory plus an explicit ordered list of bound amendments, never nested views."""
    def __init__(self, out):
        self.out = Path(out).resolve()
        self.manifest_path = self.out/'publication.json'
        self.manifest = json.loads(self.manifest_path.read_text(encoding='utf8'))
        if self.manifest['version'] != 'flat-publication-1':
            raise ValueError('Unknown flat publication version')
        base = screen.Workflow(self.out)
        verify_assessments(base)
        if source_reference(base) != self.manifest['inventory']:
            raise ValueError('Pinned inventory changed')
        self.sources = [base]
        self.config, self.pool, self.records = base.config, base.pool, base.records
        self.input_sha, self.rule_sha, self.log = base.input_sha, base.rule_sha, base.log
        self.latest = {d['doi']:d for d in base.assessments()}
        self.bindings = {digest(e['data']):base.input_sha for e in base.log.events
                         if e['kind'] in {'assessment','assessment_corrected'}}
        seen = {self.out}
        for stage in self.manifest['revisions']:
            ref = stage['source']
            path = checked_path(screen.ROOT/'reports', Path(ref['run']).relative_to('reports'))
            if path in seen or (path/'publication.json').exists() or (path/'release-view.json').exists():
                raise ValueError('Revisions must reference distinct direct review runs')
            seen.add(path)
            child = screen.Workflow(path)
            verify_assessments(child)
            if source_reference(child) != ref or child.rule_sha != child.log.events[0]['data']['rule_sha256']:
                raise ValueError('Pinned review changed')
            if (child.pool['window_start'],child.pool['window_end']) != (self.pool['window_start'],self.pool['window_end']):
                raise ValueError('Revision window mismatch')
            new = {d['doi']:d for d in child.assessments()}
            relevant = set(child.records) & set(self.records)
            targets = {t['doi']:t for t in stage['targets']}
            if not relevant or len(targets)!=len(stage['targets']) or set(targets)!=relevant:
                raise ValueError('Revision target set mismatch')
            if stage['mode']=='resolve_pending':
                pending = {doi for doi,d in self.latest.items() if d['category']=='review'}
                if relevant != pending or set(child.records)!=pending:
                    raise ValueError('Pending adjudication must resolve exactly the unresolved set')
            elif stage['mode']!='explicit_revision':
                raise ValueError('Unknown amendment mode')
            for doi in relevant:
                d, old, t = new[doi], self.latest[doi], targets[doi]
                if child.records[doi]!=self.records[doi] or d['category'] not in {'core','transferable_application','excluded'}:
                    raise ValueError('Changed candidate or unresolved revision')
                for key,expected in [('previous_assessment_sha256',digest(old)),('previous_input_sha256',old['input_sha256'])]:
                    if d.get(key)!=expected or t.get(key)!=expected:
                        raise ValueError('Revision does not bind the previous assessment')
                if stage['mode']=='explicit_revision':
                    verdict=next((e['data'] for e in child.log.events if e['kind']=='user_editorial_verdict'
                        and digest(e['data'])==d.get('editorial_basis',{}).get('verdict_sha256')),None)
                    if (not verdict or verdict.get('authority')!='human user in current conversation'
                            or verdict.get('statement_kind') not in {'explicit_individual_verdict','explicit_group_verdict'}
                            or not verdict.get('user_statement') or verdict.get('doi')!=doi
                            or verdict.get('title')!=self.records[doi]['title']
                            or verdict.get('record_sha256')!=digest(self.records[doi])
                            or verdict.get('candidate_sha256')!=child.input_sha
                            or verdict.get('verdict')!=('exclude' if d['category']=='excluded' else 'include')):
                        raise ValueError('Revision lacks an explicit bound user verdict')
                self.latest[doi]=d
            self.sources.append(child)
            self.bindings.update({digest(e['data']):child.input_sha for e in child.log.events
                                 if e['kind'] in {'assessment','assessment_corrected'}})
        if any(d['category']=='review' for d in self.latest.values()):
            raise ValueError('Publication still has unresolved records')
        authors=self.manifest['authors']
        if authors['file']!='author-metadata.json':
            raise ValueError('Author metadata must use the canonical run filename')
        self.author_events=EventLog.from_bytes(read_reference(authors['audit'],screen.ROOT)).events
        metadata=json.loads((self.out/authors['file']).read_text(encoding='utf8'))
        if (digest(metadata)!=authors['metadata_sha256'] or not any(
                e['kind']=='author_metadata_completed' and e['data']['metadata_sha256']==digest(metadata)
                for e in self.author_events)):
            raise ValueError('Author metadata lacks matching audit evidence')

    def candidate_binding(self, decision):
        try:
            return self.bindings[digest(decision)]
        except KeyError:
            raise ValueError('Assessment is absent from the explicit source history') from None

    def evidence_path(self, relative):
        return checked_path(self.out, self.manifest.get('evidence_paths',{}).get(relative,relative))


def publisher_url(record, decision):
    check = decision['hard_checks']['date']
    accepted = check.get('publication_status') == 'accepted' or check.get('basis', '').startswith('publisher.accepted')
    if accepted:
        urls = [p['article_url'] for p in record.get('publisher_records', [])
                if p.get('article_url') and p.get('publication_status') == 'accepted']
        url = check.get('source_url') or (urls[0] if urls else decision['material_source'])
        if not url.startswith('https://journals.aps.org/'):
            raise ValueError('Accepted-paper link must reference verified official publisher metadata')
        return url
    return 'https://doi.org/'+record['doi']
