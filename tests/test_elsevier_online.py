"""First online day, not issue/acceptance, must govern Elsevier inclusion."""
from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_candidates import EventLog, digest, reconcile, inventory_summary
from import_elsevier_directory import normalize
from online_date import validate_online_check


JOURNAL = {'name': 'Chaos, Solitons & Fractals', 'short': 'CSF', 'issns': ['0960-0779'],
    'collection': {'family': 'elsevier', 'date_policy': 'publisher.available_online',
        'pii_prefix': 'S09600779', 'max_pages': 100, 'article_lookups': 1000,
        'url': 'https://www.sciencedirect.com/journal/chaos-solitons-and-fractals'}}
DOI = '10.1016/j.chaos.synthetic'
ARTICLE = {'doi': DOI, 'title': 'Synthetic research', 'journal': JOURNAL['name'],
    'issn': '0960-0779', 'available_online': '2026-09-28', 'date_label': 'Available online',
    'publication_version': 'Journal Pre-proof', 'retrieved_at': '2026-10-08T09:00:00Z',
    'url': 'https://www.sciencedirect.com/science/article/pii/S0960077926000000'}


def bundle():
    return {'version': 'elsevier-browser-bibliography-1', 'journal': 'CSF',
        'window_start': '2026-09-01', 'window_end': '2026-10-08', 'articles': [deepcopy(ARTICLE)],
        'pages': [{'url': JOURNAL['collection']['url']+'/vol/200/suppl/C',
            'retrieved_at': '2026-10-08T09:00:00Z', 'journal': JOURNAL['name'], 'all_types': True,
            'records': [{'doi': DOI, 'title': ARTICLE['title'], 'article_url': ARTICLE['url'],
                         'article_type': 'Research article'}], 'next_url': None}]}


def rows(official, item=None):
    item = item or {'DOI': DOI, 'title': [ARTICLE['title']], 'ISSN': JOURNAL['issns'],
                   'published-print': {'date-parts': [[2026, 12]]}}
    crossref = {DOI: [{'metadata': item, 'metadata_sha256': digest(item)}]}
    class NoNetwork:
        def get(self, url): raise AssertionError('Unexpected request')
    with TemporaryDirectory() as tmp:
        return reconcile(crossref, [official], JOURNAL, '2026-09-01', '2026-10-08',
                         '2026-10-08', NoNetwork(), EventLog(Path(tmp)/'log.jsonl'))


class OnlineDateTests(unittest.TestCase):
    def test_issue_month_outside_window_does_not_hide_preproof(self):
        official = normalize(bundle(), JOURNAL, '2026-09-01', '2026-10-08')
        result = rows(official)[0]
        self.assertEqual(result['date'], '2026-09-28')
        self.assertEqual(result['window_membership'], 'in_window')
        self.assertEqual(result['publication_status'], 'published')
        self.assertEqual(result['publication_version'], 'Journal Pre-proof')
        self.assertNotIn('incomplete_preferred_date', result['issues'])
        self.assertFalse(inventory_summary([result], official['complete'])['candidate_inventory_complete'])

    def test_missing_official_day_never_falls_back_to_crossref(self):
        item = {'DOI': DOI, 'title': [ARTICLE['title']], 'ISSN': JOURNAL['issns'],
                'published-online': {'date-parts': [[2026, 9, 28]]}}
        result = rows({'records': []}, item)[0]
        self.assertIsNone(result['date'])
        self.assertEqual(result['window_membership'], 'unresolved')

    def test_official_outside_day_resolves_issue_month_discovery(self):
        data = bundle()
        data['articles'][0]['available_online'] = '2026-08-28'
        result = rows(normalize(data, JOURNAL, '2026-09-01', '2026-10-08'))[0]
        self.assertEqual(result['window_membership'], 'out_of_window')
        self.assertEqual(result['date'], '2026-08-28')

    def test_citation_online_meta_is_inventory_evidence_not_inclusion_history(self):
        data = bundle()
        data['articles'][0].update(date_label='citation_online_date', publication_version=None)
        result = rows(normalize(data, JOURNAL, '2026-09-01', '2026-10-08'))[0]
        self.assertEqual(result['window_membership'], 'in_window')
        with self.assertRaises(ValueError):
            validate_online_check(result, JOURNAL, {'status': 'verified',
                'basis': 'publisher.available_online', 'publication_status': 'published',
                'value': result['date'], 'observation_sha256': digest(data['articles'][0])})

    def test_first_online_binding_rejects_acceptance_and_vor_day(self):
        result = rows(normalize(bundle(), JOURNAL, '2026-09-01', '2026-10-08'))[0]
        check = {'status': 'verified', 'basis': 'publisher.available_online',
                 'publication_status': 'published', 'value': ARTICLE['available_online'],
                 'observation_sha256': digest(ARTICLE)}
        self.assertEqual(validate_online_check(result, JOURNAL, check), ARTICLE)
        for change in [{'basis': 'publisher.accepted'}, {'publication_status': 'accepted'},
                       {'value': '2026-10-01'}, {'observation_sha256': 'wrong'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_online_check(result, JOURNAL, {**check, **change})

    def test_same_doi_final_version_preserves_first_online_day(self):
        data = bundle(); data['articles'][0]['publication_version'] = 'Version of Record'
        final = rows(normalize(data, JOURNAL, '2026-09-01', '2026-10-08'))
        self.assertEqual(len(final), 1)
        self.assertEqual(final[0]['date'], ARTICLE['available_online'])

    def test_reject_x_wrong_identity_and_abstract_input(self):
        for change in [{'url': 'https://www.sciencedirect.com/science/article/pii/S2590054426000000'},
                       {'date_label': 'Accepted'}, {'journal': JOURNAL['name']+': X'},
                       {'retrieved_at': '2026-10-08T09:00:00'}, {'abstract': 'Not allowed'}]:
            data = bundle(); data['articles'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize(data, JOURNAL, '2026-09-01', '2026-10-08')

    def test_official_only_identity_and_partial_directory_survive(self):
        data = bundle(); data['articles'] = []
        partial = normalize(data, JOURNAL, '2026-09-01', '2026-10-08')
        self.assertFalse(partial['complete'])
        self.assertIsNone(partial['records'][0]['date'])
        official = normalize(bundle(), JOURNAL, '2026-09-01', '2026-10-08')
        class NoNetwork:
            def get(self, url): raise AssertionError('Unexpected request')
        with TemporaryDirectory() as tmp:
            result = reconcile({}, [official], JOURNAL, '2026-09-01', '2026-10-08',
                '2026-10-08', NoNetwork(), EventLog(Path(tmp)/'log.jsonl'))[0]
        self.assertTrue(result['identity_verified'])
        self.assertEqual(result['window_membership'], 'in_window')

    def test_conflicting_duplicate_and_first_online_observations_remain_blocked(self):
        data = bundle(); second = deepcopy(data['pages'][0])
        second['records'][0]['title'] = 'Conflicting title'
        data['pages'].append(second)
        with self.assertRaises(ValueError):
            normalize(data, JOURNAL, '2026-09-01', '2026-10-08')
        official = normalize(bundle(), JOURNAL, '2026-09-01', '2026-10-08')
        second = deepcopy(official['records'][0])
        second['date'] = '2026-09-29'
        second['publisher_date_observation']['available_online'] = second['date']
        official['records'].append(second)
        result = rows(official)[0]
        self.assertIsNone(result['date'])
        self.assertEqual(result['window_membership'], 'unresolved')

    def test_legacy_journal_without_collection_is_unaffected(self):
        self.assertIsNone(validate_online_check({}, {'name': 'Legacy fixture'}, {}))


if __name__ == '__main__':
    unittest.main()
