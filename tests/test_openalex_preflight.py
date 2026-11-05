"""Offline integration checks for persisted preflight and cross-worker failure latches."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.error import HTTPError, URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import screen_candidates as s
import supplement_evidence as supplement


class Response:
    status=200
    url='https://api.openalex.org/rate-limit'
    headers={}
    def __init__(self, payload=None, headers=None):
        self.payload=payload if payload is not None else {'api_key':'must-never-persist', 'rate_limit':{'daily_budget_usd':1,'daily_remaining_usd':1,'credits_remaining':10000,'resets_in_seconds':500,'email':'private@example.org'}}
        self.headers=headers or {}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,limit):return json.dumps(self.payload).encode()


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'preflight.json'
        for p in [patch.dict(os.environ,{'OPENALEX_API_KEY':'test-token'},clear=True),patch.object(s,'ROOT',self.root)]:
            p.start();self.addCleanup(p.stop)
    def workflow(self, gate, doi='10.1/example', stop=None):
        w=object.__new__(s.Workflow);w.records={doi:{'doi':doi,'title':'A study','issns':['0000-0001']}}
        w.collection_doi=doi;w.log=s.BufferedLog([]);w.request_stop=stop or threading.Event()
        w.current_material=lambda:None;w.next=lambda:{};w.openalex_access=gate
        for channel in ['cache','crossref','publisher']:w.attempt(channel,None,'missing')
        return w
    def ready(self):
        gate=s.OpenAlexAccess(self.path)
        with patch.object(s,'urlopen',return_value=Response()):gate.check(refresh=True)
        return gate
    def test_preflight_is_singleton_persisted_and_only_whitelists_quota(self):
        gate=s.OpenAlexAccess(self.path);log=s.BufferedLog([])
        with patch.object(s,'urlopen',return_value=Response()) as request:
            with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:gate.check(),range(8)))
            gate.check(log);s.OpenAlexAccess(self.path).check(log)
        self.assertEqual(request.call_count,1)
        self.assertEqual(len(log.events),1)
        self.assertEqual(gate.result['status'],'ready')
        self.assertEqual(gate.result['authentication'],'api_key')
        public=self.path.read_text()+json.dumps(log.events)
        for value in ['test-token','must-never-persist','private@example.org']:self.assertNotIn(value,public)
        self.assertEqual(request.call_args.args[0].get_header('Authorization'),'Bearer test-token')
    def test_failed_preflight_suppresses_all_papers_and_restored_process(self):
        for status in [401,403,429,500]:
            with self.subTest(status=status):
                gate=s.OpenAlexAccess();stop=threading.Event()
                error=HTTPError('https://api.openalex.org/rate-limit',status,'test-token',{},None)
                with patch.object(s,'urlopen',side_effect=error) as request:
                    gate.check(stop=stop)
                    jobs=[self.workflow(gate,f'10.1/{i}',stop) for i in range(5)]
                    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda w:w.fetch('openalex'),jobs))
                self.assertEqual(request.call_count,1)
                self.assertEqual(stop.is_set(),status==429)
                self.assertTrue(all(any(e['kind']=='source_attempt' and e['data'].get('request_made') is False for e in w.log.events) for w in jobs))
                self.assertNotIn('test-token',json.dumps([w.log.events for w in jobs]))
        gate=s.OpenAlexAccess(self.path)
        with patch.object(s,'urlopen',side_effect=HTTPError('https://api.openalex.org/rate-limit',401,'bad',{},None)) as request:gate.check()
        with patch.object(s,'urlopen',side_effect=AssertionError('Must not retry on CLI resume')):s.OpenAlexAccess(self.path).check()
    def test_quota_zero_unknown_and_transport_failure_are_not_ready(self):
        for payload,status in [({'rate_limit':{'credits_remaining':0}},'quota_exhausted'),({'rate_limit':{}},'quota_unknown'),({'rate_limit':None},'unavailable'),([], 'unavailable')]:
            gate=s.OpenAlexAccess()
            with patch.object(s,'urlopen',return_value=Response(payload)):self.assertEqual(gate.check()['status'],status)
        with patch.object(s,'urlopen',side_effect=URLError('sensitive redirect URL')):
            result=s.OpenAlexAccess().check()
        self.assertEqual(result['status'],'unavailable');self.assertNotIn('sensitive',json.dumps(result))
    def test_invalid_credentials_are_checked_once_without_network(self):
        gate=s.OpenAlexAccess()
        with patch.dict(os.environ,{'OPENALEX_API_KEY':''}),patch.object(s,'urlopen',side_effect=AssertionError('No HTTP')):
            self.assertEqual(gate.check()['status'],'invalid_configuration')
            self.workflow(gate).fetch('openalex')
    def test_runtime_auth_failure_is_latched_before_next_worker(self):
        for status in [401,403,429]:
            gate=self.ready();stop=threading.Event();jobs=[self.workflow(gate,f'10.1/{i}',stop) for i in range(8)]
            with patch.object(s,'urlopen',side_effect=HTTPError('https://api.openalex.org/works/example',status,'test-token',{},None)) as request:
                with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda w:w.fetch('openalex'),jobs))
            self.assertEqual(request.call_count,1);self.assertEqual(stop.is_set(),status==429)
            self.assertEqual(gate.result['status'],'rate_limited' if status==429 else 'auth_failed')
            self.assertNotIn('test-token',self.path.read_text()+json.dumps([w.log.events for w in jobs]))
    def test_404_does_not_disable_other_doi_requests(self):
        gate=self.ready()
        with patch.object(s,'urlopen',side_effect=HTTPError('https://api.openalex.org/works/example',404,'Not found',{},None)) as request:
            for i in range(2):self.workflow(gate,f'10.1/{i}').fetch('openalex')
        self.assertEqual(request.call_count,2);self.assertEqual(gate.result['status'],'ready')
    def test_runtime_quota_depletion_keeps_successful_material_but_stops_next_request(self):
        gate=self.ready();w=self.workflow(gate);saved=[];w.cache=saved.append
        paper={'doi':'https://doi.org/10.1/example','title':'A study','locations':[{'source':{'issn':['0000-0001']}}],'abstract_inverted_index':{'Explicit':[0],'abstract.':[1]}}
        with patch.object(s,'urlopen',return_value=Response(paper,{'x-ratelimit-remaining':'0'})) as request:
            w.fetch('openalex');self.workflow(gate,'10.1/second').fetch('openalex')
        self.assertEqual(request.call_count,1);self.assertEqual(len(saved),1);self.assertEqual(gate.result['status'],'quota_exhausted')
    def test_next_day_rechecks_and_explicit_auth_refresh_but_never_same_day_429(self):
        gate=s.OpenAlexAccess(self.path)
        with patch.object(s,'now',return_value='2026-11-05T00:00:00+00:00'),patch.object(s,'urlopen',return_value=Response()) as request:
            gate.check();gate.check();self.assertEqual(request.call_count,1)
        with patch.object(s,'now',return_value='2026-11-06T00:00:00+00:00'),patch.object(s,'urlopen',return_value=Response()) as request:
            gate.check();self.assertEqual(request.call_count,1)
            gate.result['status']='auth_failed';gate.check(refresh=True);self.assertEqual(request.call_count,2)
            gate.result['status']='rate_limited'
            with self.assertRaisesRegex(ValueError,'429'):gate.check(refresh=True)
            self.assertEqual(request.call_count,2)
    def test_skipped_channel_can_resume_after_explicit_successful_preflight(self):
        gate=self.ready();gate.result['status']='auth_failed';w=self.workflow(gate);saved=[];w.cache=saved.append
        with patch.object(s,'urlopen',side_effect=AssertionError('Disabled channel')):w.fetch('openalex')
        paper={'doi':'https://doi.org/10.1/example','title':'A study','locations':[{'source':{'issn':['0000-0001']}}],'abstract_inverted_index':{'Explicit':[0],'abstract.':[1]}}
        with patch.object(s,'urlopen',side_effect=[Response(),Response(paper)]) as request:
            gate.check(refresh=True);w.fetch('openalex')
        self.assertEqual(request.call_count,2);self.assertEqual(len(saved),1)
        self.assertTrue(any(e['data'].get('result')=='skipped_openalex_preflight' for e in w.log.events))

    def test_anonymous_preflight_and_corrupt_state_fail_closed(self):
        with patch.dict(os.environ,{},clear=True),patch.object(s,'urlopen',return_value=Response()) as request:
            gate=s.OpenAlexAccess(self.path);self.assertEqual(gate.check()['authentication'],'anonymous')
            self.assertIsNone(request.call_args.args[0].get_header('Authorization'))
        data=json.loads(self.path.read_text());data['api_key']='must-not-enter-public-log';self.path.write_text(json.dumps(data))
        with patch.object(s,'urlopen',side_effect=AssertionError('No HTTP')),self.assertRaisesRegex(ValueError,'Invalid private'):
            s.OpenAlexAccess(self.path).check(s.BufferedLog([]))

    def test_preflight_cli_can_run_before_inventory_without_mutating_formal_files(self):
        out=self.root/'reports/runs/future-run'
        args=['screen_candidates.py','--out',str(out),'preflight']
        with patch.object(sys,'argv',args),patch.object(s,'urlopen',return_value=Response()),contextlib.redirect_stdout(io.StringIO()):s.main()
        self.assertFalse(out.exists());self.assertTrue((self.root/'.private/work/future-run/openalex-preflight.json').exists())
    def test_regular_and_supplement_batches_preflight_before_submitting_any_http_after_429(self):
        for supplement_mode in [False,True]:
            w=object.__new__(s.Workflow);w.log=s.BufferedLog([]);w.records={};w.out=self.root/'future'
            dois=['10.1/a','10.1/b']
            w.records={d:{'doi':d,'title':'A study','window_membership':'in_window','publisher_records':[]} for d in dois}
            if supplement_mode:
                w.log.add('supplement_batch_started',{'batch_id':1,'phase':'incomplete','dois':dois});w.log.events[-1]['sequence']=1;action=lambda:supplement.collect(w)
            else:
                w.log.add('run_started',{'batch_dois':dois});action=lambda:w.collect_batch(4)
            w.openalex_access=s.OpenAlexAccess()
            with patch.object(s,'urlopen',side_effect=HTTPError('https://api.openalex.org/rate-limit',429,'rate limit',{},None)) as request,contextlib.redirect_stdout(io.StringIO()):action()
            self.assertEqual(request.call_count,1)
            self.assertFalse(any(e['kind']=='assessment' for e in w.log.events))
            stopped=[e for e in w.log.events if e['data'].get('result')=='not_started_rate_limit']
            self.assertEqual({e['data']['doi'] for e in stopped},set(dois))

if __name__=='__main__':unittest.main()
