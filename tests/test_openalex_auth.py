"""Credential isolation and authenticated abstract acquisition, without real keys."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import screen_candidates as s


class OpenAlexAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.root_patch = patch.object(s, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.url = 'https://api.openalex.org/works/https://doi.org/10.1%2Fexample'

    def test_dotenv_formats_and_environment_priority(self):
        for value in ['test-token', '"test-token"', "'test-token'", 'test-token # comment']:
            with self.subTest(value=value):
                (self.root / '.env').write_text(
                    '\ufeffOTHER_SECRET=unrelated\nexport OPENALEX_API_KEY = ' + value + '\n',
                    encoding='utf-8')
                self.assertEqual(s.openalex_api_key(), 'test-token')
                self.assertNotIn('OTHER_SECRET', os.environ)
        with patch.dict(os.environ, {'OPENALEX_API_KEY': 'process-token'}), \
                patch.object(Path, 'read_text', side_effect=AssertionError('Environment wins')):
            self.assertEqual(s.openalex_api_key(), 'process-token')

    def test_missing_key_preserves_anonymous_access(self):
        self.assertIsNone(s.evidence_request(self.url, 'openalex').get_header('Authorization'))
        (self.root / '.env').write_text('OTHER=value\n', encoding='utf-8')
        self.assertIsNone(s.openalex_api_key())

    def test_invalid_config_never_exposes_value(self):
        for value in ['', 'secret token', '"secret-token', 'secret\nOPENALEX_API_KEY=duplicate']:
            with self.subTest(value=value):
                (self.root / '.env').write_text('OPENALEX_API_KEY=' + value, encoding='utf-8')
                with self.assertRaises(ValueError) as caught:
                    s.openalex_api_key()
                self.assertNotIn('secret', str(caught.exception))
        with patch.dict(os.environ, {'OPENALEX_API_KEY': 'secret\r\nInjected: value'}):
            with self.assertRaises(ValueError):
                s.evidence_request(self.url, 'openalex')

    def test_auth_is_origin_scoped_and_not_forwarded_on_redirect(self):
        with patch.dict(os.environ, {'OPENALEX_API_KEY': 'test-token'}):
            request = s.evidence_request(self.url, 'openalex')
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
            self.assertNotIn('test-token', request.full_url)
            for channel in ['crossref', 'publisher']:
                other = s.evidence_request('https://example.org/paper', channel)
                self.assertIsNone(other.get_header('Authorization'))
            with self.assertRaises(ValueError):
                s.evidence_request('https://example.org/paper', 'openalex')
            for destination in ['https://example.org/paper', 'https://api.openalex.org/other']:
                redirected = HTTPRedirectHandler().redirect_request(
                    request, io.BytesIO(), 302, 'Found', {}, destination)
                self.assertIsNone(redirected.get_header('Authorization'))

    def workflow(self):
        record = {'doi': '10.1/example', 'title': 'A study', 'issns': ['0000-0001']}
        w = object.__new__(s.Workflow)
        w.records = {record['doi']: record}
        w.collection_doi = record['doi']
        w.log = s.BufferedLog([])
        w.request_stop = threading.Event()
        w.current_material = lambda: None
        w.next = lambda: {}
        w.openalex_access = s.OpenAlexAccess()
        w.openalex_access.result = dict(day=s.datetime.fromisoformat(s.now()).astimezone(s.ZoneInfo('Asia/Shanghai')).date().isoformat(), status='ready')
        for channel in ['cache', 'crossref', 'publisher']:
            w.attempt(channel, None, 'missing')
        return w

    def test_authenticated_fetch_preserves_material_and_public_log_boundary(self):
        w = self.workflow()
        captured = []
        w.cache = captured.append
        class Response:
            status = 200
            url = self.url
            headers = {'x-ratelimit-remaining': '999', 'Authorization': 'test-token'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return json.dumps({'doi': 'https://doi.org/10.1/example', 'title': 'A study',
                    'locations': [{'source': {'issn': ['0000-0001']}}],
                    'abstract_inverted_index': {'An': [0], 'abstract.': [1]}}).encode()
        with patch.dict(os.environ, {'OPENALEX_API_KEY': 'test-token'}), \
                patch.object(s, 'urlopen', return_value=Response()) as fetch:
            w.fetch('openalex')
        self.assertEqual(fetch.call_args.args[0].get_header('Authorization'), 'Bearer test-token')
        self.assertEqual(captured[0]['abstract'], 'An abstract.')
        s.validate_material(captured[0], w.records[w.active()])
        self.assertEqual(w.log.events[-1]['data']['request_limits'], {'x-ratelimit-remaining': '999'})
        self.assertNotIn('test-token', json.dumps(w.log.events) + json.dumps(captured))
        self.assertFalse(any(e['kind'] == 'assessment' for e in w.log.events))

    def test_auth_errors_do_not_retry_anonymously_and_429_still_stops(self):
        for status in [401, 403, 429]:
            with self.subTest(status=status):
                w = self.workflow()
                error = HTTPError(self.url, status, 'test-token', {}, None)
                with patch.dict(os.environ, {'OPENALEX_API_KEY': 'test-token'}), \
                        patch.object(s, 'urlopen', side_effect=error) as fetch:
                    self.assertEqual(w.fetch('openalex'), {'result': 'failed'})
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(w.request_stop.is_set(), status == 429)
                self.assertNotIn('test-token', json.dumps(w.log.events))
                self.assertEqual(w.log.events[-1]['data']['http_status'], status)


if __name__ == '__main__':
    unittest.main()
