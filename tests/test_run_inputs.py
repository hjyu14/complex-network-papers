"""Offline run isolation and release union checks; no real scientific verdicts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import screen_candidates as screen
import publish_snapshot as publish
from run_inputs import freeze_inputs, load_inputs, digest

class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ['config', 'docs', 'reports']:
            (self.root/name).mkdir()
        self.config = {'screening_protocol':'docs/screening-protocol.md',
            'initial_trial':{'start':'2026-09-01','end':'2026-09-30'},
            'featured_journals':['J'],
            'journals':[{'short':'J','name':'Synthetic Journal','issns':['0000-0001']},
                        {'short':'K','name':'Synthetic Extra','issns':['0000-0002']}]}
        self.write('config/sources.json', self.config)
        (self.root/'docs/screening-protocol.md').write_text('Synthetic rules, not a real review.', encoding='utf8')
        self.notes = {'categories':[{'id':'other','name':'Other'}], 'papers':{}}
        self.patches = [patch.object(screen,'ROOT',self.root), patch.object(publish,'ROOT',self.root)]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def write(self, rel, value):
        (self.root/rel).write_text(json.dumps(value, ensure_ascii=False)+'\n',encoding='utf8')

    def make_run(self, name, doi, journal='J', category='core', window_end='2026-09-30'):
        out=self.root/'reports'/name;out.mkdir()
        cfg=deepcopy(self.config);cfg['initial_trial']['end']=window_end
        self.write('config/sources.json',cfg)
        freeze_inputs(out,self.root,[journal])
        j=next(j for j in cfg['journals'] if j['short']==journal)
        record={'doi':doi,'title':'Synthetic network study '+doi,'issns':j['issns'],
                'journal':journal,'window_membership':'in_window','date':'2026-09-03',
                'date_basis':'published-online','issues':[]}
        self.write(f'reports/{name}/candidates.json',{'window_start':'2026-09-01','window_end':window_end,'records':[record]})
        self.write(f'reports/{name}/coverage.json',{'journals':{journal:{
            'window_inventory_count':1,'publisher_verified_inventory_count':1,
            'candidate_inventory_complete':True,'metadata_reconciliation_complete':True}},
            'nine_journal_inventory_complete':True,'nine_journal_reconciliation_complete':True})
        (out/'collection-log.jsonl').write_text('',encoding='utf8')
        w=screen.Workflow(out);w.init()
        hard={'identity':{'status':'verified'},'type':{'status':'verified','value':'Article'},
              'date':{'status':'verified','value':'2026-09-03','source_url':'https://example.org/paper'}}
        material=hashlib.sha256(('synthetic material '+doi).encode()).hexdigest()
        d={'doi':doi,'category':category,'hard_checks':hard,'rule_sha256':w.rule_sha,
           'material_sha256':material,'material_source':'https://example.org/paper',
           'review_basis':'Synthetic fixture, not actual screening','evidence_summary':'Synthetic network evidence.'}
        d['input_sha256']=digest({'record':record,'material_sha256':material,'hard_checks':hard,'rule_sha256':w.rule_sha})
        w.log.add('paper_started',{'doi':doi});w.log.add('assessment',d)
        authors={}
        if category=='core':
            row={'doi':doi,'record_sha256':digest(record),'authors':['Ada Example'],'status':'available',
                 'source_url':'https://example.org/paper','retrieved_at':'2026-10-03T00:00:00Z',
                 'basis':'Synthetic source','attempts':[]}
            row['metadata_sha256']=digest({k:v for k,v in row.items() if k not in {'attempts','metadata_sha256'}})
            authors[doi]=row
            self.notes['papers'][doi]={'assessment_sha256':digest(d),'categories':['other'],
                'note_en':'This synthetic fixture tests a network method without asserting real scientific results.',
                'note_zh':'仅为离线测试夹具。'}
        author_data={'candidate_sha256':w.input_sha,'records':authors}
        self.write(f'reports/{name}/author-metadata.json',author_data)
        w.log.add('author_metadata_completed',{'metadata_sha256':digest(author_data)})
        self.write('config/publication-notes.json',self.notes)
        return out

    def test_old_run_survives_global_config_and_protocol_changes(self):
        run=self.make_run('a','10.1/a')
        old=screen.Workflow(run)
        cfg=deepcopy(self.config);cfg['journals'].append({'short':'New','name':'New','issns':['9999-9999']})
        self.write('config/sources.json',cfg)
        (self.root/'docs/screening-protocol.md').write_text('Different future rules')
        resumed=screen.Workflow(run)
        self.assertEqual(resumed.rule_sha,old.rule_sha)
        self.assertEqual(resumed.config,old.config)
        self.assertEqual(len(publish.build_snapshot(run)['papers.json']['papers']),1)

    def test_frozen_input_tampering_fails(self):
        run=self.make_run('a','10.1/a')
        (run/'inputs/screening-protocol.md').write_text('Changed')
        with self.assertRaisesRegex(ValueError,'Frozen run input changed'):screen.Workflow(run)

    def test_distinct_journals_merge_with_all_bindings(self):
        a=self.make_run('a','10.1/a');b=self.make_run('b','10.1/b','K')
        result=publish.build_release([a,b]);data=result['papers.json']
        self.assertEqual({p['doi'] for p in data['papers']},{'10.1/a','10.1/b'})
        self.assertEqual(data['candidate_count'],2)
        self.assertEqual(data['screening_counts']['included'],2)
        self.assertEqual(len(data['run_inputs']),2)
        self.assertEqual({p['journal_short'] for p in data['papers'] if p['featured']},{'J'})
        self.assertEqual(len(result['screening-report.json']['included_assessments']),2)
        for name in ['a','b']:
            self.assertEqual(load_inputs(self.root/'reports'/name)[2]['journals'],['J' if name=='a' else 'K'])

    def test_identical_duplicate_deduplicates(self):
        a=self.make_run('a','10.1/a');b=self.root/'reports/b';shutil.copytree(a,b)
        result=publish.build_release([a,b])['papers.json']
        self.assertEqual(len(result['papers']),1)
        self.assertEqual(result['candidate_count'],1)
        self.assertEqual(result['screening_counts']['core'],1)

    def test_partial_overlapping_journal_coverage_cannot_be_claimed_complete(self):
        a=self.make_run('a','10.1/a');b=self.make_run('b','10.1/b')
        with self.assertRaisesRegex(ValueError,'Conflicting journal coverage'):publish.build_release([a,b])

    def test_conflicting_duplicate_and_different_windows_fail(self):
        a=self.make_run('a','10.1/a');b=self.make_run('b','10.1/a',category='excluded')
        with self.assertRaisesRegex(ValueError,'Conflicting candidate'):publish.build_release([a,b])
        c=self.make_run('c','10.1/c','K',window_end='2026-09-29')
        with self.assertRaisesRegex(ValueError,'same date window'):publish.build_release([a,c])

    def test_unresolved_or_unassessed_run_cannot_publish(self):
        a=self.make_run('a','10.1/a',category='review')
        with self.assertRaisesRegex(ValueError,'finish classification'):publish.build_snapshot(a)
        b=self.make_run('b','10.1/b')
        w=screen.Workflow(b)
        w.log.add('assessment_corrected',{**w.assessments()[0],'category':'review'})
        with self.assertRaisesRegex(ValueError,'finish classification'):publish.build_snapshot(b)
        c=self.make_run('c','10.1/c')
        (c/'screening-log.jsonl').unlink()
        w=screen.Workflow(c);w.init()
        with self.assertRaisesRegex(ValueError,'finish classification'):publish.build_snapshot(c)

    def test_publication_missing_inputs_is_read_only(self):
        a=self.make_run('a','10.1/a')
        shutil.rmtree(a/'inputs')
        before={p.relative_to(a).as_posix():p.read_bytes() for p in a.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError,'frozen inputs'):publish.build_snapshot(a)
        after={p.relative_to(a).as_posix():p.read_bytes() for p in a.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_release_selection_rejects_empty_duplicate_and_outside_paths(self):
        for paths in [[],['reports/a','reports/a'],['../outside'],['reports/a','reports/../reports/a']]:
            self.write('config/release.json',{'runs':paths})
            with self.subTest(paths=paths),self.assertRaises(ValueError):publish.selected_runs(self.root/'config/release.json')

    def test_author_and_note_bindings_still_reject_stale_data(self):
        a=self.make_run('a','10.1/a');b=self.make_run('b','10.1/b','K')
        self.notes['papers']['10.1/a']['assessment_sha256']='stale'
        self.write('config/publication-notes.json',self.notes)
        with self.assertRaisesRegex(ValueError,'superseded assessment'):publish.build_release([a,b])
        self.notes['papers']['10.1/a']['assessment_sha256']=digest(screen.Workflow(a).assessments()[0])
        self.write('config/publication-notes.json',self.notes)
        authors=json.loads((b/'author-metadata.json').read_text());authors['records']['10.1/b']['authors']=['Changed']
        self.write('reports/b/author-metadata.json',authors)
        with self.assertRaisesRegex(ValueError,'matching audit event'):publish.build_release([a,b])

if __name__=='__main__':unittest.main()
