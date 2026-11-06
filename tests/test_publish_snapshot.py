"""Reject corrupted or untraceable author metadata before public export."""
from copy import deepcopy
from pathlib import Path
import sys
import json
import hashlib
import tempfile
from types import SimpleNamespace
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from publish_snapshot import author_record, editorial_reference, continued_editorial_reference, publication_evidence, ROOT
from screen_candidates import digest

class AuthorMetadataTests(unittest.TestCase):
    def setUp(self):
        self.record = {'doi':'10.1/test', 'title':'Test', 'issns':['0000-0001']}
        self.row = {'doi':'10.1/test', 'record_sha256':digest(self.record),
                    'authors':['Ada Example'], 'status':'available',
                    'basis':'Matched source', 'retrieved_at':'2026-10-03T00:00:00Z',
                    'source_url':'https://example.org/authors', 'attempts':[]}
        self.rehash(self.row)

    def rehash(self, row):
        row['metadata_sha256']=digest({k:v for k,v in row.items() if k not in {'attempts','metadata_sha256'}})

    def test_valid_and_unresolved(self):
        self.assertEqual(author_record(self.row,self.record)['authors'],['Ada Example'])
        row=deepcopy(self.row);row.update(authors=[],status='unresolved');self.rehash(row)
        self.assertEqual(author_record(row,self.record)['status'],'unresolved')

    def test_record_and_content_mismatch(self):
        for key,value in [('record_sha256','wrong'),('doi','10.1/wrong'),('authors',['Altered'])]:
            row=deepcopy(self.row);row[key]=value
            if key!='authors':self.rehash(row)
            with self.subTest(key=key),self.assertRaises(ValueError):author_record(row,self.record)

    def test_placeholder_and_missing_source_rejected(self):
        for change in [{'authors':['Anonymous']},{'authors':[]},{'source_url':'javascript:alert(1)'},{'retrieved_at':''},{'status':'unresolved'}]:
            row=deepcopy(self.row);row.update(change);self.rehash(row)
            with self.subTest(change=change),self.assertRaises(ValueError):author_record(row,self.record)


class PublicationEvidenceTests(unittest.TestCase):
    def editorial_continuation_fixture(self):
        record={'doi':'10.1/test','title':'Synthetic title','journal':'PRE','issns':['0000-0001']}
        verdict={'doi':record['doi'],'title':record['title'],'record_sha256':digest(record),
            'candidate_sha256':'old-pool','verdict':'include','authority':'human user in current conversation',
            'user_statement':'Keep this named paper as related reading.','scope_exception':True,
            'entry_kind':'editorial_related_reading','not_a_global_scope_rule':True}
        basis={'verdict_sha256':digest(verdict),'scope_exception':True,'entry_kind':'editorial_related_reading',
            'not_a_global_scope_rule':True,'category_semantics':'Non-core individual related reading.'}
        old={'doi':record['doi'],'category':'transferable_application','input_sha256':'old-input','editorial_basis':basis}
        events=[{'kind':'user_editorial_verdict','data':verdict}]
        source=SimpleNamespace(out=ROOT/'reports/synthetic-old',records={record['doi']:record},
            input_sha='old-pool',assessments=lambda:[old],log=SimpleNamespace(events=events))
        current_record={**record,'date':'2026-11-05'}
        current={'doi':record['doi'],'category':old['category'],'record_sha256':digest(current_record),
            'candidate_sha256':'new-pool','input_sha256':'new-input',
            'editorial_basis':{'verdict_sha256':digest(verdict)}}
        row={'doi':record['doi'],'record_sha256':digest(current_record),'assessment_sha256':digest(current),
            'previous_record_sha256':digest(record),'previous_assessment_sha256':digest(old),
            'previous_input_sha256':old['input_sha256'],'previous_run':'reports/synthetic-old'}
        return current,current_record,events,{'audit':row,'source':source},verdict,basis

    def test_editorial_continuation_keeps_exact_statement_and_noncore_semantics(self):
        current,record,events,proof,verdict,basis=self.editorial_continuation_fixture()
        before=deepcopy((current,record,events,proof['audit']))
        self.assertEqual(continued_editorial_reference(current,record,'new-pool',events,proof),(verdict,basis))
        self.assertEqual(before,(current,record,events,proof['audit']))
        with self.assertRaisesRegex(ValueError,'inventory identity'):
            editorial_reference(current,record,'new-pool',events)
        # A later ordinary carryover follows the already verified chain.
        source=SimpleNamespace(out=ROOT/'reports/synthetic-next',records={record['doi']:record},input_sha='new-pool',
            assessments=lambda:[current],log=SimpleNamespace(events=events))
        nxt={**current,'candidate_sha256':'next-pool','input_sha256':'next-input'}
        row={**proof['audit'],'assessment_sha256':digest(nxt),'previous_run':'reports/synthetic-next',
            'previous_record_sha256':digest(record),'previous_assessment_sha256':digest(current),
            'previous_input_sha256':current['input_sha256']}
        self.assertEqual(continued_editorial_reference(nxt,record,'next-pool',events,
            {'audit':row,'source':source,'previous':proof}),(verdict,basis))

    def test_editorial_continuation_rejects_changed_classification_or_unbound_history(self):
        for key in ['record_sha256','assessment_sha256','previous_record_sha256',
                    'previous_assessment_sha256','previous_input_sha256','previous_run']:
            current,record,events,proof,_,_=self.editorial_continuation_fixture()
            proof['audit'][key]='wrong'
            with self.subTest(key=key),self.assertRaises(ValueError):
                continued_editorial_reference(current,record,'new-pool',events,proof)
        current,record,events,proof,_,_=self.editorial_continuation_fixture()
        for changed in [{**current,'category':'core'},
                        {**current,'editorial_basis':{'verdict_sha256':'other-user-decision'}}]:
            row={**proof['audit'],'assessment_sha256':digest(changed)}
            with self.assertRaises(ValueError):continued_editorial_reference(changed,record,'new-pool',events,{**proof,'audit':row})
        with self.assertRaises(ValueError):continued_editorial_reference(current,record,'wrong-pool',events,proof)
        with self.assertRaises(ValueError):continued_editorial_reference(current,record,'new-pool',[],proof)

    def test_editorial_exception_bound_to_verdict_and_inventory(self):
        record={'doi':'10.1/test','title':'Synthetic title'}
        verdict={'doi':record['doi'],'title':record['title'],'record_sha256':digest(record),
            'candidate_sha256':'pool','verdict':'include','authority':'human user in current conversation',
            'user_statement':'Include this particular paper.','scope_exception':True,
            'entry_kind':'editorial_related_reading','not_a_global_scope_rule':True}
        decision={'category':'transferable_application','editorial_basis':{
            'verdict_sha256':digest(verdict),'scope_exception':True,
            'entry_kind':'editorial_related_reading','not_a_global_scope_rule':True}}
        events=[{'kind':'user_editorial_verdict','data':verdict}]
        self.assertEqual(editorial_reference(decision,record,'pool',events),verdict)
        for change in [{'doi':'10.1/wrong'},{'record_sha256':'wrong'},{'candidate_sha256':'wrong'},
                       {'verdict':'exclude'},{'authority':'assistant'},{'scope_exception':False}]:
            wrong={**verdict,**change}
            modified=deepcopy(decision);modified['editorial_basis']['verdict_sha256']=digest(wrong)
            with self.subTest(change=change),self.assertRaises(ValueError):
                editorial_reference(modified,record,'pool',[{'kind':'user_editorial_verdict','data':wrong}])
        with self.assertRaises(ValueError):editorial_reference({**decision,'category':'core'},record,'pool',events)
        with self.assertRaises(ValueError):editorial_reference(decision,record,'pool',[])

    def test_supplement_hash_and_audit_required_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);source=out/'supplement.json';source.write_text('{"original_flags_unchanged":true}')
            evidence={'candidate_sha256':'pool','files':[{'path':'supplement.json',
                'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}]}
            path=out/'publication-evidence.json';path.write_text(json.dumps(evidence))
            w=SimpleNamespace(out=out,input_sha='pool',log=SimpleNamespace(events=[]))
            with self.assertRaisesRegex(ValueError,'audit binding'):publication_evidence(w)
            w.log.events=[{'kind':'publication_evidence_selected','data':{'evidence_sha256':digest(evidence)}}]
            self.assertEqual(publication_evidence(w),evidence)
            before=path.read_bytes()
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError,'evidence changed'):publication_evidence(w)
            self.assertEqual(path.read_bytes(),before)
