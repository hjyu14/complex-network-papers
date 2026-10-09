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
from run_inputs import freeze_inputs


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

    def test_missing_abstract_cannot_become_type_exclusion(self):
        decision = {'category':'excluded','hard_checks':{'type':{'status':'verified','value':'Correction'}}}
        with self.assertRaises(ValueError):
            s.validate_non_target_type(self.r, [], decision)
        events = [{'kind':'publisher_type_observed','data':{'doi':self.r['doi'],'article_type':'Correction'}}]
        s.validate_non_target_type(self.r, events, decision)
        for typ in ['Letter','Commentary',None]:
            record = {**self.r,'publisher_records':[{'article_type':typ}]}
            with self.subTest(typ=typ),self.assertRaises(ValueError):
                s.validate_non_target_type(record, [], decision)

    def test_inverted_index(self):
        self.assertEqual(s.rebuild_abstract({'one': [0, 2], 'two': [1]}), 'one two one')
        for bad in [{'a': [0], 'b': [0]}, {'a': [1]}, {'a': [-1]}]:
            with self.assertRaises(ValueError):
                s.rebuild_abstract(bad)

    def test_non_target_section_mapping_requires_bound_review_and_preserves_conflicts(self):
        record = {**self.r, 'publisher_records':[{'article_type':'Inner Workings'}]}
        decision = {'category':'excluded','hard_checks':{'type':{'status':'verified','value':'News Feature'}}}
        mapping = {'doi':record['doi'],'official_type':'Inner Workings','article_type':'News Feature',
                   'record_sha256':s.digest(record),'reason':'Official journalist-written science feature',
                   'reviewer':'Actual reviewer','source_url':'https://example.org/article'}
        with self.assertRaises(ValueError):
            s.validate_non_target_type(record, [], decision)
        events = [{'kind':'publisher_type_mapping_reviewed','data':mapping}]
        s.validate_non_target_type(record, events, decision)
        for key,value in [('record_sha256','wrong'),('reason',''),('article_type','Article')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                s.validate_non_target_type(record,[{'kind':events[0]['kind'],'data':{**mapping,key:value}}],decision)
        conflicting = {**record,'publisher_records':record['publisher_records']+[{'article_type':'Article'}]}
        with self.assertRaises(ValueError):
            s.validate_non_target_type(conflicting,[{'kind':events[0]['kind'],'data':{**mapping,'record_sha256':s.digest(conflicting)}}],decision)

    def test_official_news_section_names_remain_type_exclusions(self):
        for typ in ['Muse', 'Technology Feature', 'This Week In Pnas']:
            decision = {'category':'excluded','hard_checks':{'type':{'status':'verified','value':typ}}}
            record = {**self.r,'publisher_records':[{'article_type':typ}]}
            s.validate_non_target_type(record, [], decision)
            # A conflicting official research label still requires resolution.
            record['publisher_records'].append({'article_type':'Article'})
            with self.assertRaises(ValueError):
                s.validate_non_target_type(record, [], decision)

    def test_brief_communication_still_requires_actual_bound_reading(self):
        record = {**self.r,'journal':'Test journal'}
        observation = {**record,'source_url':'https://example.org/communication',
            'article_type':'BriefCommunication','explicit_abstract_absent':True,
            'identity_verified':True,'full_visible_comment_read':True}
        observation['evidence_sha256'] = s.digest(observation)
        decision = {'sources':[observation['source_url']], 'hard_checks':{
            'identity':{'evidence_sha256':observation['evidence_sha256']},
            'type':{'value':'BriefCommunication'}}}
        s.validate_short_comment_review(observation, record, decision)
        for changes in [{'full_visible_comment_read':False},{'identity_verified':False},
                        {'explicit_abstract_absent':False}]:
            changed = {**observation,**changes};changed.pop('evidence_sha256')
            changed['evidence_sha256'] = s.digest(changed)
            bound = {**decision,'hard_checks':{**decision['hard_checks'],
                'identity':{'evidence_sha256':changed['evidence_sha256']}}}
            with self.assertRaises(ValueError):
                s.validate_short_comment_review(changed, record, bound)

    def test_policy_article_exception_is_one_authorized_exclusion(self):
        record = {**self.r, 'doi':'10.1126/science.aef7249', 'journal':'Science'}
        observation = {**record, 'source_url':'https://www.science.org/doi/10.1126/science.aef7249',
            'article_type':'Policy Article', 'explicit_abstract_absent':True,
            'identity_verified':True, 'full_visible_comment_read':True,
            'user_authorization':'允许这篇例外审读', 'authorization_source':'user_message'}
        def check(obs, rec, category):
            obs = dict(obs); obs.pop('evidence_sha256', None)
            obs['evidence_sha256'] = s.digest(obs)
            decision = {'category':category, 'sources':[obs['source_url']], 'hard_checks':{
                'identity':{'evidence_sha256':obs['evidence_sha256']}, 'type':{'value':'Policy Article'}}}
            s.validate_short_comment_review(obs, rec, decision)
        check(observation, record, 'excluded')
        for category in ['core', 'transferable_application']:
            with self.assertRaises(ValueError):
                check(observation, record, category)
        with self.assertRaises(ValueError):
            check({**observation, 'user_authorization':''}, record, 'excluded')
        other = {**record, 'doi':'10.1126/science.other'}
        with self.assertRaises(ValueError):
            check({**observation, 'doi':other['doi']}, other, 'excluded')

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

    def test_aps_footer_identity_and_clean_abstract(self):
        html = ('<meta name="citation_doi" content="10.1103/example">'
                '<meta name="citation_title" content="A study">'
                '<meta name="citation_journal_title" content="Physical Review Letters">'
                '<h1>A study</h1><p>DOI: 10.1103/example</p>'
                '<section id="abstract-section"><h2>Abstract</h2>'
                '<div id="abstract-section-content"><p>Actual abstract.</p><ul><li>PHYSH inner label</li></ul></div>'
                '<div class="figure-band">View figure</div><dialog>Close Next</dialog>'
                '<ul><li>PHYSH label</li></ul></section><footer>ISSN 1079-7114</footer>')
        parser = s.AbstractParser(); parser.feed(html)
        m = parser.material('https://journals.aps.org/prl/abstract/10.1103/example')
        self.assertEqual(m['abstract'], 'Actual abstract.')
        self.assertEqual(m['issns'], ['1079-7114'])
        for bad in [html.replace('Physical Review Letters', 'Wrong journal'),
                    html.replace('DOI: 10.1103/example', 'DOI: 10.1103/wrong'),
                    html.replace('<h1>A study</h1>', '<h1>Wrong title</h1>')]:
            parser = s.AbstractParser(); parser.feed(bad)
            self.assertEqual(parser.material('https://journals.aps.org/prl/abstract/10.1103/example')['issns'], [])

    def test_aps_accepted_math_uses_primary_h1_without_loosening_candidate_match(self):
        parser=s.AbstractParser()
        parser.feed('<head><title>Physical Review Letters - Accepted Paper: Material BiFeO</title></head>'
                    '<h1>Physical Review Letters</h1><h1>Material BiFeO3</h1>'
                    '<p>DOI: 10.1103/math</p><section id="abstract-section"><p>Actual abstract.</p></section>'
                    '<footer>ISSN 1079-7114</footer>')
        m=parser.material('https://journals.aps.org/prl/accepted/10.1103/math')
        self.assertEqual(m['title'],'Material BiFeO3')
        with self.assertRaises(ValueError):
            s.validate_identity(m,{'doi':'10.1103/math','title':'Different material','issns':['1079-7114']})

    def test_expansion_aps_journals_use_same_strict_identity_gate(self):
        for slug, journal, issn in [('pre', 'Physical Review E', '2470-0053'),
                                    ('prresearch', 'Physical Review Research', '2643-1564')]:
            html = (f'<head><title>{journal} - Accepted Paper: A study</title></head>'
                    f'<h1>{journal}</h1><h1>A study</h1><p>DOI: 10.1103/example</p>'
                    f'<section id="abstract-section"><p>Explicit abstract.</p></section><footer>ISSN {issn}</footer>')
            parser = s.AbstractParser(); parser.feed(html)
            m = parser.material(f'https://journals.aps.org/{slug}/accepted/10.1103/example')
            self.assertEqual((m['doi'], m['title'], m['issns']), ('10.1103/example', 'A study', [issn]))
            bad = s.AbstractParser(); bad.feed(html.replace('DOI: 10.1103/example', 'DOI: 10.1103/wrong'))
            self.assertEqual(bad.material(f'https://journals.aps.org/{slug}/accepted/10.1103/example')['doi'], '')
            regular = s.AbstractParser()
            regular.feed(f'<meta name="citation_doi" content="10.1103/example">'
                         f'<meta name="citation_title" content="A study">'
                         f'<meta name="citation_journal_title" content="{journal}">'
                         f'<h1>A study</h1><p>DOI: 10.1103/example</p><footer>ISSN {issn}</footer>')
            self.assertEqual(regular.material(f'https://journals.aps.org/{slug}/abstract/10.1103/example')['issns'], [issn])

    def test_gate_resume_and_public_abstract_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root/'reports'
            out.mkdir()
            (root/'docs').mkdir()
            (root/'config').mkdir()
            (root/'docs/screening-protocol.md').write_text('rules')
            (root/'config/sources.json').write_text(json.dumps({'journals':[{'short':'J'}], 'screening_protocol':'docs/screening-protocol.md', 'initial_trial':{'start':'2026-09-01','end':'2026-09-30'}}))
            rs = [{**self.r, 'date': '2026-09-01', 'date_basis': 'published-online',
                   'issues': [], 'journal': 'J', 'window_membership': 'in_window'},
                  {**self.r, 'doi': '10.1/second', 'date': '2026-09-02',
                   'date_basis': 'published-online', 'issues': [], 'journal': 'J',
                   'window_membership': 'in_window'}]
            (out/'candidates.json').write_text(json.dumps({'window_start':'2026-09-01','window_end':'2026-09-30','records': rs}))
            freeze_inputs(out,root)
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
            (root/'config/sources.json').write_text(json.dumps({'journals': [{'short': 'J'}], 'screening_protocol':'docs/screening-protocol.md', 'initial_trial':{'start':'2026-09-01','end':'2026-09-30'}}))
            base = {**self.r, 'date': '2026-09-01', 'date_basis': 'published-online',
                    'issues': [], 'journal': 'J', 'window_membership': 'in_window'}
            rs = [base, {**base, 'doi': '10.1/failure'},
                  {**base, 'doi': '10.1/news', 'publisher_records': [{'article_type': 'News'}]}]
            (out/'candidates.json').write_text(json.dumps({'window_start':'2026-09-01','window_end':'2026-09-30','records': rs}))
            freeze_inputs(out,root)

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
                w.decide({**d, 'doi': '10.1/news', 'exclusion_basis': 'publisher_non_target_type',
                          'hard_checks': {**d['hard_checks'], 'type': {'status':'verified','value':'News'}}})
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


    def test_short_comment_requires_bound_identity_source_and_type(self):
        r = {**self.r, 'journal': 'Test journal'}
        obs = {**r, 'source_url': 'https://example.org/comment', 'article_type': 'Commentary',
               'explicit_abstract_absent': True, 'identity_verified': True,
               'full_visible_comment_read': True}
        def check(change=None, bound=True):
            o = {**obs, **(change or {})}; o['evidence_sha256'] = s.digest(o)
            w = object.__new__(s.Workflow); w.records = {r['doi']: r}
            w.collection_doi = r['doi']; w.log = s.BufferedLog([])
            w.log.add('short_comment_reviewed', o)
            w.current_material = lambda: None; w.status = lambda: {}
            w.rule_sha = 'rule'; w.input_sha = 'input'
            d = {'doi': r['doi'], 'category': 'excluded', 'reason': 'Domain argument.',
                 'evidence_summary': 'Domain argument.', 'reviewer': 'actual reviewer',
                 'sources': [obs['source_url']], 'hard_checks': {
                     'identity': {'status': 'verified', 'evidence_sha256': o['evidence_sha256'] if bound else 'wrong'},
                     'type': {'status': 'verified', 'value': 'Commentary'},
                     'date': {'status': 'not_required_for_scope_exclusion'}}}
            w.decide(d); return w.log.events[-1]['data']
        result = check()
        self.assertIsNone(result['material_sha256'])
        self.assertIn('short comment', result['review_basis'])
        for change in [{'title': 'Other paper'}, {'journal': 'Other journal'}, {'issns': []},
                       {'source_url': 'https://other.org/comment'}, {'article_type': 'Article'},
                       {'full_visible_comment_read': False}]:
            with self.subTest(change=change), self.assertRaises(ValueError): check(change)
        with self.assertRaises(ValueError): check(bound=False)

    def test_author_abstract_exception_cannot_expand_to_other_records(self):
        r = {**self.r, 'doi': '10.1103/lvpn-gblk'}
        authors = [f'Author {i}' for i in range(13)]
        link = {'official_source_url': 'https://journals.aps.org/prl/accepted/10.1103/lvpn-gblk',
                'source_title': r['title'], 'official_authors': authors,
                'source_authors': authors, 'authorized_use': 'scope_exclusion_only'}
        m = {**self.m, 'doi': r['doi'], 'source_url': 'https://arxiv.org/abs/2609.09615v1',
             'abstract_basis': 'arxiv.Abstract/user_authorized_single_record', 'identity_link': link}
        s.validate_material(m, r)
        for changed in [{**m, 'source_url': 'https://arxiv.org/abs/other'},
                        {**m, 'identity_link': {**link, 'source_authors': authors[:-1]}}]:
            with self.assertRaises(ValueError): s.validate_material(changed, r)
        with self.assertRaises(ValueError):
            s.validate_material({**m, 'doi': self.r['doi']}, self.r)


if __name__ == '__main__':
    unittest.main()
