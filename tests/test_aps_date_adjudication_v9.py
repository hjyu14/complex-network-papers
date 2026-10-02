import unittest

from scripts.adjudicate_remaining_v9 import resolve_aps_date


class ApsDateAdjudicationTests(unittest.TestCase):
    def resolve(self, **changes):
        inputs = {'doi': '10.1103/43yn-sh6g', 'previous_online': '2026-09-09',
                  'accepted': '2026-09-09', 'published': '2026-10-01',
                  'fresh_online': '2026-10-01'}
        inputs.update(changes)
        return resolve_aps_date(**inputs)

    def test_new_crossref_agreement_resolves_with_history_preserved(self):
        result = self.resolve()
        self.assertEqual(result['status'], 'resolved_fresh_crossref_publisher_agreement')
        self.assertEqual(result['effective_date'], '2026-10-01')
        self.assertTrue(result['original_date_preserved'])

    def test_user_authorized_publisher_date_when_crossref_still_acceptance(self):
        result = self.resolve(fresh_online='2026-09-09')
        self.assertEqual(result['status'], 'resolved_authorized_publisher_date_priority')
        self.assertEqual(result['effective_date'], '2026-10-01')

    def test_unrelated_earlier_online_date_is_not_silently_replaced(self):
        self.assertEqual(self.resolve(previous_online='2026-09-08')['status'], 'review')
        self.assertEqual(self.resolve(fresh_online='2026-09-08')['status'], 'review')

    def test_incomplete_dates_remain_review(self):
        self.assertEqual(self.resolve(published='2026-10')['status'], 'review')
        self.assertEqual(self.resolve(published=None)['status'], 'review')

    def test_aps_exception_not_generalized_to_other_publishers(self):
        self.assertEqual(self.resolve(doi='10.1016/example')['status'], 'review')


if __name__ == '__main__':
    unittest.main()
