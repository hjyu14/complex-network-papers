"""Resolve DOI pages for v9 review records; abstracts are transient only."""
import argparse, html, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from collect import clean, relevance

ROOT = Path(__file__).resolve().parents[1]

def meta(page, names):
    for name in names:
        pat = re.compile(r'<meta[^>]+(?:name|property)=["\']' + re.escape(name) + r'["\'][^>]+content=["\'](.*?)["\']', re.I | re.S)
        m = pat.search(page)
        if not m:
            pat = re.compile(r'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\']' + re.escape(name) + r'["\']', re.I | re.S)
            m = pat.search(page)
        if m: return clean(html.unescape(m.group(1)))
    return ''

def fetch(row):
    doi = row['doi']
    url = 'https://doi.org/' + quote(doi, safe='/')
    try:
        req = Request(url, headers={'User-Agent':'ComplexNetworkPapers/0.1 (v9 metadata fallback)', 'Accept':'text/html,application/xhtml+xml'})
        with urlopen(req, timeout=25) as resp:
            page = resp.read(2_000_000).decode('utf-8', 'ignore')
            final_url = resp.geturl()
        title = meta(page, ['citation_title','og:title','twitter:title']) or row.get('title','')
        abstract = meta(page, ['citation_abstract','description','og:description','twitter:description'])
        journal = meta(page, ['citation_journal_title'])
        online = meta(page, ['citation_online_date','article:published_time'])
        published = meta(page, ['citation_publication_date'])
        return {'doi':doi,'title':title,'abstract':abstract,'journal':journal,'online_date':online,'published_date':published,'source_url':final_url,'status':'ok'}
    except Exception as exc:
        return {'doi':doi,'title':row.get('title',''),'source_url':url,'status':'error','error':type(exc).__name__}

def run(out, workers=4):
    trial = ROOT / 'reports/v9-2026-09'
    report = json.loads((trial/'screening-report.json').read_text(encoding='utf-8'))
    rows = [r for r in report['decisions'] if r['decision']=='review']
    rules = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))['screening']
    results=[]; counts={'included':0,'review':0,'error':0,'processed':0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fetch,row) for row in rows]
        for idx, fut in enumerate(as_completed(futures),1):
            fetched=fut.result(); counts['processed']=idx
            if fetched['status']!='ok': counts['error']+=1; counts['review']+=1
            else:
                decision, routes, evidence = relevance(fetched['title'], fetched.get('abstract',''), rules)
                if decision=='included':
                    counts['included']+=1; final='included'
                else:
                    counts['review']+=1; final='review'
                # Never write abstract or page HTML.
                fetched={'doi':fetched['doi'],'title':fetched['title'],'source_url':fetched['source_url'],'status':fetched['status'], 'publisher_journal':fetched['journal'], 'date_evidence':{'online':fetched['online_date'],'published':fetched['published_date']}, 'decision':final, 'reason':decision, 'evidence':evidence, 'routes':routes}
            results.append(fetched)
            if idx%10==0 or idx==len(rows): print(json.dumps({'phase':'publisher_fallback','processed':idx,'total':len(rows),'included':counts['included'],'review':counts['review'],'errors':counts['error']},ensure_ascii=False),flush=True)
    results.sort(key=lambda x:x['doi'])
    payload={'version':'v9','window_start':'2026-09-01','window_end':'2026-09-30','input_count':len(rows),'counts':counts,'results':results,'note':'Publisher metadata and abstracts were processed transiently; abstracts and page HTML are not stored.'}
    Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return counts

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--workers',type=int,default=16); args=ap.parse_args(); print(json.dumps(run(args.out,args.workers),ensure_ascii=False))
