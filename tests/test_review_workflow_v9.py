import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from review_workflow_v9 import Workflow
from review_fetch_v9 import publisher_extract, fetch
from review_routes_v9 import build


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ('config/screening-policy-v9.json','config/sources.json','docs/screening-protocol-v9.md'):
            p = self.root/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}', encoding='utf-8')
        self.routes = [dict(doi='10.1234/'+x, title='Synthetic '+x, routes=[
            dict(url='https://example.org/'+x,kind='crossref')]) for x in ('one','two')]
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self, doi, route):
        self.calls.append(doi)
        return dict(doi=doi, doi_match=True, title='Synthetic', source_url=route['url'],
                    retrieved_at='2026-10-02T00:00:00Z', abstract_basis='crossref.abstract'), 'Synthetic evidence for a study unrelated to network science.'

    def flow(self, fetcher=None):
        return Workflow(self.root, self.routes, fetcher or self.fetch)

    def assessment(self, state):
        return dict(doi=state['doi'], review_input_sha256=state['review_input_sha256'],
                    **{'class':'excluded'}, reason='Synthetic non-network subject.',
                    reviewer='test fixture, not an actual paper', evidence='unrelated to network science')

    def test_gate_restart_input_binding_and_no_public_abstract(self):
        flow = self.flow()
        first = flow.next()
        self.assertEqual(first['status'], 'awaiting_review')
        flow = self.flow()  # restart
        self.assertEqual(flow.next()['doi'], first['doi'])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(ValueError):
            flow.next('10.1234/two')
        with self.assertRaises(ValueError):
            flow.defer('Must not skip cached input')
        review = self.assessment(first)
        with self.assertRaises(ValueError):
            flow.submit(dict(review, review_input_sha256='wrong'))
        with self.assertRaises(ValueError):
            flow.submit(dict(review, evidence='invented phrase'))
        review['abstract'] = 'Must not copy this to ordinary reports.'
        saved = flow.submit(review)
        self.assertNotIn('abstract', saved)
        self.assertEqual(flow.next()['doi'], '10.1234/two')
        self.assertEqual(len(self.calls), 2)

    def test_failure_browser_handoff_and_resume(self):
        def failed(doi, route):
            raise ValueError('No explicit abstract')
        flow = self.flow(failed)
        self.assertEqual(flow.next()['status'], 'needs_browser_or_source_review')
        metadata, abstract = self.fetch('10.1234/one', {'url':'https://www.nature.com/articles/test'})
        metadata['abstract_basis'] = 'publisher.Abstract'
        self.assertEqual(flow.import_browser(metadata, abstract)['status'], 'awaiting_review')
        flow.submit(self.assessment(flow.state()))
        flow.next()
        saved = flow.defer('No explicit abstract after programmatic attempts; browser still needed.')
        self.assertFalse(saved['subject_scope_assessed'])
        self.assertEqual(saved['disposition'],'acquisition_unresolved')

    def test_publisher_type_exclusion_without_abstract(self):
        def failed(doi, route):
            raise ValueError('No independent abstract')
        flow = self.flow(failed)
        flow.next()
        evidence = dict(doi='10.1234/one', doi_match=True, title='Synthetic one',
                        source_url='https://www.nature.com/articles/test',
                        publisher_type='RESEARCH BRIEFINGS', retrieved_at='2026-10-02T00:00:00Z',
                        reviewer='test fixture', reason='Verified non-research briefing.')
        for changed in (dict(doi='10.1234/two'), dict(title='Wrong title'),
                        dict(publisher_type='Article'), dict(doi_match=False),
                        dict(source_url='https://example.org/article')):
            with self.assertRaises(ValueError):
                flow.exclude_publisher_type(dict(evidence, **changed))
        record = flow.exclude_publisher_type(evidence)
        self.assertEqual(record['class'], 'excluded')
        self.assertFalse(record['subject_scope_assessed'])
        self.assertNotIn('abstract', record)
        self.assertIsNone(flow.cache.get('10.1234/one'))
        self.assertEqual(flow.status()['acquisition_unresolved'], [])
        self.assertEqual(flow.next()['doi'], '10.1234/two')

    def test_reject_description_and_reference_doi(self):
        page = '<meta name="citation_doi" content="10.1234/one"><meta name="description" content="A long teaser is not an abstract.">'
        self.assertEqual(publisher_extract('10.1234/one', page)[1], '')
        with self.assertRaises(ValueError):
            publisher_extract('10.1234/one', '<a href="https://doi.org/10.1234/one">reference</a>')

    def test_aps_accepted_requires_matching_title_and_doi_path(self):
        page = '<h1 class="heading-lg-bold">Synthetic title</h1><p>Accepted Paper</p><section id="abstract-section">Abstract Synthetic contents.</section>'
        url = 'https://journals.aps.org/pre/accepted/10.1103/test'
        self.assertEqual(publisher_extract('10.1103/test', page, url, 'Synthetic title')[1], 'Synthetic contents.')
        with self.assertRaises(ValueError):
            publisher_extract('10.1103/test', page, url, 'Different title')
        with self.assertRaises(ValueError):
            publisher_extract('10.1103/wrong', page, url, 'Synthetic title')

    def test_api_adapters_identity_and_explicit_fields(self):
        doi = '10.1234/test'
        abstract = 'These synthetic words describe an abstract used only for testing the source adapters.'
        cases = {
            'crossref': {'message':{'DOI':doi,'title':['Synthetic'], 'abstract':abstract}},
            'europepmc': {'resultList':{'result':[{'doi':doi,'title':'Synthetic','abstractText':abstract}]}},
            'openalex': {'doi':'https://doi.org/'+doi,'title':'Synthetic','abstract_inverted_index':{w:[i] for i,w in enumerate(abstract.split())}},
        }
        for kind, payload in cases.items():
            with self.subTest(kind=kind), patch('review_fetch_v9.request', return_value=('https://example.org',json.dumps(payload))):
                meta, text = fetch(doi, {'kind':kind,'url':'https://example.org'})
                self.assertTrue(meta['doi_match'])
                self.assertEqual(text, abstract)
                with self.assertRaises(ValueError):
                    fetch('10.1234/wrong', {'kind':kind,'url':'https://example.org'})
        xml = '<PubmedArticleSet><PubmedArticle><ArticleId IdType="doi">'+doi+'</ArticleId><ArticleTitle>Synthetic</ArticleTitle><Abstract><AbstractText>'+abstract+'</AbstractText></Abstract></PubmedArticle></PubmedArticleSet>'
        with patch('review_fetch_v9.request', side_effect=[('https://example.org',json.dumps({'esearchresult':{'idlist':['123']}})),('https://example.org',xml)]):
            meta, text = fetch(doi, {'kind':'pubmed','url':'https://example.org'})
            self.assertEqual(text,abstract)

    def test_route_reconstruction_and_description_priority(self):
        trial = self.root/'reports/v9-2026-09'
        trial.mkdir(parents=True)
        def save(name, data):
            (trial/name).write_text(json.dumps(data), encoding='utf-8')
        doi = '10.1038/test'
        save('final-screening-progress-v1.json', {'results':[dict(doi=doi,decision='review',reason='pending')]})
        save('material-master-v4.json', {'results':[dict(doi=doi,title='Synthetic',retrieved_by=[],material={},initial_screening_record={'abstract_available':False})]})
        save('publisher-canonical-v2.json', {'results':[dict(doi=doi,abstract_available=True,sources=[dict(url='https://www.nature.com/articles/test?code=xyz',abstract_available=True)])]})
        save('openalex-fallback.json', {'results':[dict(doi=doi,abstract_available=True)]})
        result = build(trial)
        routes = result['records'][0]['routes']
        self.assertEqual(routes[0]['kind'], 'openalex')
        publisher = next(r for r in routes if r['kind']=='publisher')
        self.assertEqual(publisher['historical_basis'],'historical_description_or_abstract_unresolved')
        self.assertNotIn('?', publisher['url'])


if __name__ == '__main__':
    unittest.main()
