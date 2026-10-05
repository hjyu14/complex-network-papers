import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import abstract_cache as cache
import screen_candidates as screening


class CacheTests(unittest.TestCase):
    def test_legacy_reference_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            key=hashlib.sha256(b'10.1/example').hexdigest()
            old=root/key/'version.json'
            new=cache.relocated(root, old.relative_to(root))
            self.assertEqual(new.parent, cache.doi_directory(root, '10.1/example'))
            new.parent.mkdir(parents=True)
            new.write_text('{}')
            self.assertEqual(cache.resolve_reference(root, old), new)
            old.parent.mkdir()
            old.write_text('{"different":true}')
            with self.assertRaises(ValueError):
                cache.resolve_reference(root, old)

    def test_confinement_and_manual_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'cache'
            self.assertEqual(cache.relocated(root,'browser-inputs/a.json'), root/'legacy-inputs/browser-inputs/a.json')
            for path in (root/'../outside.json', root):
                with self.assertRaises(ValueError):
                    cache.resolve_reference(root,path)
            with self.assertRaises(ValueError):
                cache.relocated(root,'../outside.json')

    def test_historical_judgment_reads_exact_version_and_export(self):
        from types import SimpleNamespace
        import manage_runs
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            private=root/'.private/abstract-cache/v9'
            run=root/'reports/runs/example'
            run.mkdir(parents=True)
            m={'doi':'10.1/example','abstract':'PRIVATE TEST ABSTRACT'}
            version=screening.digest(m)
            key=hashlib.sha256(m['doi'].encode()).hexdigest()
            old=private/key/(version+'.json')
            new=cache.relocated(private,old.relative_to(private))
            new.parent.mkdir(parents=True)
            new.write_text(json.dumps(m))
            data={'doi':m['doi'],'material_sha256':version,'cache_path':old.relative_to(root).as_posix()}
            w=object.__new__(screening.Workflow)
            w.log=screening.BufferedLog([{'kind':'material_cached','data':data}])
            w.records={m['doi']:{'doi':m['doi'],'title':'Example'}}
            with patch.object(screening,'ROOT',root), patch.object(screening,'PRIVATE',private), \
                 patch.object(screening,'validate_material'), patch.object(w,'active',return_value=m['doi']):
                self.assertEqual(w.current_material(),m)
                fake=SimpleNamespace(records=w.records,log=w.log,status=lambda:{},assessments=lambda:[
                    {'doi':m['doi'],'category':'core','material_sha256':version}])
                with patch('publication_view.publication_workflow',return_value=fake):
                    manage_runs.export_view(run,root)
                    exported=(root/'.private/work/example/exports/review.json').read_text(encoding='utf8')
                    self.assertNotIn(m['abstract'],exported)
                    row=json.loads(exported)['records'][0]
                    self.assertEqual(row['cache_status'],'verified')
                    self.assertEqual(row['cache_file'],new.relative_to(root).as_posix())
                    new.write_text(json.dumps({**m,'abstract':'changed'}))
                    with self.assertRaises(ValueError):
                        manage_runs.export_view(run,root)
                with self.assertRaises(ValueError):
                    w.current_material()

    def test_reuse_keeps_material_hash_and_one_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            private=root/'.private/abstract-cache/v9'
            material={'doi':'10.1/example','abstract_sha256':'a','source_url':'https://example.org',
                      'abstract_basis':'test','retrieved_at':'2026-10-01'}
            w=object.__new__(screening.Workflow)
            w.records={'10.1/example':{'doi':'10.1/example'}}
            w.log=screening.BufferedLog([])
            with patch.object(screening,'ROOT',root), patch.object(screening,'PRIVATE',private), \
                 patch.object(screening,'OLD_PRIVATE',root/'old'), \
                 patch.object(screening,'validate_material'), \
                 patch.object(w,'active',return_value='10.1/example'), \
                 patch.object(w,'current_material',return_value=None), \
                 patch.object(w,'next',return_value={}):
                w.cache(material)
                original=screening.digest(material)
                w.fetch('cache')
                paths=list(private.rglob('*.json'))
                self.assertEqual(len(paths),1)
                self.assertEqual(screening.digest(json.loads(paths[0].read_text())),original)
                events=[e['data'] for e in w.log.events if e['kind']=='material_cached']
                self.assertEqual([e['material_sha256'] for e in events],[original,original])
                self.assertEqual(events[-1]['imported_from'],str(paths[0]))


if __name__=='__main__':
    unittest.main()
