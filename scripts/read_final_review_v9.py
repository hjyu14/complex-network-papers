"""Read a bounded batch cache-first; full abstracts stay in the private cache."""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

from collect import clean
from prepare_final_review_v9 import TRIAL
from private_abstract_cache import AbstractCache, FIELDS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', type=int, required=True)
    ap.add_argument('--count', type=int, default=8)
    ap.add_argument('--show-abstract', action='store_true', help='Display to reviewer; never redirect to ordinary logs')
    a = ap.parse_args()
    papers = json.loads((TRIAL/'papers-editorial.json').read_text(encoding='utf-8'))['papers']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = TRIAL / f'final-review-cached-reads-{a.start:03d}-{stamp}.json'
    cache = AbstractCache()

    def read(pair):
        i, paper = pair
        doi = paper['doi']
        url = 'https://api.crossref.org/works/' + quote(doi, safe='')
        now = datetime.now(timezone.utc).isoformat()
        result = {'index': i, 'doi': doi, 'source_url': url, 'retrieved_at': now}
        abstract = ''
        try:
            cached = cache.get(doi)
            if cached:
                abstract = cached['abstract']
                result.update({k: cached[k] for k in FIELDS if k in cached})
                result.update(cache_hit=True, private_cache_saved=True, doi_match=True,
                              abstract_available=True, abstract_sha256=cached['abstract_sha256'],
                              abstract_word_count=len(abstract.split()),
                              read_at=now, review_input_sha256=hashlib.sha256(json.dumps(
                                  cached, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
                return result, abstract
            request = Request(url, headers={'User-Agent': 'ComplexNetworkPapers/0.1 (bounded v9 review)'})
            with urlopen(request, timeout=25) as response:
                item = json.load(response)['message']
            assert item['DOI'].lower() == doi.lower(), 'DOI mismatch'
            abstract = clean(item.get('abstract', ''))
            result.update(title=clean(' '.join(item.get('title', []))),
                          issns=item.get('ISSN', []), article_type=item.get('type'),
                          published_online=item.get('published-online'),
                          published_print=item.get('published-print'),
                          abstract_available=bool(abstract), doi_match=True,
                          abstract_sha256=hashlib.sha256(abstract.encode()).hexdigest() if abstract else None,
                          abstract_word_count=len(abstract.split()))
            result.update(abstract_basis='crossref.abstract', cache_hit=False, private_cache_saved=False)
            if abstract:
                cached = cache.put(result, abstract)
                result['private_cache_saved'] = True
            result['review_input_sha256'] = hashlib.sha256(json.dumps(
                cached if abstract else {'metadata': result, 'abstract': abstract}, ensure_ascii=False, sort_keys=True
            ).encode()).hexdigest()
        except Exception as exc:
            abstract = ''
            result.update(abstract_available=False, error=type(exc).__name__ + ': ' + str(exc)[:200])
        return result, abstract

    evidence = []
    pairs = list(enumerate(papers))[a.start:a.start+a.count]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result, abstract in pool.map(read, pairs):
            evidence.append(result)
            display = {**result, 'transient_abstract': abstract} if a.show_abstract else result
            print(json.dumps(display, ensure_ascii=False), flush=True)
    output.write_text(json.dumps({'complete': True, 'full_abstracts_in_this_report': False,
                                 'private_cache_saved_count': sum(r.get('private_cache_saved', False) for r in evidence),
                                 'results': evidence}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit('Retired collection-only entry point. Use review_workflow_v9.py next/show/submit to keep reading and assessment in the same work unit.')
