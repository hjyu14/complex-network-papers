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
        # Keep this historical revision fixture independent of subsequent daily entries.
        self.config['entries'] = [e for e in self.config['entries'] if e['recommended_on'] == '2026-10-06']
        self.config['revisions'] = [e for e in self.config['revisions'] if e['recommended_on'] == '2026-10-06']
        e = self.config['entries'][0]
        self.papers = {e['doi']: {'assessment_sha256': e['assessment_sha256'],
            'title': 'Cross-order induced behaviors in contagion dynamics on higher-order networks',
            'input_sha256': e['input_sha256'], 'review_evidence_kind': e['review_evidence_kind'],
            'review_evidence_sha256': e['evidence_sha256']}}
        self.sources = {(e['source_run'], e['assessment_sha256']): {'publication_sha256': e['publication_sha256'],
            'decision': {'doi': e['doi'], 'category': 'core', 'input_sha256': e['input_sha256'],
                         'material_sha256': e['evidence_sha256']}}}

    def check(self, config=None):
        return validate_suggestions(config or self.config, self.papers, self.sources, as_of='2026-10-06')

    def test_valid_and_duplicate_history(self):
        self.assertEqual(len(self.check()), 1)
        self.assertEqual(self.check()[0]['review_evidence_kind'], 'fulltext')
        wrong = deepcopy(self.config); wrong['entries'].append(deepcopy(wrong['entries'][0]))
        with self.assertRaisesRegex(ValueError, 'once'): self.check(wrong)

    def test_revision_must_bind_preserved_history(self):
        wrong = deepcopy(self.config)
        wrong['revisions'][0]['supersedes_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'predecessor'): self.check(wrong)
        wrong = deepcopy(self.config)
        wrong['entries'][0]['question']['zh'] = 'Rewritten history'
        with self.assertRaisesRegex(ValueError, 'predecessor'): self.check(wrong)

    def test_fulltext_identity_and_private_fields_rejected(self):
        for change in [{'doi': '10.1234/wrong'}, {'title': 'Wrong paper'},
                       {'sha256': 'wrong'}, {'pages': 0}, {'reviewed_at':'2026-10-07T00:00:00+08:00'},
                       {'source_url': 'file:///private/paper.pdf'}, {'file': '.private/paper.pdf'}]:
            wrong = deepcopy(self.config)
            wrong['revisions'][0]['fulltext_review'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): self.check(wrong)

    def test_rereading_and_screening_bindings_are_independent(self):
        wrong = deepcopy(self.config)
        wrong['revisions'][0]['evidence_sha256'] = wrong['revisions'][0]['fulltext_review']['sha256']
        with self.assertRaisesRegex(ValueError, 'assessment/evidence'): self.check(wrong)
        wrong = deepcopy(self.config)
        wrong['revisions'][0]['reading_comment']['zh'] = []
        with self.assertRaisesRegex(ValueError, 'paragraphs'): self.check(wrong)

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
