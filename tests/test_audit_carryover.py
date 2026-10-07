"""Synthetic daily handoff failures and explicit overlapping release tests."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import test_run_inputs as fixtures
import audit_carryover as audit
import screen_candidates as screen
import publish_snapshot as publish
from publication_view import source_reference
from report_io import file_sha


class CarryoverTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RunTests(); self.f.setUp()
        self.root_patch = patch.object(audit,'ROOT',self.f.root); self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop(); self.f.tearDown()

    def seal(self, path, carryover=None):
        w = screen.Workflow(path)
        value = {'version':'flat-publication-1','inventory':source_reference(w),'revisions':[],
                 'authors':{'file':'author-metadata.json',
                    'metadata_sha256':screen.digest(json.loads((path/'author-metadata.json').read_text())),
                    'audit':{'path':(path/'screening-log.jsonl').relative_to(self.f.root).as_posix(),
                             'sha256':file_sha(path/'screening-log.jsonl')}}}
        if carryover:
            value['carryover_audit'] = carryover
        self.f.write(path.relative_to(self.f.root).as_posix()+'/publication.json',value)

    def pair(self, same_doi=False):
        previous = self.f.make_run('previous','10.1/a'); self.seal(previous)
        current = self.f.make_run('current','10.1/a' if same_doi else '10.1/b',
                                  window_start='2026-09-30',window_end='2026-10-01')
        return previous,current

    def bind_audit(self, previous, current):
        w = screen.Workflow(current); value = audit.build_audit(w,[previous])
        self.assertEqual(value['blockers'],[])
        (current/'evidence').mkdir()
        self.f.write('reports/current/evidence/cross-run-audit.json',value)
        w.log.add('carryover_audit_completed',{'audit_sha256':screen.digest(value)})
        self.seal(current,{'file':'evidence/cross-run-audit.json',
                           'sha256':file_sha(current/'evidence/cross-run-audit.json')})

    def test_explicit_overlap_preserves_old_inclusion_and_hashes(self):
        old,new = self.pair(); self.bind_audit(old,new)
        before = {p:p.read_bytes() for p in old.rglob('*') if p.is_file()}
        data = publish.build_release([old,new])['papers.json']
        self.assertEqual({p['doi'] for p in data['papers']},{'10.1/a','10.1/b'})
        self.assertEqual(data['candidate_count'],2)
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertEqual(data['carryover_audits'][0]['counts']['newly_reviewed'],1)

    def test_same_doi_requires_explicit_binding_and_never_duplicates(self):
        old,new = self.pair(True)
        with self.assertRaisesRegex(ValueError,'superseded assessment|Conflicting candidate'):
            publish.build_release([old,new])
        self.bind_audit(old,new)
        data = publish.build_release([old,new])['papers.json']
        self.assertEqual(len(data['papers']),1)
        self.assertEqual(data['papers'][0]['date'],'2026-09-30')
        self.assertEqual(data['candidate_count'],1)
        saved = json.loads((new/'evidence/cross-run-audit.json').read_text())
        saved['records'][0]['previous_assessment_sha256']='forged'
        self.f.write('reports/current/evidence/cross-run-audit.json',saved)
        with self.assertRaisesRegex(ValueError,'audit file binding'):
            publish.build_release([old,new])

    def test_out_of_window_registered_only_is_not_reviewed(self):
        record={'doi':'10.1/a','title':'Synthetic','journal':'J','issns':['0000-0001'],
                'date':'2026-09-29','window_membership':'out_of_window'}
        rows,blockers=audit.compare_history({record['doi']:record},{},{},'2026-09-01','2026-10-01')
        self.assertEqual(rows[0]['history_status'],'missing_history')
        self.assertIn('no effective historical assessment',blockers[0]['reason'])
        rows,blockers=audit.compare_history({None:record},{},{},'2026-09-01','2026-10-01')
        self.assertTrue(blockers)

    def test_same_window_refresh_keeps_prior_inventory_and_new_paper(self):
        old = self.f.make_run('previous','10.1/a'); self.seal(old)
        new = self.f.make_run('current','10.1/b')
        # Rebuild only this synthetic, unsealed fixture with both current observations.
        old_w,new_w=screen.Workflow(old),screen.Workflow(new)
        previous_record=old_w.records['10.1/a']
        original_decision=new_w.assessments()[0]
        pool=json.loads((new/'candidates.json').read_text())
        pool['records'].append(previous_record)
        self.f.write('reports/current/candidates.json',pool)
        coverage=json.loads((new/'coverage.json').read_text())
        coverage['journals']['J'].update(window_inventory_count=2,publisher_verified_inventory_count=2)
        self.f.write('reports/current/coverage.json',coverage)
        (new/'screening-log.jsonl').unlink()
        new_w=screen.Workflow(new);new_w.init()
        for decision in [original_decision,old_w.assessments()[0]]:
            new_w.log.add('paper_started',{'doi':decision['doi']});new_w.log.add('assessment',decision)
        metadata=json.loads((new/'author-metadata.json').read_text())
        metadata['candidate_sha256']=new_w.input_sha
        metadata['records']['10.1/a']=json.loads((old/'author-metadata.json').read_text())['records']['10.1/a']
        self.f.write('reports/current/author-metadata.json',metadata)
        new_w.log.add('author_metadata_completed',{'metadata_sha256':screen.digest(metadata)})
        self.bind_audit(old,new)
        data=publish.build_release([old,new])['papers.json']
        self.assertEqual({p['doi'] for p in data['papers']},{'10.1/a','10.1/b'})
        self.assertEqual(data['coverage'][0]['candidate_count'],2)
        self.assertEqual(len(data['coverage'][0]['windows'][0]['observations']),2)

    def test_missing_previously_published_overlap_record_blocks_refresh(self):
        old=self.f.make_run('previous','10.1/a');self.seal(old)
        new=self.f.make_run('current','10.1/b')
        result=audit.build_audit(screen.Workflow(new),[old])
        self.assertTrue(any('absent from current full inventory' in b['reason'] for b in result['blockers']))

    def test_category_change_is_not_a_metadata_update(self):
        old,new = self.pair(True)
        w=screen.Workflow(new)
        w.log.add('assessment_corrected',{**w.assessments()[0],'category':'excluded'})
        result=audit.build_audit(screen.Workflow(new),[old])
        self.assertTrue(any('category change' in b['reason'] for b in result['blockers']))

    def test_accepted_transition_is_traced_without_reclassifying(self):
        record={'doi':'10.1/a','title':'Synthetic','journal':'J','issns':['0000-0001'],
                'date':'2026-09-30','window_membership':'in_window'}
        old={'category':'core','input_sha256':'old','hard_checks':{'date':{'basis':'publisher.accepted'}}}
        new={**old,'input_sha256':'new','hard_checks':{'date':{'publication_status':'published'}}}
        rows,blockers=audit.compare_history({'10.1/a':record},{'10.1/a':new},
            {'10.1/a':{'run':'reports/old','record':record,'decision':old}},'2026-09-01','2026-10-01')
        self.assertFalse(blockers)
        self.assertTrue(rows[0]['publication_status_changed'])
        self.assertEqual(rows[0]['previous_assessment_sha256'],screen.digest(old))

    def test_gap_or_missing_overlap_does_not_become_complete(self):
        old,new = self.pair()
        w=screen.Workflow(new)
        w.pool=deepcopy(w.pool);w.pool['window_start']='2026-10-01'
        result=audit.build_audit(w,[old])
        self.assertTrue(any('previous cutoff' in b['reason'] for b in result['blockers']))

    def transition_fixture(self, previous_category='core'):
        old={'doi':'10.1/a','category':previous_category,
             'hard_checks':{'date':{'value':'2026-09-02','publication_status':'accepted'}}}
        new={'doi':'10.1/a','category':previous_category,
             'hard_checks':{'date':{'value':'2026-09-30','publication_status':'published'}}}
        histories={'reports/old':{'10.1/a':old},'reports/new':{'10.1/a':new}}
        row={'doi':'10.1/a','publication_status_changed':True,
             'previous_publication_status':'accepted','publication_status':'published',
             'previous_category':previous_category,'category':previous_category,
             'previous_run':'reports/old','previous_assessment_sha256':screen.digest(old),
             'assessment_sha256':screen.digest(new)}
        audits=[{'current_run':'reports/new','records':[row]}]
        papers={'10.1/a':{'publication_status':'published','published_date':'2026-09-30'}}
        return papers,audits,histories

    def test_transition_keeps_original_dates_and_bound_history(self):
        papers,audits,histories=self.transition_fixture()
        transitions=publish.publication_transitions(papers,audits,histories)
        self.assertEqual(papers['10.1/a']['accepted_date'],'2026-09-02')
        self.assertEqual(transitions['10.1/a']['audit_sha256'],screen.digest(audits[0]))
        self.assertEqual(len(papers),1)
        with self.assertRaisesRegex(ValueError,'binding mismatch'):
            histories['reports/old']['10.1/a']['hard_checks']['date']['value']='2026-09-01'
            publish.publication_transitions(papers,audits,histories)

    def test_excluded_transitions_and_unlisted_dois_get_no_badge(self):
        papers,audits,histories=self.transition_fixture('excluded')
        self.assertEqual(publish.publication_transitions(papers,audits,histories),{})
        self.assertNotIn('publication_transition',papers['10.1/a'])
        papers,audits,histories=self.transition_fixture()
        self.assertEqual(publish.publication_transitions({},audits,histories),{})

    def test_invalid_transition_chronology_is_rejected(self):
        papers,audits,histories=self.transition_fixture()
        histories['reports/old']['10.1/a']['hard_checks']['date']['value']='2026-10-01'
        audits[0]['records'][0]['previous_assessment_sha256']=screen.digest(histories['reports/old']['10.1/a'])
        with self.assertRaisesRegex(ValueError,'precedes accepted'):
            publish.publication_transitions(papers,audits,histories)


if __name__=='__main__':
    unittest.main()
