"""OpenAIRE DOI batch fallback; no response bodies or abstract text stored."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from api_batch_v9 import get_json, TRIAL, ROOT
from collect import clean, relevance


def seq(v):
    return v if isinstance(v, list) else [v] if v is not None else []


def text(v):
    value = v.get('$', '') if isinstance(v, dict) else v
    return clean(str(value)) if isinstance(value, (str, int, float)) else ''


def fetch(batch):
    url = 'https://api.openaire.eu/search/publications?doi=' + quote(','.join(batch), safe='') + '&format=json&size=100'
    status, data = get_json(url)
    coverage = {'dois': batch, 'http_status': status, 'matched': 0, 'abstract_found': 0}
    results = []
    if not data:
        return coverage, results
    response = data.get('response', {})
    coverage['total_returned'] = text(response.get('header', {}).get('total', {}))
    rules = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))['screening']
    for entry in seq((response.get('results') or {}).get('result')):
        product = entry.get('metadata', {}).get('oaf:entity', {}).get('oaf:result', {})
        dois = [text(p).lower() for p in seq(product.get('pid')) if isinstance(p, dict) and p.get('@classid') == 'doi']
        titles = seq(product.get('title')); title = text(titles[0]) if titles else ''
        abstracts = [text(d) for d in seq(product.get('description'))]
        abstract = max(abstracts, key=len, default='')
        enough = len(abstract.split()) >= 40
        for doi in dois:
            if doi not in batch:
                continue
            row = {'doi': doi, 'abstract_available': enough, 'title': title, 'source_url': url,
                   'date_evidence': text(product.get('dateofacceptance')), 'status': 'matched',
                   'classification_deferred': True}
            if enough:
                reason, routes, evidence = relevance(title, abstract, rules)
                row['material_observations'] = {'heuristic_reason': reason, 'routes': routes, 'evidence': evidence,
                                               'abstract_word_count': len(abstract.split())}
            results.append(row)
    coverage['matched'] = len(results)
    coverage['abstract_found'] = sum(bool(r['abstract_available']) for r in results)
    return coverage, results


def main(out):
    report = json.loads((TRIAL/'screening-report.json').read_text(encoding='utf-8'))
    known = set()
    for fn in ('crossref-fallback.json','crossref-batch-refresh.json','europepmc-fallback.json','openalex-fallback.json'):
        data = json.loads((TRIAL/fn).read_text(encoding='utf-8'))
        known |= {r['doi'].lower() for r in data['results'] if r.get('abstract_available')}
    targets = sorted({r['doi'].lower() for r in report['decisions'] if r['decision']=='review'}-known)
    batches = [targets[i:i+40] for i in range(0,len(targets),40)]
    results = []; coverage = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i, future in enumerate(as_completed([pool.submit(fetch,b) for b in batches]),1):
            c, rows = future.result(); results.extend(rows); coverage.append(c)
            print(json.dumps({'phase':'openaire','batches':i,'total_batches':len(batches),
                'matched':len(results),'abstract_found':sum(bool(r['abstract_available']) for r in results)}),flush=True)
    payload = {'input_count':len(targets),'coverage':coverage,'results':results,
               'counts': {'processed_batches': len(coverage), 'batches':len(batches),
                          'matched':len(results),'abstract_found':sum(bool(r['abstract_available']) for r in results),
                          'failed_batches':sum(c['http_status']!=200 for c in coverage)},
               'note':'Abstracts processed transiently; no abstracts or response bodies stored.'}
    Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main(sys.argv[1])
