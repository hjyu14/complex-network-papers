"""Synthetic fixtures validate enumeration and date boundaries, not topic relevance."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_nmi import DirectoryParser, collect_crossref, collect_directory, crossref_date, digest, merge_records


def item(doi='10.1234/synthetic', **extra):
    return dict({'DOI': doi, 'ISSN': ['2522-5839'], 'title': ['Synthetic title'],
                 'URL': 'https://www.nature.com/articles/synthetic',
                 'published-online': {'date-parts': [[2026, 9, 30]]}}, **extra)


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.attempts = []

    def get(self, url):
        self.attempts.append({'retrieved_at': 'synthetic time'})
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return json.dumps({'status': 'ok', 'message': response})


class NmiPilotTests(unittest.TestCase):
    def test_card_parser_ignores_description_and_handles_void_tags(self):
        parser = DirectoryParser(2026)
        parser.feed('<html><head><title>Articles in 2026 | Nature Machine Intelligence</title></head>'
                    '<body><span>2026 (1)</span><li class="app-article-list-row__item">'
                    '<img src="unused"><h3><a class="c-card__link" href="/articles/synthetic">'
                    'Synthetic <i>title</i></a></h3><p>DO NOT STORE DESCRIPTION</p>'
                    '<ul><li>Author</li></ul><span class="c-meta__type">Article</span>'
                    '<time datetime="2026-09-30">30 Sept</time></li>'
                    '<footer>2522-5839</footer></body></html>')
        result = parser.finish()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['records'][0]['title'], 'Synthetic title')
        self.assertNotIn('DESCRIPTION', json.dumps(result))

    def test_access_or_empty_page_is_not_complete_directory(self):
        parser = DirectoryParser(2026)
        parser.feed('<html><title>Access verification</title><body>Please wait</body></html>')
        with self.assertRaises(ValueError):
            parser.finish()

    def test_current_last_page_without_hyperlink_is_counted(self):
        parser = DirectoryParser(2026)
        parser.feed('<li class="c-pagination__item" data-page="7"><a class="c-pagination__link" '
                    'href="/natmachintell/articles?year=2026&page=7">7</a></li>'
                    '<li class="c-pagination__item" data-page="8">'
                    '<span class="c-pagination__link c-pagination__link--active">8</span></li>')
        self.assertEqual(max(parser.pages), 8)

    def test_resume_rejects_modified_completed_page_evidence(self):
        resume = {'pages': [{'page': 1, 'count': 1, 'records_sha256': 'wrong hash'}],
                  'records': [{'title': 'Synthetic title', 'article_type': 'Article',
                               'date': '2026-09-30', 'article_url': 'https://www.nature.com/articles/synthetic',
                               'directory_page': 1}], 'reported_totals': [2], 'expected_last_page': 2}
        with self.assertRaises(ValueError):
            collect_directory(Client([]), 2026, resume=resume)

    def test_preferred_incomplete_date_does_not_fall_back_to_print(self):
        record = item(**{'published-online': {'date-parts': [[2026, 9]]},
                         'published-print': {'date-parts': [[2026, 9, 30]]}})
        self.assertEqual(crossref_date(record), (None, 'published-online', 'incomplete_preferred_date'))

    def test_terminal_page_requires_reported_unique_count(self):
        response = {'items': [item()], 'total-results': 2, 'next-cursor': 'ignored'}
        _, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30')
        self.assertTrue(all(not q['complete'] for q in queries))

    def test_repeated_cursor_and_page_budget_are_incomplete(self):
        response = {'items': [item()], 'total-results': 2, 'next-cursor': '*'}
        _, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30', rows=1)
        self.assertTrue(all(not q['complete'] for q in queries))
        response['next-cursor'] = 'next'
        _, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30', rows=1, max_pages=1)
        self.assertTrue(all(q['error'] == 'page_budget_exhausted' for q in queries))

    def test_no_unselected_abstract_is_retained(self):
        response = {'items': [item(abstract='synthetic forbidden text')], 'total-results': 1}
        records, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30')
        self.assertFalse(records)
        self.assertTrue(all(not q['complete'] for q in queries))

    def test_date_conflict_and_missing_official_record_remain_unresolved(self):
        record = item()
        obs = {'metadata': record, 'metadata_sha256': 'synthetic hash'}
        official = {'records': [{'title': 'Synthetic title', 'article_type': 'Article',
                                'date': '2026-09-29', 'article_url': record['URL']}]}
        rows = merge_records({record['DOI']: [obs]}, official,
                             '2026-09-01', '2026-09-30', '2026-10-03', Client([]))
        self.assertEqual(rows[0]['window_status'], 'needs_check')
        self.assertIn('publisher_crossref_date_conflict', rows[0]['issues'])
        rows = merge_records({record['DOI']: [obs]}, {'records': []},
                             '2026-09-01', '2026-09-30', '2026-10-03', Client([]))
        self.assertIn('not_found_in_official_target_window', rows[0]['issues'])

    def test_window_uses_online_date_and_includes_endpoints(self):
        observations = {}
        official = {'records': []}
        for idx, day in enumerate([[2026, 9, 1], [2026, 9, 30], [2026, 8, 31]]):
            record = item(doi=f'10.1234/synthetic{idx}', **{'published-online': {'date-parts': [day]},
                           'published-print': {'date-parts': [[2026, 9, 30]]},
                           'URL': f'https://www.nature.com/articles/synthetic{idx}'})
            observations[record['DOI']] = [{'metadata': record, 'metadata_sha256': str(idx)}]
            if idx < 2:
                official['records'].append({'title': 'Synthetic title', 'article_type': 'Article',
                                           'date': '2026-09-01' if idx == 0 else '2026-09-30',
                                           'article_url': record['URL']})
        rows = merge_records(observations, official, '2026-09-01', '2026-09-30', '2026-10-03', Client([]))
        self.assertEqual([row['window_status'] for row in rows], ['out_of_window','in_window','in_window'])


if __name__ == '__main__':
    unittest.main()
