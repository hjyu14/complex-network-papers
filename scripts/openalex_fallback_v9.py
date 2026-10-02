"""OpenAlex metadata fallback for v9; abstract text is transient only."""
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from collect import clean, relevance

ROOT=Path(__file__).resolve().parents[1]

def fetch(doi):
    url='https://api.openalex.org/works/https://doi.org/'+quote(doi,safe='')
    try:
        req=Request(url,headers={'User-Agent':'ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)','Accept':'application/json'})
        with urlopen(req,timeout=25) as resp: data=json.load(resp)
        inv=data.get('abstract_inverted_index') or {}
        words=[]
        for word,positions in inv.items():
            for pos in positions: words.append((pos,word))
        abstract=' '.join(w for _,w in sorted(words))
        return doi,data,abstract,None
    except HTTPError as exc:
        if exc.code == 429: time.sleep(10)
        return doi,{},'',f'HTTP_{exc.code}'
    except Exception as exc:
        return doi,{},'',type(exc).__name__

def run(out,workers=2,checkpoint=None):
    trial=ROOT/'reports/v9-2026-09'
    cr=json.loads((trial/'crossref-fallback.json').read_text(encoding='utf-8'))
    rows=[x for x in cr['results'] if not x.get('abstract_available')]
    rules=json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))['screening']
    results=[]; counts={'processed':0,'abstract_found':0,'new_direct_included':0,'errors':0,'still_review':0}
    if checkpoint and Path(checkpoint).exists():
        saved=json.loads(Path(checkpoint).read_text(encoding='utf-8')); results=saved.get('results',[]); done={x['doi'] for x in results}; rows=[x for x in rows if x['doi'] not in done]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fetch,x['doi']) for x in rows]
        for idx,fut in enumerate(as_completed(futures),1):
            doi,data,abstract,error=fut.result(); counts['processed']=idx
            if error:
                counts['errors']+=1; counts['still_review']+=1; result={'doi':doi,'status':'error','error':error}
            else:
                if abstract: counts['abstract_found']+=1
                title=clean(data.get('title','')); decision,routes,evidence=relevance(title,abstract,rules) if abstract else ('review_missing_abstract',[],[])
                final='included' if decision=='included' else 'review'
                counts['new_direct_included'] += final=='included'; counts['still_review'] += final=='review'
                result={'doi':doi,'status':'ok','title':title,'abstract_available':bool(abstract),'publication_date':data.get('publication_date'),'type':data.get('type'),'primary_location':(data.get('primary_location') or {}).get('landing_page_url'),'decision':final,'reason':decision,'evidence':evidence,'routes':routes,'source_url':'https://api.openalex.org/works/https://doi.org/'+doi}
            results.append(result)
            if checkpoint and (idx%50==0 or idx==len(rows)):
                Path(checkpoint).write_text(json.dumps({'version':'v9','results':results,'counts':counts},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            if idx%25==0 or idx==len(rows): print(json.dumps({'phase':'openalex','processed':idx,'batch_total':len(rows),'saved_total':len(results),**counts},ensure_ascii=False),flush=True)
    results.sort(key=lambda x:x['doi'])
    payload={'version':'v9','input_count':len(rows),'counts':counts,'results':results,'note':'OpenAlex abstract text was processed transiently and not stored.'}
    Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return counts

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--checkpoint',required=True); ap.add_argument('--workers',type=int,default=2); a=ap.parse_args(); print(json.dumps(run(a.out,a.workers,a.checkpoint),ensure_ascii=False))
