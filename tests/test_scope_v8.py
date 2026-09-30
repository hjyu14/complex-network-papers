"""V8 scope gates using published review records; no invented abstracts."""
from datetime import date
import json
import unittest

from scripts.collect import ROOT, CONFIG, screen


class ScopeV8Tests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding='utf-8'))
        self.papers = json.loads((ROOT / 'site/data/baseline-v6.json').read_text(encoding='utf-8'))['papers']

    def item(self, doi):
        p = next(x for x in self.papers if x['doi'] == doi)
        return {'DOI': doi, 'type': 'journal-article', 'title': [p['title']],
                'ISSN': p['issns'], 'published-online': {'date-parts': [[2026, 9, 20]]}}

    def test_core_and_transferable_class_without_method_labels(self):
        for doi, category in [('10.1103/v1vq-skr1', 'core'), ('10.1103/xsg5-cb6l', 'transferable_application')]:
            paper, reason = screen(self.item(doi), self.config, date(2026, 9, 29))
            self.assertEqual(reason, 'included')
            self.assertEqual(paper['scope_class'], category)
            self.assertNotIn('methods', paper)
            self.assertNotIn('method_evidence', paper)

    def test_unknown_and_changed_title_do_not_pass_keywords(self):
        item = self.item('10.1103/v1vq-skr1')
        item['DOI'] = '10.1234/unreviewed'
        self.assertEqual(screen(item, self.config, date(2026, 9, 29))[1], 'review_unassessed_scope')
        item = self.item('10.1103/v1vq-skr1')
        item['title'] = ['A changed synchronization paper on complex networks']
        self.assertEqual(screen(item, self.config, date(2026, 9, 29))[1], 'review_changed_title')

    def test_excluded_and_unresolved_are_not_promoted(self):
        for doi, reason in [('10.1073/pnas.2620995123', 'outside_editorial_scope'), ('10.1103/32qy-2v16', 'review_scope')]:
            self.assertEqual(screen(self.item(doi), self.config, date(2026, 9, 29))[1], reason)

    def test_approved_assessment_never_bypasses_metadata_boundaries(self):
        item = self.item('10.1103/v1vq-skr1')
        for field, value, reason in [('ISSN', [], 'journal_not_whitelisted'), ('type', 'posted-content', 'not_article'),
                                      ('published-online', {'date-parts': [[2026, 9, 30]]}, 'outside_window')]:
            changed = dict(item, **{field: value})
            self.assertEqual(screen(changed, self.config, date(2026, 9, 29))[1], reason)

    def test_published_review_hash_and_two_classes_match(self):
        import hashlib
        from collections import Counter
        data = json.loads((ROOT / 'site/data/papers.json').read_text(encoding='utf-8'))
        registry_raw = (ROOT / self.config['scope_policy']['review_file']).read_bytes()
        registry = json.loads(registry_raw)
        self.assertEqual(data['rescreening']['scope_review_sha256'], hashlib.sha256(registry_raw).hexdigest())
        self.assertEqual({p['doi'] for p in data['papers']}, {doi for doi, row in registry['decisions'].items() if row['v8_category'] in ['core','transferable_application']})
        self.assertEqual(Counter(p['scope_class'] for p in data['papers']), {'core': 110, 'transferable_application': 7})


if __name__ == '__main__':
    unittest.main()
