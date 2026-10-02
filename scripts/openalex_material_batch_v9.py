"""Low-rate exact-DOI OpenAlex batches; abstracts stay in memory only."""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from api_batch_v9 import TRIAL, get_json
from collect import clean


def run():
    pending = json.loads((TRIAL/'material-pending-after-elsevier-verification-corrected.json').read_text(encoding='utf-8'))
    dois = sorted({r['doi'].lower() for r in pending['missing_abstract'] + pending['missing_preferred_date_with_abstract']})
    out = TRIAL/'openalex-material-batch-v1.json'
    saved = json.loads(out.read_text(encoding='utf-8')) if out.exists() else {}
    results = saved.get('results', [])
    coverage = saved.get('coverage', [])
    done = {d for c in coverage if c.get('http_status') == 200 for d in c['dois']}
    todo = [d for d in dois if d not in done]
    batches = [todo[i:i+50] for i in range(0, len(todo), 50)]
    for batch in batches:
        url = 'https://api.openalex.org/works?' + urlencode({'filter': 'doi:'+'|'.join(batch), 'per_page':100, 'select':'doi,title,type,publication_date,abstract_inverted_index,primary_location'})
        status, data = get_json(url)
        found = {}
        for item in (data or {}).get('results', []):
            doi = (item.get('doi') or '').lower().removeprefix('https://doi.org/')
            if doi not in batch:
                continue
            inv = item.get('abstract_inverted_index') or {}
            words = sorted((pos,word) for word,positions in inv.items() for pos in positions)
            abstract = clean(' '.join(word for _,word in words))
            loc = item.get('primary_location') or {}
            source = loc.get('source') or {}
            found[doi] = {'doi':doi, 'title':item.get('title'), 'doi_match':True, 'abstract_available':bool(abstract), 'abstract_word_count':len(abstract.split()), 'abstract_sha256':hashlib.sha256(abstract.encode()).hexdigest() if abstract else None, 'date_candidate':item.get('publication_date'), 'date_candidate_semantics':'OpenAlex publication_date; not publisher-labelled online-first proof', 'article_type':item.get('type'), 'publisher_url':loc.get('landing_page_url'), 'journal':source.get('display_name'), 'issns':source.get('issn'), 'source_url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(), 'scope_terms':sorted(set(re.findall(r'\b(?:networks?|graphs?|hypergraphs?|synchroni\w+|percolation|communities|centralit\w+|epidemic\w+|topolog\w+|coupl\w+|spreading|connectiv\w+)\b', abstract, re.I))), 'classification_deferred':True, 'status':'matched'}
        for doi in batch:
            results.append(found.get(doi, {'doi':doi, 'status':'not_returned' if status == 200 else 'request_error', 'http_status':status, 'abstract_available':False}))
        coverage.append({'dois':batch,'http_status':status,'matched':len(found),'source_url':url})
        counts = {'target':len(dois), 'processed':len({r['doi'] for r in results}), 'matched':sum(r['status']=='matched' for r in results), 'abstract_found':sum(r['abstract_available'] for r in results), 'failed_batches':sum(c['http_status']!=200 for c in coverage)}
        payload = {'complete':counts['processed']==len(dois), 'counts':counts, 'coverage':coverage, 'results':results, 'note':'Exact DOI matching only; abstracts are transient, date candidates do not override incomplete preferred publisher dates.'}
        tmp = out.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        tmp.replace(out)
        print(json.dumps(counts),flush=True)
        if status in (401, 403, 429):
            print('Service access/rate limit; stopped this channel without bypass.',flush=True)
            break
        time.sleep(0.5)


if __name__ == '__main__':
    run()
