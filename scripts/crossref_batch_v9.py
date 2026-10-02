"""Batch Crossref refresh by journal; abstracts are transient and not saved."""
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode

from collect import clean, publication_date, relevance, request_json

ROOT=Path(__file__).resolve().parents[1]

def fetch(job):
    name, issn = job
    params={'filter':'type:journal-article,from-pub-date:2026-09-01,until-pub-date:2026-09-30','rows':1000,'offset':0,'sort':'published','order':'desc','select':'DOI,title,type,ISSN,abstract,published-online,published-print,published,issued,link'}
    url='https://api.crossref.org/journals/'+issn+'/works?'+urlencode(params)
    try:
        msg=request_json(url); return name,msg.get('items',[]),None
    except Exception as exc: return name,[],type(exc).__name__

def run(out,workers=4):
    source=json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
    pending=json.loads((ROOT/'reports/v9-2026-09/screening-report.json').read_text(encoding='utf-8'))
    pending_doi={x['doi'] for x in pending['decisions'] if x['decision']=='review'}
    jobs=[(j['name'],j['issns'][0]) for j in source['journals']]
    seen={}; coverage=[]; errors=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fetch,j) for j in jobs]
        for idx,f in enumerate(as_completed(futures),1):
            name,items,error=f.result(); coverage.append({'journal':name,'retrieved':len(items),'error':error})
            if error: errors.append({'journal':name,'error':error})
            for item in items:
                doi=item.get('DOI','').lower()
                if doi in pending_doi: seen[doi]=item
            print(json.dumps({'phase':'crossref_batch','journal_index':idx,'journal_total':len(jobs),'journal':name,'retrieved':len(items),'pending_matched':len(seen)},ensure_ascii=False),flush=True)
    counts={'pending':len(pending_doi),'matched':len(seen),'abstract_found':0,'date_complete':0,'links_found':0,'direct_inclusion_signals':0,'errors':len(errors)}; results=[]
    rules=source['screening']
    for idx,doi in enumerate(sorted(pending_doi),1):
        item=seen.get(doi)
        if not item:
            results.append({'doi':doi,'status':'not_returned'}); continue
        title=clean(' '.join(item.get('title',[]))); abstract=clean(item.get('abstract','')); pub,ds=publication_date(item); links=item.get('link',[]) or []
        counts['abstract_found']+=bool(abstract); counts['date_complete']+=bool(pub); counts['links_found']+=bool(links)
        decision,routes,evidence=relevance(title,abstract,rules) if abstract else ('review_missing_abstract',[],[])
        counts['direct_inclusion_signals']+=decision=='included'
        results.append({'doi':doi,'status':'ok','title':title,'abstract_available':bool(abstract),'date':pub.isoformat() if pub else None,'date_source':ds,'link_count':len(links),'decision':'included' if decision=='included' else 'review','reason':decision,'evidence':evidence,'routes':routes})
        if idx%100==0 or idx==len(pending_doi): print(json.dumps({'phase':'crossref_batch_screen','processed':idx,'total':len(pending_doi),**counts},ensure_ascii=False),flush=True)
    payload={'version':'v9','input_count':len(pending_doi),'counts':counts,'coverage':coverage,'errors':errors,'results':results,'note':'Abstracts and link URLs were processed transiently; no abstracts or full text are stored.'}
    Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return counts

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--workers',type=int,default=4); a=ap.parse_args(); print(json.dumps(run(a.out,a.workers),ensure_ascii=False))
