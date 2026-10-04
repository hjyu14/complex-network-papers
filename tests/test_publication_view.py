"""Synthetic supersession fixtures; not scientific assessments."""
import json
from copy import deepcopy
import unittest
import test_run_inputs as fixtures
import screen_candidates as screen
from publication_view import PublicationView, source_reference
from collect_candidates import EventLog
from run_inputs import digest
import publish_snapshot as publish


class PublicationViewTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RunTests()
        self.f.setUp()
        self.parent = self.f.make_run('parent', '10.1/a', category='review')
        self.child = self.f.make_run('child', '10.1/a')
        p, c = screen.Workflow(self.parent), screen.Workflow(self.child)
        old = p.assessments()[0]
        d = {**c.assessments()[0], 'previous_assessment_sha256': digest(old),
             'previous_input_sha256': old['input_sha256']}
        c.log.add('assessment_corrected', d)
        self.f.notes['papers']['10.1/a']['assessment_sha256'] = digest(d)
        self.f.write('config/publication-notes.json', self.f.notes)
        pm = {'parent_run': 'reports/parent', 'parent_log_head': p.log.head,
              'parent_candidate_sha256': p.input_sha, 'targets': [
                  {'doi': '10.1/a', 'previous_assessment_sha256': digest(old),
                   'previous_input_sha256': old['input_sha256']}]}
        self.f.write('reports/child/parent-manifest.json', pm)
        self.view = self.f.root/'reports/view'; self.view.mkdir()
        self.pin()
        authors = json.loads((self.child/'author-metadata.json').read_text())
        authors['candidate_sha256'] = p.input_sha
        self.f.write('reports/view/author-metadata.json', authors)
        EventLog(self.view/'publication-log.jsonl').add('author_metadata_completed', {'metadata_sha256': digest(authors)})

    def tearDown(self):
        self.f.tearDown()

    def pin(self):
        manifest = {'version': 'adjudicated-publication-view-1',
                    'parent': source_reference(screen.Workflow(self.parent)),
                    'adjudication': source_reference(screen.Workflow(self.child))}
        self.f.write('reports/view/release-view.json', manifest)
        log = self.view/'publication-log.jsonl'
        if log.exists(): log.unlink()
        EventLog(log).add('publication_view_started', {'manifest_sha256': digest(manifest)})

    def test_exact_review_supersession_publishes_without_mutating_sources(self):
        before = {p:p.read_bytes() for folder in [self.parent,self.child] for p in folder.rglob('*') if p.is_file()}
        data = publish.build_snapshot(self.view)['papers.json']
        self.assertEqual(data['candidate_count'], 1)
        self.assertEqual(data['screening_counts']['review'], 0)
        self.assertEqual(data['papers'][0]['assessment_sha256'], digest(screen.Workflow(self.child).assessments()[0]))
        self.assertEqual(before, {p:p.read_bytes() for p in before})

    def test_source_file_tampering_rejected(self):
        (self.child/'parent-manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Pinned publication source changed'):
            PublicationView(self.view)

    def test_source_log_advancement_requires_new_explicit_view(self):
        screen.Workflow(self.parent).log.add('observation', {'message':'Synthetic new observation'})
        with self.assertRaisesRegex(ValueError, 'Pinned publication source changed'):
            PublicationView(self.view)

    def test_previous_assessment_binding_cannot_be_forged(self):
        c=screen.Workflow(self.child);d=deepcopy(c.assessments()[0]);d['previous_assessment_sha256']='bad'
        c.log.add('assessment_corrected',d);self.pin()
        with self.assertRaisesRegex(ValueError, 'previous assessment'):
            PublicationView(self.view)

    def test_wrong_target_set_rejected_even_with_new_pin(self):
        pm=json.loads((self.child/'parent-manifest.json').read_text());pm['targets']=[]
        self.f.write('reports/child/parent-manifest.json',pm);self.pin()
        with self.assertRaisesRegex(ValueError, 'exactly the parent review set'):
            PublicationView(self.view)

    def test_unresolved_child_cannot_publish(self):
        c=screen.Workflow(self.child);c.log.add('assessment_corrected',{**c.assessments()[0],'category':'review'});self.pin()
        with self.assertRaisesRegex(ValueError, 'unresolved verdict'):
            PublicationView(self.view)

    def test_resolved_parent_cannot_be_overridden(self):
        p=screen.Workflow(self.parent);p.log.add('assessment_corrected',{**p.assessments()[0],'category':'excluded'})
        pm=json.loads((self.child/'parent-manifest.json').read_text());pm['parent_log_head']=p.log.head
        self.f.write('reports/child/parent-manifest.json',pm);self.pin()
        with self.assertRaisesRegex(ValueError, 'exactly the parent review set'):
            PublicationView(self.view)

    def test_source_inventory_binding_checked(self):
        c=screen.Workflow(self.child);c.log.add('assessment_corrected',{**c.assessments()[0],'candidate_sha256':'wrong'});self.pin()
        with self.assertRaisesRegex(ValueError, 'inventory binding mismatch'):
            PublicationView(self.view)


if __name__ == '__main__': unittest.main()
