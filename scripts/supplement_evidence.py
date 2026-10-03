"""Bounded supplementation of a frozen unresolved queue; no semantic classifier."""
import argparse, copy, json, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from screen_candidates import Workflow, BufferedLog, digest, now, ROOT

OUT=None
WORK=None
AUTHORIZATION=None

class Supplement(Workflow):
    def fetch(self, channel):
        # Bounded retry is authorized only by the fixed-cohort coordinator.
        self.authorized_supplement_route = True
        return super().fetch(channel)

    def current_material(self):
        view=object.__new__(Workflow)
        events=[e for e in self.log.events if not(e['kind']=='material_cached'
                and e['data']['doi']==self.active()
                and e.get('sequence',self.material_boundary+1)<=self.material_boundary)]
        view.__dict__={**self.__dict__,'log':BufferedLog(events)}
        return Workflow.current_material(view)

def workflow():return Workflow(OUT)
def batch(w):
    event=next(e for e in reversed(w.log.events) if e['kind']=='supplement_batch_started')
    return event['data'],0 if event['data']['phase']=='followup' else event['sequence']

def init(w):
    previous = next((e['data'] for e in w.log.events if e['kind']=='supplement_round_started'), None)
    if previous:
        manifest = json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
        if digest(manifest) != previous['manifest_sha256'] or manifest['candidate_sha256'] != w.input_sha:
            raise ValueError('Supplement manifest changed or belongs to another run')
        return
    latest={d['doi']:d for d in w.assessments()}
    deferred=list(dict.fromkeys(e['data']['doi'] for e in w.log.events if e['kind']=='material_deferred' and e['data']['doi'] not in latest))
    reviews=[d['doi'] for d in latest.values() if d['category']=='review']
    attempts={d:[] for d in deferred}
    for e in w.log.events:
        if e['kind']=='source_attempt' and e['data']['doi'] in attempts:attempts[e['data']['doi']].append(e['data'])
    incomplete=[d for d in deferred if not any(a['channel']=='publisher' for a in attempts[d])]
    groups={'incomplete':incomplete,'insufficient':reviews,'aps':[d for d in deferred if d not in incomplete and w.records[d]['journal'] in {'PRL','PRX'}],'other':[d for d in deferred if d not in incomplete and w.records[d]['journal'] not in {'PRL','PRX'}]}
    if not sum(map(len,groups.values())):
        raise ValueError('No unresolved records to supplement')
    if not AUTHORIZATION:
        raise ValueError('Record the actual user authorization before starting supplementation')
    WORK.mkdir(parents=True,exist_ok=True)
    manifest={'groups':groups,'assessment_sha256':{d:digest(latest[d]) for d in reviews},'created_at':now(),'candidate_sha256':w.input_sha}
    (WORK/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    w.log.add('supplement_round_started',{'target_dois':[d for g in groups.values() for d in g],'manifest_sha256':digest(manifest),'groups':{k:len(v) for k,v in groups.items()},'authorization':AUTHORIZATION})

def begin(w,phase,size):
    manifest=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    started=next((e['data'] for e in w.log.events if e['kind']=='supplement_round_started'),None)
    if started and (digest(manifest)!=started['manifest_sha256'] or manifest['candidate_sha256']!=w.input_sha):
        raise ValueError('Supplement manifest changed or belongs to another run')
    completed={d for e in w.log.events if e['kind']=='supplement_batch_closed' for d in e['data']['dois']}
    starts=[e for e in w.log.events if e['kind']=='supplement_batch_started'];closed={e['data']['batch_id'] for e in w.log.events if e['kind']=='supplement_batch_closed'}
    if any(e['data']['batch_id'] not in closed for e in starts):raise ValueError('Close current supplement batch before advancing')
    if phase=='followup':
        latest={d['doi']:d for d in w.assessments()}
        chosen=[d for group in manifest['groups'].values() for d in group
                if d not in latest or latest[d]['category']=='review'][:size]
    else:
        chosen=[d for d in manifest['groups'][phase] if d not in completed][:size]
    if not chosen:print('Phase complete');return
    ident=len(starts)+1
    w.log.add('supplement_batch_started',{'batch_id':ident,'phase':phase,'dois':chosen,'workers':4})
    print(json.dumps({'batch_id':ident,'phase':phase,'count':len(chosen)}))

def collect(w):
    b,boundary=batch(w);snapshot=list(w.log.events);stop=threading.Event()
    def job(doi):
        j=object.__new__(Supplement);j.__dict__={**w.__dict__,'log':BufferedLog(snapshot),'collection_doi':doi,'request_stop':stop,'material_boundary':boundary}
        attempts=[e['data'] for e in snapshot if e['kind']=='source_attempt' and e['data']['doi']==doi]
        previous={a['channel'] for a in attempts}
        current_attempts={a['channel'] for a in attempts if a.get('supplement_batch_id')==b['batch_id']}
        if j.current_material():return doi,[],True
        if b['phase']=='incomplete':route=[c for c in ['cache','crossref','publisher','openalex'] if c not in previous]
        else:route=['publisher']+(['openalex'] if 'openalex' not in previous else [])
        try:
            for c in route:
                if c in current_attempts:continue
                if stop.is_set() or j.current_material():break
                j.fetch(c)
        except Exception as exc:
            j.log.add('supplement_route_failed',{'doi':doi,'error_type':type(exc).__name__,'reason':str(exc)[:200]})
        for e in j.log.pending:e['data']['supplement_batch_id']=b['batch_id']
        return doi,j.log.pending,bool(j.current_material())
    found=0
    remaining=iter(b['dois'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={}
        def submit_one():
            doi=next(remaining,None)
            if doi is not None:pending[pool.submit(job,doi)]=doi
        for _ in range(4):submit_one()
        while pending:
            done,_=wait(pending,return_when=FIRST_COMPLETED)
            for f in done:
                pending.pop(f)
                doi,events,ready=f.result()
                for e in events:w.log.add(e['kind'],{**e['data'],'observed_at':e['at']})
                found+=ready
                print(json.dumps({'doi':doi,'material_ready':ready}),flush=True)
                if not stop.is_set():submit_one()
        if stop.is_set():
            for doi in remaining:
                w.log.add('supplement_route_stopped',{'doi':doi,'supplement_batch_id':b['batch_id'],'result':'not_started_rate_limit','request_made':False})
    print(json.dumps({'count':len(b['dois']),'material_ready':found,'rate_limited':stop.is_set()}))

def pack(w):
    b,boundary=batch(w)
    for i,doi in enumerate(b['dois']):
        j=object.__new__(Supplement);j.__dict__={**w.__dict__,'collection_doi':doi,'material_boundary':boundary}
        r=w.records[doi];m=j.current_material()
        print(json.dumps({'i':i,'doi':doi,'journal':r['journal'],'title':r['title'],'publisher_records':r.get('publisher_records'),'material':m,'issues':r['issues'],'date':r['date'],'date_basis':r['date_basis']},ensure_ascii=False))

def save(w,path):
    b,boundary=batch(w);decisions=json.loads(Path(path).read_text(encoding='utf-8'));latest={d['doi']:d for d in w.assessments()}
    for d in decisions:
        doi=d['doi'];assert doi in b['dois']
        j=object.__new__(Supplement);j.__dict__={**w.__dict__,'collection_doi':doi,'material_boundary':boundary,'log':BufferedLog(w.log.events)};j.log.head=w.log.head
        j.decide(d);new=j.log.pending[-1]['data'];new['supplement_batch_id']=b['batch_id']
        if doi in latest:
            new.update(previous_assessment_sha256=digest(latest[doi]),correction_reason='User-authorized targeted supplementation; historical material and assessment retained')
            w.log.add('assessment_corrected',new)
        else:
            w.log.add('paper_started',{'doi':doi,'record_sha256':digest(w.records[doi]),'supplement_batch_id':b['batch_id']});w.log.add('assessment',new)
    print('Saved',len(decisions))

def close(w):
    b,boundary=batch(w);resolved={e['data']['doi'] for e in w.log.events if e['kind'] in {'assessment','assessment_corrected','supplement_deferred'} and e['data'].get('supplement_batch_id')==b['batch_id']}
    for doi in b['dois']:
        if doi not in resolved:
            j=object.__new__(Supplement);j.__dict__={**w.__dict__,'collection_doi':doi,'material_boundary':boundary}
            if j.current_material():raise ValueError('Ready material needs an actual saved assessment before closing: '+doi)
            w.log.add('supplement_deferred',{'doi':doi,'supplement_batch_id':b['batch_id'],'reason':'No new decision: explicit official abstract or non-target type still required; no title-only exclusion','subject_scope_status':'review' if doi in {d['doi'] for d in w.assessments()} else 'not_assessed'})
    saved={e['data']['doi'] for e in w.log.events if e['kind'] in {'assessment','assessment_corrected'} and e['data'].get('supplement_batch_id')==b['batch_id']}
    w.log.add('supplement_batch_closed',{'batch_id':b['batch_id'],'dois':b['dois'],'decisions_saved':len(saved),'deferred':len(b['dois'])-len(saved)})

def main():
    global OUT, WORK, AUTHORIZATION
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['init','begin','collect','pack','save','close'])
    ap.add_argument('--phase', choices=['incomplete','insufficient','aps','other','followup'])
    ap.add_argument('--size', type=int, default=30)
    ap.add_argument('--path')
    ap.add_argument('--run', required=True, type=Path)
    ap.add_argument('--authorization', help='Actual task authorization; required for init')
    args = ap.parse_args()
    if args.command == 'begin' and (not args.phase or not 1 <= args.size <= 100):
        ap.error('begin requires a phase and size from 1 to 100')
    if args.command == 'save' and not args.path:
        ap.error('save requires --path')
    OUT = args.run.resolve()
    WORK = ROOT/'.private/work/supplement'/OUT.relative_to((ROOT/'reports').resolve())
    AUTHORIZATION = args.authorization
    w = workflow()
    if args.command == 'init':init(w)
    elif args.command == 'begin':begin(w,args.phase,args.size)
    elif args.command == 'collect':collect(w)
    elif args.command == 'pack':pack(w)
    elif args.command == 'save':save(w,args.path)
    elif args.command == 'close':close(w)

if __name__ == '__main__':
    main()
