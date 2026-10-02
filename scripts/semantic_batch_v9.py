"""Semantic Scholar public batch API fallback; abstracts never written."""
import json, time, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from api_batch_v9 import TRIAL, ROOT, UA
from collect import clean, relevance


def main(out):
    base = json.loads((TRIAL/'screening-report.json').read_text(encoding='utf-8'))['decisions']
    review = {x['doi'].lower() for x in base if x['decision']=='review'}
    known = {x['doi'].lower() for x in base if x.get('abstract_available')}
    for fn in ('crossref-fallback.json','crossref-batch-refresh.json','europepmc-fallback.json',
               'openalex-fallback.json','crossref-refresh-v2.json','publisher-canonical-v2.json',
               'openaire-batch-v2.json','pubmed-batch-v2.json'):
        d = json.loads((TRIAL/fn).read_text(encoding='utf-8'))
        known |= {x['doi'].lower() for x in d.get('results',[]) if x.get('abstract_available')}
    targets = sorted(review-known)
    rules = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))['screening']
    url = 'https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,abstract,externalIds,publicationDate,journal,url'
    results = []; coverage = []; processed = 0; stopped = False
    for offset in range(0,len(targets),100):
        batch = targets[offset:offset+100]
        for attempt in range(3):
            try:
                req = Request(url,data=json.dumps({'ids':['DOI:'+d for d in batch]}).encode(),
                    headers={'User-Agent':UA,'Content-Type':'application/json','Accept':'application/json'},method='POST')
                with urlopen(req,timeout=40) as r:
                    data=json.load(r)
                error = None; break
            except HTTPError as e:
                error={'http_status':e.code,'retry_after':e.headers.get('Retry-After')}
                if e.code==429 or e.code in (401,403):
                    stopped=True; break
                if e.code not in (500,502,503,504) or attempt==2:
                    break
                time.sleep(3*(attempt+1))
            except Exception as e:
                error={'error':type(e).__name__}
                if attempt==2: break
                time.sleep(3*(attempt+1))
        if error:
            coverage.append({'offset':offset,'count':len(batch),**error})
            if stopped: break
        else:
            if not isinstance(data,list) or len(data)!=len(batch):
                coverage.append({'offset':offset,'count':len(batch),'error':'response_cardinality_mismatch'})
                stopped=True; break
            for doi, item in zip(batch,data):
                row={'doi':doi,'status':'not_found' if item is None else 'matched','abstract_available':False}
                if item:
                    reported=((item.get('externalIds') or {}).get('DOI') or '').lower()
                    if reported and reported!=doi:
                        row['status']='doi_mismatch'
                    else:
                        title=clean(item.get('title') or ''); abstract=clean(item.get('abstract') or '')
                        row.update({'title':title,'source_url':item.get('url'),
                            'publication_date_evidence':item.get('publicationDate'),
                            'journal':item.get('journal'),'abstract_available':len(abstract.split())>=40,
                            'classification_deferred':True})
                        if row['abstract_available']:
                            reason,routes,evidence=relevance(title,abstract,rules)
                            row['material_observations']={'heuristic_reason':reason,'routes':routes,
                                'evidence':evidence,'abstract_word_count':len(abstract.split())}
                results.append(row)
            coverage.append({'offset':offset,'count':len(batch),'http_status':200})
            processed+=len(batch)
        counts={'target':len(targets),'processed':processed,'abstract_found':sum(bool(x['abstract_available']) for x in results),
                'matched':sum(x['status']=='matched' for x in results),'failed_batches':sum(c.get('http_status')!=200 for c in coverage)}
        payload={'counts':counts,'coverage':coverage,'results':results,'complete':offset+len(batch)==len(targets),
                 'note':'Public POST batch endpoint; abstract text kept only in memory, never stored; classification deferred.'}
        Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'phase':'semantic_batch',**counts}),flush=True)
        time.sleep(3)
    if stopped:
        payload={'counts':{'target':len(targets),'processed':processed,'abstract_found':sum(bool(x['abstract_available']) for x in results)},
                 'coverage':coverage,'results':results,'complete':False,'status':'stopped_on_access_or_rate_limit'}
        Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Semantic Scholar batch finished',flush=True)


if __name__=='__main__':
    main(sys.argv[1])
