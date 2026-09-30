"""Fixed-cohort mechanics plus checks of the actual saved re-screen audit.

Synthetic mechanics below do not substitute for live metadata evaluation.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.collect import CONFIG, ROOT, write_json
from scripts.rescreen_existing import digest, fetch_cohort, promote_trial, rescreen


class FixedCohortTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding='utf-8'))
        self.baseline = {'window_end': '2026-09-29', 'papers': [{'doi': '10.1234/example'}]}
        self.item = {'DOI': '10.1234/example', 'type': 'journal-article',
                     'title': ['Synchronization on complex networks'], 'ISSN': ['2470-0053'],
                     'published-online': {'date-parts': [[2026, 9, 20]]}}

    def test_no_missing_extra_or_duplicate_dois(self):
        for items in [{}, {'10.1234/example': self.item, '10.1234/extra': self.item}]:
            with self.assertRaises(ValueError):
                rescreen(self.baseline, items, self.config)
        duplicate = copy.deepcopy(self.baseline)
        duplicate['papers'] *= 2
        with self.assertRaises(ValueError):
            rescreen(duplicate, {'10.1234/example': self.item}, self.config)

    def test_doi_response_identity_checked(self):
        with self.assertRaises(ValueError):
            rescreen(self.baseline, {'10.1234/example': dict(self.item, DOI='10.1234/wrong')}, self.config)

    def test_fetch_failure_propagates_and_no_outputs_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'papers.json'
            path.write_text('previous valid snapshot', encoding='utf-8')
            def fail(url):
                raise OSError('Synthetic request failure')
            with self.assertRaises(OSError):
                fetch_cohort(self.baseline, fail)
            self.assertEqual(path.read_text(encoding='utf-8'), 'previous valid snapshot')

    def test_audit_no_abstract_and_method_evidence(self):
        item = dict(self.item, abstract='We use numerical simulation to study synchronization.')
        papers, decisions = rescreen(self.baseline, {'10.1234/example': item}, self.config)
        self.assertEqual(papers[0]['methods'], ['simulation'])
        self.assertEqual(decisions[0]['metadata_sha256'], digest(item))
        self.assertNotIn('abstract', papers[0])
        self.assertNotIn('abstract', decisions[0])

    def test_real_cohort_matches_prior_review_without_new_dois(self):
        baseline_raw = (ROOT / 'site/data/baseline-v6.json').read_bytes()
        baseline = json.loads(baseline_raw)
        data = json.loads((ROOT / 'site/data/papers.json').read_text(encoding='utf-8'))
        audit = json.loads((ROOT / 'site/data/screening-report.json').read_text(encoding='utf-8'))
        expected = json.loads((ROOT / 'tests/fixtures/editorial-cohort.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(baseline_raw).hexdigest(), expected['baseline_sha256'])
        original = {p['doi'] for p in baseline['papers']}
        included = {p['doi'] for p in data['papers']}
        self.assertEqual(included, original - set(expected['do_not_display']))
        self.assertTrue(set(expected['retain_boundary_cases']) <= included)
        self.assertEqual(data['config_sha256'], digest(self.config))
        self.assertEqual(data['rescreening']['added_dois'], [])
        self.assertFalse(data['rescreening']['new_candidates_queried'])
        self.assertEqual({r['doi'] for r in audit['decisions']}, original)
        self.assertTrue(all(len(r['metadata_sha256']) == 64 for r in audit['decisions']))

    def test_promotion_rejects_stale_or_expanded_trial(self):
        source = ROOT / 'site/data/baseline-v6.json'
        with tempfile.TemporaryDirectory() as directory:
            trial, out = Path(directory) / 'trial', Path(directory) / 'out'
            for name in ['papers.json', 'screening-report.json', 'status.json']:
                value = json.loads((ROOT / 'site/data' / name).read_text(encoding='utf-8'))
                if name == 'papers.json':
                    value['config_sha256'] = 'stale'
                write_json(trial / name, value)
            with self.assertRaises(ValueError):
                promote_trial(source, trial, out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
