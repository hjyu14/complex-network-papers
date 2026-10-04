"""Frozen-policy, provenance and no-abstract editorial exclusion safeguards."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import screen_candidates as s
from run_inputs import freeze_inputs


class EditorialAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root/'reports'; self.out.mkdir()
        (self.root/'docs').mkdir(); (self.root/'config').mkdir()
        (self.root/'docs/screening-protocol.md').write_text(
            'New authorized policy: explicit_abstract_research_inference; user_editorial_verdict', encoding='utf-8')
        (self.root/'config/sources.json').write_text(json.dumps({
            'journals':[{'short':'J'}], 'screening_protocol':'docs/screening-protocol.md',
            'initial_trial':{'start':'2026-09-01','end':'2026-09-30'}}), encoding='utf-8')
        self.r = {'doi':'10.1/example','title':'Original research study','issns':['0000-0001'],
                  'journal':'J','date':'2026-09-02','date_basis':'published-online',
                  'window_membership':'in_window','issues':[],'publisher_records':[]}
        self.m = {k:self.r[k] for k in ['doi','title','issns']}
        self.m.update(source_url='https://example.org/article',retrieved_at='2026-10-04T00:00:00Z',
                      abstract_basis='publisher.Abstract', abstract='We introduce a network method and test its results.')
        self.m['abstract_sha256']=s.sha(self.m['abstract'])
        (self.out/'candidates.json').write_text(json.dumps({'window_start':'2026-09-01',
            'window_end':'2026-09-30','as_of_date':'2026-10-04','records':[self.r]}),encoding='utf-8')
        freeze_inputs(self.out,self.root)
        self.addCleanup(patch.stopall)
        patch.object(s,'ROOT',self.root).start()
        patch.object(s,'PRIVATE',self.root/'.private/abstract-cache/v9').start()
        self.w=s.Workflow(self.out)
        self.w.log.add('run_started',{'candidate_sha256':self.w.input_sha,
            'rule_sha256':self.w.rule_sha,'batch_dois':[self.r['doi']]})
        self.w.next()

    def decision(self):
        return {'doi':self.r['doi'],'category':'core','reviewer':'actual human/assistant reader',
                'reason':'Reviewed network-method contribution','evidence_summary':'Introduces and tests a network method.',
                'screening_summary':'A network method with tested results.',
                'sources':[self.m['source_url']],
                'hard_checks':{'identity':{'status':'verified'},
                    'date':{'status':'verified','value':'2026-09-02'},
                    'type':{'status':'verified','value':None,'basis_kind':'explicit_abstract_research_inference',
                        'research_nature':'original_research','basis':'Read a proposed method and explicit new results; no type conflicts.',
                        'material_sha256':s.digest(self.m),'special_type_check':'clear','specific_subtype':None,
                        'subtype_status':'not_required_for_inclusion','sources':[self.m['source_url']]}}}

    def verdict(self, **changes):
        return {'doi':self.r['doi'],'verdict':'exclude','authority':'human user in current conversation',
                'user_statement':'I reviewed this paper personally; exclude it.',
                'statement_kind':'explicit_individual_verdict','personally_reviewed':True,**changes}

    def exclusion(self, verdict):
        d=self.decision();d.update(category='excluded',exclusion_basis='user_editorial_decision',
                                  editorial_basis={'verdict_sha256':s.digest(verdict)})
        d['hard_checks']['type']={'status':'unresolved','value':None}
        return d

    def test_regular_research_subtype_can_remain_unknown(self):
        self.w.cache(self.m);self.w.decide(self.decision())
        d=self.w.assessments()[0]
        self.assertIsNone(d['hard_checks']['type']['value'])
        self.assertEqual(d['category'],'core')
        self.assertIsNone(self.w.active())

    def test_inference_needs_abstract_and_current_frozen_permission(self):
        with self.assertRaisesRegex(ValueError,'Research-nature'):
            self.w.decide(self.decision())
        self.w.cache(self.m)
        self.w.protocol='Old PRL-only frozen rule'
        with self.assertRaisesRegex(ValueError,'Research-nature'):
            self.w.decide(self.decision())

    def test_inference_hash_and_subtype_cannot_be_fabricated(self):
        self.w.cache(self.m)
        for field,value in [('material_sha256','wrong'),('value','Article'),
                            ('specific_subtype','Letter'),('special_type_check','conflict')]:
            with self.subTest(field=field):
                d=self.decision();d['hard_checks']['type'][field]=value
                with self.assertRaisesRegex(ValueError,'Research-nature'):
                    self.w.decide(d)

    def test_official_special_type_blocks_ordinary_inference(self):
        self.w.cache(self.m)
        self.w.log.add('browser_bibliography_observed',{'doi':self.r['doi'],'article_type':'Perspective'})
        with self.assertRaisesRegex(ValueError,'Research-nature'):
            self.w.decide(self.decision())

    def test_user_no_abstract_exclusion_is_attributed(self):
        verdict=self.verdict();self.w.log.add('user_editorial_verdict',verdict)
        self.w.decide(self.exclusion(verdict));d=self.w.assessments()[0]
        self.assertIsNone(d['material_sha256'])
        self.assertIn('no abstract obtained or reviewed by assistant',d['review_basis'])
        self.assertEqual(d['hard_checks']['type']['status'],'unresolved')

    def test_user_exclusion_requires_matching_doi_and_explicit_personal_review(self):
        for changes in [{'doi':'10.1/other'},{'personally_reviewed':False},
                        {'statement_kind':'editorial_direction'},{'verdict':'include'}]:
            with self.subTest(changes=changes):
                v=self.verdict(**changes);self.w.log.add('user_editorial_verdict',v)
                with self.assertRaises(ValueError):self.w.decide(self.exclusion(v))

    def test_user_exclusion_without_event_or_with_wrong_hash_rejected(self):
        v=self.verdict()
        with self.assertRaisesRegex(ValueError,'matching authorized'):
            self.w.decide(self.exclusion(v))
        self.w.log.add('user_editorial_verdict',v)
        d=self.exclusion(v);d['editorial_basis']['verdict_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'matching authorized'):self.w.decide(d)

    def test_user_inclusion_does_not_bypass_abstract_or_date_checks(self):
        v=self.verdict(verdict='include');self.w.log.add('user_editorial_verdict',v)
        d=self.decision();d['editorial_basis']={'verdict_sha256':s.digest(v)}
        with self.assertRaises(ValueError):self.w.decide(d)
        self.w.cache(self.m);d['hard_checks']['date']['status']='unresolved'
        with self.assertRaisesRegex(ValueError,'resolved hard checks'):self.w.decide(d)


if __name__=='__main__':unittest.main()
