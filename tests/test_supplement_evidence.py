"""Supplement material views must never mutate the shared append-only log."""
import sys
from pathlib import Path
import threading
import tempfile
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from screen_candidates import Workflow,BufferedLog
from supplement_evidence import Supplement, begin, close

class SupplementTests(unittest.TestCase):
    def test_concurrent_views_preserve_shared_log_and_new_material_boundary(self):
        events=[{'sequence':1,'kind':'material_cached','data':{'doi':'a'}},
                {'sequence':2,'kind':'material_cached','data':{'doi':'b'}},
                {'kind':'material_cached','data':{'doi':'a'}}]
        shared=BufferedLog(events)
        original=shared.events
        barrier=threading.Barrier(2)
        jobs=[]
        for doi in ['a','b']:
            j=object.__new__(Supplement)
            j.log=shared;j.collection_doi=doi;j.material_boundary=2
            jobs.append(j)
        def inspect(view):
            barrier.wait(timeout=3)
            self.assertIs(shared.events,original)
            return [e for e in view.log.events if e['kind']=='material_cached' and e['data']['doi']==view.active()]
        with patch.object(Workflow,'current_material',inspect):
            with ThreadPoolExecutor(max_workers=2) as pool:
                result=list(pool.map(lambda j:j.current_material(),jobs))
        self.assertEqual([len(x) for x in result],[1,0])
        self.assertIs(shared.events,original)
        self.assertEqual(shared.events,events)

    def test_followup_only_selects_unresolved_original_manifest_records(self):
        w = object.__new__(Workflow); w.log = BufferedLog([])
        w.assessments = lambda: [{'doi': 'done', 'category': 'excluded'},
                                {'doi': 'review', 'category': 'review'},
                                {'doi': 'outside', 'category': 'review'}]
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work/'manifest.json').write_text(json.dumps({'groups': {'aps': ['done', 'review', 'missing']}}))
            with patch('supplement_evidence.WORK', work): begin(w, 'followup', 100)
        self.assertEqual(w.log.events[-1]['data']['dois'], ['review', 'missing'])
        with self.assertRaises(ValueError): begin(w, 'followup', 100)

    def test_close_separates_saved_decisions_and_explicit_deferrals(self):
        w = object.__new__(Workflow)
        w.log = BufferedLog([{'sequence': 1, 'kind': 'supplement_batch_started',
                             'data': {'batch_id': 7, 'phase': 'followup', 'dois': ['a', 'b']}},
                            {'kind': 'assessment', 'data': {'doi': 'a', 'supplement_batch_id': 7}},
                            {'kind': 'supplement_deferred', 'data': {'doi': 'b', 'supplement_batch_id': 7}}])
        close(w)
        self.assertEqual(w.log.events[-1]['data']['decisions_saved'], 1)
        self.assertEqual(w.log.events[-1]['data']['deferred'], 1)

if __name__=='__main__':unittest.main()
