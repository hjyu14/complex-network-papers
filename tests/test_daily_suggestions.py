"""Recommendation history must not duplicate papers or drift from reviewed evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from daily_suggestions import validate_suggestions


class SuggestionTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.config = json.loads((root/'config/daily-suggestions.json').read_text(encoding='utf-8'))
        e = self.config['entries'][0]
        self.papers = {e['doi']: {'assessment_sha256': e['assessment_sha256'],
            'input_sha256': e['input_sha256'], 'review_evidence_kind': e['review_evidence_kind'],
            'review_evidence_sha256': e['evidence_sha256']}}
        self.sources = {(e['source_run'], e['assessment_sha256']): {'publication_sha256': e['publication_sha256'],
            'decision': {'doi': e['doi'], 'category': 'core', 'input_sha256': e['input_sha256'],
                         'material_sha256': e['evidence_sha256']}}}

    def check(self, config=None):
        return validate_suggestions(config or self.config, self.papers, self.sources, as_of='2026-10-06')

    def test_valid_and_duplicate_history(self):
        self.assertEqual(len(self.check()), 1)
        wrong = deepcopy(self.config); wrong['entries'].append(deepcopy(wrong['entries'][0]))
        with self.assertRaisesRegex(ValueError, 'once'): self.check(wrong)

    def test_current_evidence_change_requires_reread(self):
        self.papers[next(iter(self.papers))]['review_evidence_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'evidence has changed'): self.check()

    def test_source_corruption_missing_current_and_future_dates(self):
        for change in [{'evidence_sha256': 'wrong'}, {'publication_sha256': 'wrong'},
                       {'recommended_on': '2026-10-07'}, {'abstract': 'do not export'}]:
            wrong = deepcopy(self.config); wrong['entries'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): self.check(wrong)
        self.papers.clear()
        with self.assertRaisesRegex(ValueError, 'public paper list'): self.check()

    def test_future_rereading_and_incomplete_translation_rejected(self):
        for change in [{'reviewed_at': '2026-10-07T00:01:00+08:00'}, {'question': {'en': 'Missing Chinese'}}]:
            wrong = deepcopy(self.config); wrong['entries'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): self.check(wrong)
