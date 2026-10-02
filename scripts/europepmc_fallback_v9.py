"""Europe PMC DOI batch metadata fallback; abstracts are transient only."""
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from collect import clean, relevance

ROOT=Path(__file__).resolve().parents[1]

def fetch(batch):
    q=' OR '.join('DOI:"'+d+'"' for d in batch)
    url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?query='+quote(q)+'&format=json&resultType=core&pageSize=100'
    try:
        req=Request(url,headers={'User-Agent':'ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)','Accept':'application/json'})
        with urlopen(req,timeout=30) as resp: return batch,json.load(resp),None
    except Exception as exc: return batch,{},type(exc).__name__

def run(out,workers=2):
    report=json.loads((ROOT/'reports/v9-2026-09/screening-report.json').read_text(encoding='utf-8'))
    dois=[x['doi'] for x in report['decisions'] if x['decision']=='review']
    batches=[dois[i:i+50] for i in range(0,len(dois),50)]
    rules=json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))['screening']
    results=[]; counts={'batches':len(batches),'processed_batches':0,'matched':0,'abstract_found':0,'direct_inclusion_signals':0,'errors':0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fetch,b) for b in batches]
        for idx,fut in enumerate(as_completed(futures),1):
            batch,data,error=fut.result(); counts['processed_batches']=idx
            if error: counts['errors']+=1
            else:
                for item in data.get('resultList',{}).get('result',[]) or []:
                    doi=(item.get('doi') or '').lower()
                    if not doi: continue
                    counts['matched']+=1; abstract=clean(item.get('abstractText','')); counts['abstract_found']+=bool(abstract)
                    decision,routes,evidence=relevance(clean(item.get('title','')),abstract,rules) if abstract else ('review_missing_abstract',[],[])
                    counts['direct_inclusion_signals']+=decision=='included'
                    results.append({'doi':doi,'title':clean(item.get('title','')),'abstract_available':bool(abstract),'pubYear':item.get('pubYear'),'journalTitle':item.get('journalTitle'),'source_url':'https://europepmc.org/article/MED/'+str(item.get('pmid')) if item.get('pmid') else 'https://europepmc.org/search?query=DOI:'+doi,'decision':'included' if decision=='included' else 'review','reason':decision,'evidence':evidence,'routes':routes})
            print(json.dumps({'phase':'europepmc','batch':idx,'total_batches':len(batches),**counts},ensure_ascii=False),flush=True)
    by={x['doi']:x for x in results}; payload={'version':'v9','input_count':len(dois),'counts':counts,'results':sorted(by.values(),key=lambda x:x['doi']),'note':'Abstracts processed transiently and not stored.'}
    Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return counts

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--workers',type=int,default=2); a=ap.parse_args(); print(json.dumps(run(a.out,a.workers),ensure_ascii=False))
