"""Synthetic, explicit settled-verdict revisions; no scientific classifier."""
from copy import deepcopy
import json
import unittest
import test_run_inputs as fixtures
import screen_candidates as screen
from publication_view import PublicationView, source_reference, publication_workflow, publication_metadata_reference
from collect_candidates import EventLog
from run_inputs import digest
import publish_snapshot as publish


class EditorialRevisionViewTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RunTests();self.f.setUp()
        self.parent=self.f.make_run('parent','10.1/a',category='excluded')
        self.child=self.f.make_run('child','10.1/a')
        p,c=screen.Workflow(self.parent),screen.Workflow(self.child)
        old=p.assessments()[0];r=c.records['10.1/a']
        self.verdict={'doi':r['doi'],'title':r['title'],'record_sha256':digest(r),
            'candidate_sha256':c.input_sha,'verdict':'include',
            'statement_kind':'explicit_individual_verdict',
            'authority':'human user in current conversation','user_statement':'Include this synthetic fixture.'}
        c.log.add('user_editorial_verdict',self.verdict)
        d={**c.assessments()[0],'previous_assessment_sha256':digest(old),
            'previous_input_sha256':old['input_sha256'],'candidate_sha256':c.input_sha,
            'record_sha256':digest(r),'editorial_basis':{'verdict_sha256':digest(self.verdict)}}
        c.log.add('assessment_corrected',d)
        self.f.notes['papers'][r['doi']]['assessment_sha256']=digest(d)
        self.f.write('config/publication-notes.json',self.f.notes)
        self.targets=[{'doi':r['doi'],'previous_assessment_sha256':digest(old),
            'previous_input_sha256':old['input_sha256']}]
        self.view=self.f.root/'reports/view';self.view.mkdir()
        self.pin()
        authors=json.loads((self.child/'author-metadata.json').read_text())
        authors['candidate_sha256']=p.input_sha
        self.f.write('reports/view/author-metadata.json',authors)
        EventLog(self.view/'publication-log.jsonl').add('author_metadata_completed',{'metadata_sha256':digest(authors)})

    def tearDown(self):
        self.f.tearDown()

    def pin(self):
        manifest={'version':'editorial-revision-publication-view-1',
            'parent':source_reference(publication_workflow(self.parent)),
            'adjudication':source_reference(screen.Workflow(self.child)),
            'parent_publication_hash_basis':'canonical_json',
            'parent_publication_files':publication_metadata_reference(self.parent),
            'targets':self.targets}
        self.f.write('reports/view/release-view.json',manifest)
        log=self.view/'publication-log.jsonl'
        if log.exists():log.unlink()
        EventLog(log).add('publication_view_started',{'manifest_sha256':digest(manifest)})

    def test_settled_exclusion_explicitly_revised_without_mutating_sources(self):
        before={p:p.read_bytes() for folder in [self.parent,self.child] for p in folder.rglob('*') if p.is_file()}
        result=publish.build_snapshot(self.view)['papers.json']
        self.assertEqual(result['candidate_count'],1)
        self.assertEqual(result['screening_counts']['included'],1)
        self.assertEqual(result['papers'][0]['scope_authority'],'human user in current conversation')
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_original_resolved_only_adjudication_is_not_relaxed(self):
        m=json.loads((self.view/'release-view.json').read_text());m['version']='adjudicated-publication-view-1'
        self.f.write('reports/view/release-view.json',m)
        with self.assertRaises((ValueError,FileNotFoundError)):PublicationView(self.view)

    def test_target_omission_rejected(self):
        self.targets=[];self.pin()
        with self.assertRaisesRegex(ValueError,'explicit parent target set'):PublicationView(self.view)

    def test_forged_previous_verdict_rejected(self):
        c=screen.Workflow(self.child);d=deepcopy(c.assessments()[0]);d['previous_assessment_sha256']='bad'
        c.log.add('assessment_corrected',d);self.pin()
        with self.assertRaisesRegex(ValueError,'previous assessment'):PublicationView(self.view)

    def test_missing_user_authority_rejected(self):
        c=screen.Workflow(self.child);d=deepcopy(c.assessments()[0]);d.pop('editorial_basis')
        c.log.add('assessment_corrected',d);self.pin()
        with self.assertRaisesRegex(ValueError,'explicit bound user verdict'):PublicationView(self.view)

    def test_wrong_verdict_candidate_binding_rejected(self):
        c=screen.Workflow(self.child);v={**self.verdict,'candidate_sha256':'wrong'}
        c.log.add('user_editorial_verdict',v);d=deepcopy(c.assessments()[0]);d['editorial_basis']={'verdict_sha256':digest(v)}
        c.log.add('assessment_corrected',d);self.pin()
        with self.assertRaisesRegex(ValueError,'explicit bound user verdict'):PublicationView(self.view)

    def test_editorial_direction_is_not_a_final_verdict(self):
        c=screen.Workflow(self.child);v={**self.verdict,'statement_kind':'editorial_direction'}
        c.log.add('user_editorial_verdict',v);d=deepcopy(c.assessments()[0]);d['editorial_basis']={'verdict_sha256':digest(v)}
        c.log.add('assessment_corrected',d);self.pin()
        with self.assertRaisesRegex(ValueError,'explicit bound user verdict'):PublicationView(self.view)

    def test_child_log_advancement_without_repin_rejected(self):
        screen.Workflow(self.child).log.add('observation',{'message':'Later synthetic evidence'})
        with self.assertRaisesRegex(ValueError,'Pinned publication source changed'):PublicationView(self.view)

    def test_inherited_authors_are_pinned(self):
        data=json.loads((self.parent/'author-metadata.json').read_text());data['unexpected']='tamper'
        self.f.write('reports/parent/author-metadata.json',data)
        with self.assertRaisesRegex(ValueError,'parent publication metadata'):PublicationView(self.view)

    def test_parent_json_line_endings_do_not_change_content_binding(self):
        path=self.parent/'author-metadata.json'
        path.write_bytes(path.read_bytes().replace(b'\n',b'\r\n'))
        self.assertEqual(PublicationView(self.view).status()['not_assessed'],0)

    def test_repin_does_not_allow_unresolved_revision(self):
        c=screen.Workflow(self.child);d=deepcopy(c.assessments()[0]);d['category']='review'
        c.log.add('assessment_corrected',d);self.pin()
        with self.assertRaisesRegex(ValueError,'unresolved'):PublicationView(self.view)

    def test_cyclic_view_rejected(self):
        m=json.loads((self.view/'release-view.json').read_text());m['parent']['run']='reports/view'
        self.f.write('reports/view/release-view.json',m)
        with self.assertRaisesRegex(ValueError,'Invalid publication source'):PublicationView(self.view)

    def test_nested_revision_preserves_original_coverage_and_recursively_pinned_sources(self):
        parent=PublicationView(self.view)
        child_path=self.f.make_run('child2','10.1/a')
        c=screen.Workflow(child_path);prior=parent.assessments()[0];r=c.records['10.1/a']
        v={**self.verdict,'candidate_sha256':c.input_sha}
        c.log.add('user_editorial_verdict',v)
        d={**c.assessments()[0],'candidate_sha256':c.input_sha,'record_sha256':digest(r),
            'previous_assessment_sha256':digest(prior),'previous_input_sha256':prior['input_sha256'],
            'editorial_basis':{'verdict_sha256':digest(v)}}
        c.log.add('assessment_corrected',d)
        self.f.notes['papers']['10.1/a']['assessment_sha256']=digest(d)
        self.f.write('config/publication-notes.json',self.f.notes)
        nested=self.f.root/'reports/nested';nested.mkdir()
        manifest={'version':'editorial-revision-publication-view-1',
            'parent':source_reference(parent),'adjudication':source_reference(c),
            'parent_publication_hash_basis':'canonical_json',
            'parent_publication_files':publication_metadata_reference(self.view),
            'targets':[{'doi':'10.1/a','previous_assessment_sha256':digest(prior),
                'previous_input_sha256':prior['input_sha256']}]}
        self.f.write('reports/nested/release-view.json',manifest)
        authors=json.loads((self.view/'author-metadata.json').read_text())
        self.f.write('reports/nested/author-metadata.json',authors)
        log=EventLog(nested/'publication-log.jsonl')
        log.add('publication_view_started',{'manifest_sha256':digest(manifest)})
        log.add('author_metadata_completed',{'metadata_sha256':digest(authors)})
        result=publish.build_snapshot(nested)['papers.json']
        self.assertEqual(result['coverage'][0]['candidate_count'],1)
        self.assertEqual(result['papers'][0]['scope_authority'],'human user in current conversation')
        self.assertEqual(result['papers'][0]['assessment_sha256'],digest(d))
        screen.Workflow(self.parent).log.add('observation',{'message':'Tamper with the deepest source'})
        with self.assertRaisesRegex(ValueError,'Pinned publication source changed'):PublicationView(nested)


if __name__=='__main__':unittest.main()
