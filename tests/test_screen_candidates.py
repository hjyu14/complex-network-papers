"""Offline checks for evidence identity, cache integrity and one-paper gate."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import screen_candidates as s


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.r = {'doi': '10.1/example', 'title': 'A study', 'issns': ['0000-0001']}
        self.m = {**self.r, 'source_url': 'https://example.org/article',
                  'retrieved_at': '2026-10-03T00:00:00Z', 'abstract_basis': 'crossref.abstract',
                  'abstract': 'An explicit abstract.', 'abstract_sha256': s.sha('An explicit abstract.')}

    def test_identity_and_hash(self):
        s.validate_material(self.m, self.r)
        for k, v in [('doi', '10.1/wrong'), ('issns', []), ('abstract', 'Corrupted'),
                     ('abstract_basis', 'description'), ('source_url', 'https://x.org/?token=secret')]:
            with self.subTest(k=k), self.assertRaises(ValueError):
                s.validate_material({**self.m, k: v}, self.r)

    def test_inverted_index(self):
        self.assertEqual(s.rebuild_abstract({'one': [0, 2], 'two': [1]}), 'one two one')
        for bad in [{'a': [0], 'b': [0]}, {'a': [1]}, {'a': [-1]}]:
            with self.assertRaises(ValueError):
                s.rebuild_abstract(bad)

    def test_audience_marker_is_not_an_abstract(self):
        for text in ['International audience', 'Data supplement for the publication "Example".']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                s.validate_material({**self.m, 'abstract': text,
                                     'abstract_sha256': s.sha(text)}, self.r)

    def test_parser_does_not_capture_body_or_description(self):
        parser = s.AbstractParser()
        parser.feed('<meta name="description" content="Not an abstract"><p>Body</p>'
                    '<section data-title="Abstract"><h2>Abstract</h2><p>Actual abstract.</p></section>'
                    '<section><p>Full article.</p></section>')
        self.assertEqual(parser.material('https://x.org/a')['abstract'], 'Actual abstract.')

    def test_aps_accepted_identity_requires_visible_evidence(self):
        html = ('<head><title>Physical Review X - Accepted Paper: A study</title></head>'
                '<h1>Physical Review X</h1><h1>A study</h1>'
                '<p>DOI: https://doi.org/10.1103/example</p>'
                '<section id="abstract-section"><h2>Abstract</h2><p>Actual abstract.</p></section>'
                '<p>Unrelated body must not be retained.</p><footer>ISSN 2160-3308 (online)</footer>')
        url = 'https://journals.aps.org/prx/accepted/10.1103/example'
        parser = s.AbstractParser()
        parser.feed(html)
        m = parser.material(url)
        self.assertEqual((m['doi'], m['title'], m['issns'], m['abstract']),
                         ('10.1103/example', 'A study', ['2160-3308'], 'Actual abstract.'))
        bad = s.AbstractParser()
        bad.feed(html.replace('DOI: https://doi.org/10.1103/example', 'No labelled DOI'))
        self.assertEqual(bad.material(url)['doi'], '')

    def test_gate_resume_and_public_abstract_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root/'reports'
            out.mkdir()
            (root/'docs').mkdir()
            (root/'config').mkdir()
            (root/'docs/screening-protocol.md').write_text('rules')
            (root/'config/sources.json').write_text('{}')
            rs = [{**self.r, 'date': '2026-09-01', 'date_basis': 'published-online',
                   'issues': [], 'journal': 'J', 'window_membership': 'in_window'},
                  {**self.r, 'doi': '10.1/second', 'date': '2026-09-02',
                   'date_basis': 'published-online', 'issues': [], 'journal': 'J',
                   'window_membership': 'in_window'}]
            (out/'candidates.json').write_text(json.dumps({'records': rs}))
            with patch.object(s, 'ROOT', root), patch.object(s, 'PRIVATE', root/'.private/abstract-cache/v9'):
                w = s.Workflow(out)
                w.log.add('run_started', {'candidate_sha256': w.input_sha, 'rule_sha256': w.rule_sha,
                          'batch_dois': [r['doi'] for r in rs]})
                w.next()
                w.cache(self.m)
                self.assertEqual(s.Workflow(out).next()['doi'], self.r['doi'])
                with self.assertRaises(ValueError):
                    w.batch(1)
                path = next((root/'.private/abstract-cache/v9').rglob('*.json'))
                path.write_text(json.dumps({**self.m, 'abstract': 'corrupted'}))
                with self.assertRaises(ValueError):
                    w.current_material()
                path.write_text(json.dumps(self.m))
                d = {'doi': self.r['doi'], 'category': 'excluded', 'reviewer': 'test',
                     'reason': 'Routine domain study', 'evidence_summary': 'Domain result.',
                     'hard_checks': {k: {'status': 'verified'} for k in ['identity', 'type', 'date']}}
                with self.assertRaises(ValueError):
                    w.decide({**d, 'evidence_summary': self.m['abstract']})
                w.decide(d)
                self.assertNotIn(self.m['abstract'], (out/'screening-log.jsonl').read_text())
                with self.assertRaises(ValueError):
                    w.batch(1)
                w.correct_check(self.r['doi'], 'date', {'status': 'unresolved', 'value': None},
                                'Source date semantics remain unresolved')
                self.assertEqual(w.status()['assessed'], 1)
                restored = s.Workflow(out).assessments()[0]
                self.assertEqual(restored['hard_checks']['date']['status'], 'unresolved')
                self.assertNotEqual(restored['input_sha256'], restored['previous_input_sha256'])
                self.assertEqual(w.next()['doi'], '10.1/second')

    def test_parallel_collection_defers_without_assessing_and_preserves_batch_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root/'reports'
            out.mkdir()
            (root/'docs').mkdir()
            (root/'config').mkdir()
            (root/'docs/screening-protocol.md').write_text('rules')
            (root/'config/sources.json').write_text(json.dumps({'journals': [{'short': 'J'}]}))
            base = {**self.r, 'date': '2026-09-01', 'date_basis': 'published-online',
                    'issues': [], 'journal': 'J', 'window_membership': 'in_window'}
            rs = [base, {**base, 'doi': '10.1/failure'},
                  {**base, 'doi': '10.1/news', 'publisher_records': [{'article_type': 'News'}]}]
            (out/'candidates.json').write_text(json.dumps({'records': rs}))

            def collect(w):
                if w.active() == '10.1/failure':
                    raise ValueError('Synthetic source failure')
                w.cache(self.m)

            with patch.object(s, 'ROOT', root), patch.object(s, 'PRIVATE', root/'.private/abstract-cache/v9'):
                w = s.Workflow(out)
                w.log.add('run_started', {'candidate_sha256': w.input_sha, 'rule_sha256': w.rule_sha,
                          'batch_dois': [r['doi'] for r in rs]})
                with patch.object(s.Workflow, 'fetch_active', collect):
                    result = w.collect_batch(2)
                self.assertEqual(result['results'], {'abstract_ready': 1, 'deferred': 1, 'type_evidence_ready': 1})
                self.assertEqual(w.status()['assessed'], 0)
                self.assertEqual(w.status()['not_assessed'], 3)
                self.assertEqual(w.status()['deferred_unassessed'], 1)
                with self.assertRaises(ValueError):
                    w.batch(1)
                self.assertEqual(s.Workflow(out).next()['doi'], self.r['doi'])
                w = s.Workflow(out)
                d = {'doi': self.r['doi'], 'category': 'excluded', 'reviewer': 'test',
                     'reason': 'Domain result', 'evidence_summary': 'Domain evidence.',
                     'hard_checks': {k: {'status': 'verified'} for k in ['identity', 'type', 'date']}}
                w.decide(d)
                self.assertEqual(w.next()['doi'], '10.1/news')
                w.decide({**d, 'doi': '10.1/news', 'exclusion_basis': 'publisher_non_target_type'})
                self.assertTrue(w.next()['batch_complete'])
                restored = s.Workflow(out)
                self.assertEqual(restored.status()['assessed'], 2)
                self.assertEqual(restored.status()['not_assessed'], 1)
                self.assertNotIn(self.m['abstract'], (out/'screening-log.jsonl').read_text())

    def test_fresh_network_bypasses_cache_and_429_stops_later_channels(self):
        w = object.__new__(s.Workflow)
        w.records = {self.r['doi']: self.r}
        w.collection_doi = self.r['doi']
        w.log = s.BufferedLog([])
        w.fresh_network = True
        w.request_stop = threading.Event()
        w.current_material = lambda: None
        w.next = lambda: {}
        error = HTTPError('https://api.crossref.org/works/example', 429, 'Rate limited', {}, None)
        with patch.object(Path, 'glob', side_effect=AssertionError('Must not read local cache')), \
                patch.object(s, 'urlopen', side_effect=error) as request:
            w.fetch_active()
        self.assertTrue(w.request_stop.is_set())
        self.assertEqual(request.call_count, 1)
        attempts = [e['data'] for e in w.log.events if e['kind'] == 'source_attempt']
        self.assertEqual([a['channel'] for a in attempts], ['cache', 'crossref'])
        self.assertEqual(attempts[0]['result'], 'benchmark_bypass')
        self.assertEqual(attempts[1]['http_status'], 429)

    def test_rate_limit_does_not_submit_remaining_batch_or_claim_absence(self):
        w = object.__new__(s.Workflow)
        records = [{**self.r, 'doi': f'10.1/paper-{i}', 'window_membership': 'in_window'}
                   for i in range(3)]
        w.records = {r['doi']: r for r in records}
        w.log = s.BufferedLog([])
        w.log.add('batch_selected', {'batch_dois': list(w.records)})
        called = []
        def limited(job):
            called.append(job.active())
            job.request_stop.set()
        with patch.object(s.Workflow, 'fetch_active', limited):
            result = w.collect_batch(1)
        self.assertEqual(called, [records[0]['doi']])
        self.assertEqual(result['results'], {'deferred_rate_limit': 1, 'not_started_rate_limit': 2})
        self.assertFalse(any(e['kind'] == 'assessment' for e in w.log.events))
        deferred = [e['data'] for e in w.log.events if e['kind'] == 'material_deferred']
        self.assertEqual(len(deferred), 3)
        self.assertTrue(all(d['subject_scope_status'] == 'not_assessed' for d in deferred))

    def test_shared_crossref_gate_limits_overlap_and_records_service_headers(self):
        gate = threading.Lock()
        schedule = {'last_started': 0.0}
        state = {'active': 0, 'peak': 0}
        workers = []
        class Response:
            status = 200
            headers = {'x-api-pool': 'public', 'x-concurrency-limit': '1'}
            def __init__(response, request):
                response.url = request.full_url
            def __enter__(response):
                state['active'] += 1
                state['peak'] = max(state['peak'], state['active'])
                return response
            def read(response, limit):
                time.sleep(.015)
                doi = unquote(response.url.rsplit('/', 1)[-1])
                return json.dumps({'message': {'DOI': doi, 'title': ['A study'],
                                  'ISSN': ['0000-0001'], 'abstract': 'An explicit abstract.'}}).encode()
            def __exit__(response, *args):
                state['active'] -= 1
        for i in range(2):
            w = object.__new__(s.Workflow)
            doi = f'10.1/gate-{i}'
            w.records = {doi: {**self.r, 'doi': doi}}
            w.collection_doi = doi
            w.log = s.BufferedLog([])
            w.crossref_gate, w.crossref_schedule = gate, schedule
            w.request_stop = threading.Event()
            w.current_material = lambda: None
            w.cache = lambda material: None
            w.next = lambda: {}
            w.attempt('cache', None, 'missing')
            workers.append(w)
        with patch.object(s, 'urlopen', side_effect=lambda request, **kw: Response(request)):
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(lambda w: w.fetch('crossref'), workers))
        self.assertEqual(state['peak'], 1)
        self.assertTrue(all(w.log.events[-1]['data']['request_limits']['x-concurrency-limit'] == '1'
                            for w in workers))


if __name__ == '__main__':
    unittest.main()
