"""Read-only, explicitly pinned adjudication references; never manufacture reviews."""
import hashlib
import json
from pathlib import Path
from collections import Counter
import screen_candidates as screen
from collect_candidates import EventLog
from run_inputs import digest


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    def __init__(self, out):
        self.out = Path(out).resolve()
        self.manifest_path = self.out/'release-view.json'
        self.manifest = json.loads(self.manifest_path.read_text(encoding='utf8'))
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
        return [e for w in self.sources for e in w.log.events]


def publication_workflow(out):
    if (Path(out)/'release-view.json').exists():
        return PublicationView(out)
    return screen.Workflow(out)


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
