"""Crossref machine-readable fallback for v9 review records; no abstracts stored."""
import argparse, hashlib, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from collect import clean, relevance, publication_date

ROOT = Path(__file__).resolve().parents[1]

def fetch(doi):
    url = 'https://api.crossref.org/works/' + quote(doi, safe='')
    try:
        req = Request(url, headers={'User-Agent':'ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)', 'Accept':'application/json'})
        with urlopen(req, timeout=30) as response:
            message = __import__('json').load(response)
        return doi, message.get('message', {}), None
    except Exception as exc:
        return doi, {}, type(exc).__name__

def run(out, workers=8):
    trial = ROOT / 'reports/v9-2026-09'
    report = json.loads((trial/'screening-report.json').read_text(encoding='utf-8'))
    rows = [r for r in report['decisions'] if r['decision']=='review']
    rules = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))['screening']
    results=[]; counts={'processed':0,'abstract_found':0,'date_complete':0,'links_found':0,'new_direct_included':0,'still_review':0,'errors':0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fetch,row['doi']) for row in rows]
        for idx, fut in enumerate(as_completed(futures),1):
            doi, item, error = fut.result(); counts['processed']=idx
            if error:
                counts['errors']+=1; counts['still_review']+=1
                result={'doi':doi,'status':'error','error':error}
            else:
                title=clean(' '.join(item.get('title',[]))); abstract=clean(item.get('abstract','') or item.get('description',''))
                pub, date_source=publication_date(item); links=[]
                for link in item.get('link',[]) or []:
                    links.append({'url':link.get('URL'),'content_type':link.get('content-type'),'intended_application':link.get('intended-application'),'version':link.get('content-version')})
                if abstract: counts['abstract_found']+=1
                if pub: counts['date_complete']+=1
                if links: counts['links_found']+=1
                decision, routes, evidence = relevance(title, abstract, rules) if abstract else ('review_missing_abstract',[],[])
                if decision=='included': counts['new_direct_included']+=1; final='included'
                else: counts['still_review']+=1; final='review'
                # Abstract is deliberately not written.
                result={'doi':doi,'status':'ok','title':title,'date':pub.isoformat() if pub else None,'date_source':date_source,'abstract_available':bool(abstract),'links':links,'decision':final,'reason':decision,'evidence':evidence,'routes':routes,'metadata_url':url_for(doi)}
            results.append(result)
            if idx%50==0 or idx==len(rows): print(json.dumps({'phase':'crossref_fallback','processed':idx,'total':len(rows),**counts},ensure_ascii=False),flush=True)
    results.sort(key=lambda x:x['doi'])
    payload={'version':'v9','window_start':'2026-09-01','window_end':'2026-09-30','input_count':len(rows),'counts':counts,'results':results,'note':'Crossref abstracts were processed transiently and not stored.'}
    Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return counts

def url_for(doi): return 'https://api.crossref.org/works/' + quote(doi, safe='')

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--workers',type=int,default=8); args=ap.parse_args(); print(json.dumps(run(args.out,args.workers),ensure_ascii=False))
