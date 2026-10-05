"""Lossless storage, safe output boundaries and explicit flat publication tests."""
import gzip, hashlib, json, tempfile, unittest, zipfile
from pathlib import Path
from copy import deepcopy
import test_run_inputs as fixtures
import screen_candidates as screen
from collect_candidates import EventLog
from report_io import read_bytes, read_reference, run_directory
from publication_view import source_reference, publication_workflow
from run_inputs import digest
import publish_snapshot as publish
from collect_authors import reusable_rows, save_metadata
from unittest.mock import patch


class StorageTests(unittest.TestCase):
    def test_compression_preserves_chain_and_blocks_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'events.jsonl';log=EventLog(p);log.add('test',{'value':'evidence'})
            raw=p.read_bytes();head=log.head
            p.with_name(p.name+'.gz').write_bytes(gzip.compress(raw,mtime=0));p.unlink()
            self.assertEqual(read_bytes(p),raw)
            sealed=EventLog(p);self.assertEqual(sealed.head,head)
            with self.assertRaisesRegex(ValueError,'read-only'):sealed.add('test',{})
            p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Ambiguous'):EventLog(p)

    def test_archive_hash_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=b'evidence'
            with zipfile.ZipFile(root/'a.zip','w') as z:z.writestr('source.json',data)
            ref={'archive':'a.zip','member':'source.json','sha256':hashlib.sha256(data).hexdigest()}
            self.assertEqual(read_reference(ref,root),data)
            with self.assertRaises(ValueError):read_reference({**ref,'sha256':'wrong'},root)
            with self.assertRaises(ValueError):read_reference({**ref,'member':'../source.json'},root)
            with self.assertRaises(ValueError):read_reference({**ref,'archive':'../a.zip'},root)

    def test_run_path_and_seal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'reports/runs/trial';run.mkdir(parents=True)
            self.assertEqual(run_directory(run,root,writable=True),run.resolve())
            for path in [root/'reports/final',root/'site/data',root/'reports/runs']:
                with self.assertRaises(ValueError):run_directory(path,root)
            (run/'publication.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Sealed'):run_directory(run,root,writable=True)

    def test_published_review_is_sealed_even_without_compression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'reports/runs/trial';run.mkdir(parents=True)
            review=root/'reports/reviews/revision';review.mkdir(parents=True)
            (run/'publication.json').write_text(json.dumps({'revisions':[
                {'source':{'run':'reports/reviews/revision'}}]}))
            self.assertEqual(run_directory(review,root),review.resolve())
            with self.assertRaisesRegex(ValueError,'Published review'):
                run_directory(review,root,writable=True)


class FlatTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RunTests();self.f.setUp()
        self.parent=self.f.make_run('parent','10.1/a',category='excluded')
        self.child=self.f.make_run('child','10.1/a')
        p,c=screen.Workflow(self.parent),screen.Workflow(self.child)
        old=p.assessments()[0];r=c.records['10.1/a']
        verdict={'doi':r['doi'],'title':r['title'],'record_sha256':digest(r),'candidate_sha256':c.input_sha,
                 'authority':'human user in current conversation','statement_kind':'explicit_individual_verdict',
                 'user_statement':'Include this synthetic fixture.','verdict':'include'}
        c.log.add('user_editorial_verdict',verdict)
        d={**c.assessments()[0],'previous_assessment_sha256':digest(old),'previous_input_sha256':old['input_sha256'],
           'candidate_sha256':c.input_sha,'record_sha256':digest(r),'editorial_basis':{'verdict_sha256':digest(verdict)}}
        c.log.add('assessment_corrected',d)
        self.f.notes['papers'][r['doi']]['assessment_sha256']=digest(d)
        self.f.write('config/publication-notes.json',self.f.notes)
        authors=json.loads((self.child/'author-metadata.json').read_text())
        self.f.write('reports/parent/author-metadata.json',authors)
        self.manifest={'version':'flat-publication-1','inventory':source_reference(p),
            'revisions':[{'mode':'explicit_revision','source':source_reference(c),'targets':[{
                'doi':r['doi'],'previous_assessment_sha256':digest(old),'previous_input_sha256':old['input_sha256']}]}],
            'authors':{'file':'author-metadata.json','metadata_sha256':digest(authors),'audit':{
                'path':'reports/child/screening-log.jsonl','sha256':hashlib.sha256((self.child/'screening-log.jsonl').read_bytes()).hexdigest()}}}
        self.save()

    def save(self):self.f.write('reports/parent/publication.json',self.manifest)
    def tearDown(self):self.f.tearDown()

    def test_flat_release_keeps_scientific_authority(self):
        p=publish.build_snapshot(self.parent)['papers.json']
        self.assertEqual(len(p['papers']),1)
        self.assertEqual(p['papers'][0]['scope_authority'],'human user in current conversation')
        self.assertEqual(len(publication_workflow(self.parent).sources),2)

    def test_wrong_old_binding_rejected(self):
        self.manifest['revisions'][0]['targets'][0]['previous_assessment_sha256']='bad';self.save()
        with self.assertRaisesRegex(ValueError,'previous assessment'):publication_workflow(self.parent)

    def test_missing_target_rejected(self):
        self.manifest['revisions'][0]['targets']=[];self.save()
        with self.assertRaisesRegex(ValueError,'target set'):publication_workflow(self.parent)

    def test_missing_user_verdict_rejected(self):
        c=screen.Workflow(self.child);d=deepcopy(c.assessments()[0]);d.pop('editorial_basis');c.log.add('assessment_corrected',d)
        self.manifest['revisions'][0]['source']=source_reference(c);self.save()
        with self.assertRaisesRegex(ValueError,'bound user verdict'):publication_workflow(self.parent)

    def test_author_reuse_is_explicit_and_does_not_modify_input(self):
        previous=json.loads((self.child/'author-metadata.json').read_text());before=deepcopy(previous)
        records=screen.Workflow(self.child).records
        self.assertEqual(reusable_rows(previous,records,{'10.1/a'}),previous['records'])
        self.assertEqual(reusable_rows(previous,records,{'10.1/a'},['10.1/a']),{})
        self.assertEqual(previous,before)

    def test_author_update_preserves_reconstructible_previous_version(self):
        path=self.child/'author-metadata.json';previous=json.loads(path.read_text())
        result=deepcopy(previous);result['records']['10.1/a']['authors']=['New Synthetic Author']
        w=screen.Workflow(self.child)
        with patch('collect_authors.ROOT',self.f.root):save_metadata(w,path,result,previous)
        change=next(e['data'] for e in w.log.events if e['kind']=='author_metadata_replaced')
        reconstructed={**change['previous_header'],'records':{
            **{d:r for d,r in result['records'].items() if d not in change['added_dois']},
            **change['previous_changed_records']}}
        self.assertEqual(reconstructed,previous)
        self.assertEqual(digest(reconstructed),change['previous_metadata_sha256'])

    def test_pending_mode_cannot_replace_resolved_verdict(self):
        self.manifest['revisions'][0]['mode']='resolve_pending';self.save()
        with self.assertRaisesRegex(ValueError,'unresolved set'):publication_workflow(self.parent)

    def test_duplicate_review_source_rejected(self):
        self.manifest['revisions'].append(deepcopy(self.manifest['revisions'][0]));self.save()
        with self.assertRaisesRegex(ValueError,'distinct direct'):publication_workflow(self.parent)


if __name__=='__main__':unittest.main()
