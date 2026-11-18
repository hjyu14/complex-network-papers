import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_carryover import compare_history
from publication_view import awaiting_aps_publication
from run_inputs import digest


class APSAcceptedDeferralTests(unittest.TestCase):
    def setUp(self):
        self.doi = '10.1103/test-1234'
        self.url = f'https://journals.aps.org/pre/accepted/{self.doi}'
        self.record = dict(doi=self.doi, title='Example', journal='PRE',
                           date='2026-11-17', publication_status='accepted',
                           window_membership='in_window', identity_verified=True,
                           publisher_records=[dict(article_url=self.url, publication_status='accepted')])
        self.observation = dict(doi=self.doi, channel='publisher', source_url=self.url,
                                result='no_explicit_abstract', http_status=200,
                                verified_metadata={'doi': self.doi})
        defer = dict(doi=self.doi, record_sha256=digest(self.record), candidate_sha256='inventory',
                     observation_sha256='observation', authorization='User rule adopted 2026-11-18')
        self.workflow = SimpleNamespace(
            assessments=lambda: [], records={self.doi: self.record}, input_sha='inventory',
            log=SimpleNamespace(events=[
                dict(kind='source_attempt', sha256='observation', data=self.observation),
                dict(kind='aps_accepted_awaiting_publication', sha256='deferral', data=defer)]))

    def test_missing_accepted_abstract_can_await_publication(self):
        waiting = awaiting_aps_publication(self.workflow)
        rows, blockers = compare_history(self.workflow.records, {}, {}, '2026-11-01',
                                         '2026-11-18', waiting=waiting)
        self.assertEqual(blockers, [])
        self.assertEqual(rows[0]['aps_deferral']['deferral_sha256'], 'deferral')
        self.assertNotIn('assessment_sha256', rows[0])

    def test_access_failure_and_cached_abstract_do_not_qualify(self):
        self.observation['http_status'] = 403
        with self.assertRaisesRegex(ValueError, 'Invalid APS accepted-paper deferral'):
            awaiting_aps_publication(self.workflow)
        self.observation['http_status'] = 200
        self.workflow.log.events.append(dict(kind='material_cached', data={'doi': self.doi}))
        with self.assertRaisesRegex(ValueError, 'Invalid APS accepted-paper deferral'):
            awaiting_aps_publication(self.workflow)

    def test_historical_deferral_does_not_waive_published_review(self):
        waiting = awaiting_aps_publication(self.workflow)
        record = dict(self.record, window_membership='out_of_window')
        _, blockers = compare_history({self.doi: record}, {}, {}, '2026-11-01',
                                      '2026-11-20', historical_waiting=waiting)
        self.assertEqual(blockers, [])
        record['publication_status'] = 'published'
        _, blockers = compare_history({self.doi: record}, {}, {}, '2026-11-01',
                                      '2026-11-20', historical_waiting=waiting)
        self.assertTrue(blockers)

    def test_still_accepted_previously_deferred_paper_cannot_be_assessed(self):
        waiting = awaiting_aps_publication(self.workflow)
        decision = dict(category='core', input_sha256='assessment-input',
                        hard_checks={'date': {'publication_status': 'accepted'}})
        _, blockers = compare_history(self.workflow.records, {self.doi: decision}, {},
                                      '2026-11-01', '2026-11-20', historical_waiting=waiting)
        self.assertEqual(len(blockers), 1)
        self.assertIn('formally published', blockers[0]['reason'])
