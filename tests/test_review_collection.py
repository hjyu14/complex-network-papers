"""Historical collection bindings and canonical DOI references."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from review_collection import attach_reviews


class ReviewCollectionTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = {'papers.json': json.loads((ROOT/'site/data/papers.json').read_text(encoding='utf8'))}

    def test_complete_collection_is_separate_and_shared_doi_is_referenced(self):
        before = copy.deepcopy(self.artifacts)
        result = attach_reviews(self.artifacts)
        self.assertEqual(before, self.artifacts)
        reviews = result['reviews.json']
        self.assertEqual(reviews['total_count'], 84)
        self.assertEqual(len(reviews['papers']), 84)
        self.assertEqual(reviews['current_collection_dois'], [])
        self.assertNotIn('10.1063/5.0348359', {p['doi'] for p in reviews['papers']})
        self.assertEqual({p['journal_short'] for p in reviews['papers']}, {'PR', 'RMP'})
        self.assertEqual(sum(p['journal_short']=='PR' for p in reviews['papers']), 72)
        dates = {p['doi']:p['date'] for p in reviews['papers']}
        self.assertEqual(dates['10.1016/j.physrep.2026.09.008'], '2026-10-15')
        self.assertEqual(dates['10.1016/j.physrep.2026.09.002'], '2026-09-11')
        self.assertEqual(dates['10.1016/j.physrep.2026.07.004'], '2026-08-27')
        self.assertNotIn('10.1016/j.physrep.2026.05.004', dates)
        encoded = json.dumps(reviews)
        for forbidden in ['.private/', '"abstract":', '"abstract_text":', 'fulltext-library', 'C:\\Users']:
            self.assertNotIn(forbidden, encoded)

    def test_matching_daily_identity_is_shared_but_conflicts_fail(self):
        paper = attach_reviews(self.artifacts)['reviews.json']['papers'][0]
        self.artifacts['papers.json']['papers'].append(copy.deepcopy(paper))
        result = attach_reviews(self.artifacts)['reviews.json']
        self.assertEqual(len(result['papers']), 83)
        self.assertEqual(result['total_count'], 84)
        self.assertIn(paper['doi'], result['current_collection_dois'])
        self.artifacts['papers.json']['papers'][-1]['date'] = '2000-01-01'
        with self.assertRaisesRegex(ValueError, 'Conflicting review'):
            attach_reviews(self.artifacts)

    def test_source_pin_and_record_bindings_are_checked(self):
        config = json.loads((ROOT/'config/review-collection.json').read_text(encoding='utf8'))
        source = json.loads((ROOT/config['source']['path']).read_text(encoding='utf8'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'config').mkdir()
            for supplemental in config.get('supplemental_sources', []):
                dest = root/supplemental['path']; dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((ROOT/supplemental['path']).read_bytes())
            target = root/config['source']['path']; target.parent.mkdir(parents=True)
            target.write_text(json.dumps(source), encoding='utf8')
            (root/'config/review-collection.json').write_text(json.dumps(config), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'source changed'):
                attach_reviews(self.artifacts, root)
            config['source']['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
            (root/'config/review-collection.json').write_text(json.dumps(config), encoding='utf8')
            self.assertEqual(attach_reviews(self.artifacts, root)['reviews.json']['total_count'], 84)
            source['records'][0]['paper']['date'] = '2000-01-01'
            target.write_text(json.dumps(source), encoding='utf8')
            config['source']['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
            (root/'config/review-collection.json').write_text(json.dumps(config), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'record binding changed'):
                attach_reviews(self.artifacts, root)

    def test_supplement_pin_and_duplicate_identity_fail(self):
        config = json.loads((ROOT/'config/review-collection.json').read_text(encoding='utf8'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'config').mkdir()
            for source in [config['source'], *config['supplemental_sources']]:
                target = root/source['path']; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT/source['path']).read_bytes())
            cfg = root/'config/review-collection.json'
            cfg.write_text(json.dumps(config), encoding='utf8')
            supplement = root/config['supplemental_sources'][0]['path']
            supplement.write_bytes(supplement.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError, 'source changed'):
                attach_reviews(self.artifacts, root)
            config['supplemental_sources'] = [config['source']]
            config['count'] = 162
            cfg.write_text(json.dumps(config), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'duplicate DOI'):
                attach_reviews(self.artifacts, root)


if __name__ == '__main__':
    unittest.main()
