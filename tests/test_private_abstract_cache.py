import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from private_abstract_cache import AbstractCache
from check_private_abstracts import violations


class PrivateAbstractTests(unittest.TestCase):
    def test_versions_identity_and_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = AbstractCache(temp)
            meta = dict(doi='10.1234/test', doi_match=True, title='Synthetic test',
                        source_url='https://example.org/test', retrieved_at='2026-10-02T00:00:00Z',
                        abstract_basis='crossref.abstract')
            cache.put(meta, 'Synthetic abstract one.')
            cache.put(dict(meta, retrieved_at='2026-10-02T01:00:00Z'), 'Synthetic abstract two.')
            self.assertEqual(cache.get(meta['doi'])['abstract'], 'Synthetic abstract two.')
            self.assertEqual(len(list(cache.root.rglob('*.json'))), 2)
            with self.assertRaises(ValueError):
                cache.put(dict(meta, doi_match=False), 'Synthetic abstract.')
            with self.assertRaises(ValueError):
                cache.put(dict(meta, abstract_basis='description'), 'Description.')
            path = next(cache.root.rglob('*.json'))
            path.write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                cache.get(meta['doi'])

    def test_forced_staging_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.run(['git', '-C', temp, *args], check=True, capture_output=True)
            git('init')
            (root/'.gitignore').write_text('/.private/\n', encoding='utf-8')
            cache = root/'.private/test.json'
            cache.parent.mkdir()
            cache.write_text('{}', encoding='utf-8')
            git('check-ignore', '.private/test.json')
            self.assertEqual(violations(root), [])
            git('add', '-f', '.private/test.json')
            self.assertEqual(len(violations(root)), 1)
            site = root/'site/data/test.json'
            site.parent.mkdir(parents=True)
            site.write_text(json.dumps({'abstract': 'Synthetic only.'}), encoding='utf-8')
            git('add', 'site/data/test.json')
            self.assertEqual(len(violations(root)), 2)


if __name__ == '__main__':
    unittest.main()
