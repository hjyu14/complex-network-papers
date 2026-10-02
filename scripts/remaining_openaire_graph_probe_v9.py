"""Probe documented OpenAIRE Graph V3 DOI filter; no response bodies saved."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

TRIAL = Path(__file__).resolve().parents[1] / 'reports' / 'v9-2026-09'


def main():
    merged = json.loads((TRIAL / 'material-after-programmatic-v1.json').read_text(encoding='utf8'))
    dois = [r['doi'] for r in merged['results'] if r['collection_state'] == 'needs_material']
    url = 'https://api.openaire.eu/graph/v3/research-products'
    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'input_dois': dois,
               'endpoint': url, 'documentation': [
                   'https://graph.openaire.eu/docs/apis/graph-api/research-products/',
                   'https://graph.openaire.eu/docs/apis/graph-api/research-products/filtering/'],
               'results': [], 'coverage': [], 'abstracts_not_archived': True}
    out = TRIAL / 'remaining-openaire-graph-probe-v3.json'
    if out.exists():
        payload['previous_attempt'] = json.loads(out.read_text(encoding='utf8'))
    # The live server explicitly limits each filter to four logical operators.
    # Five exact DOI values per request meet that constraint.
    for offset in range(0, len(dois), 5):
        batch = dois[offset:offset + 5]
        query = '(' + ' OR '.join('"' + d + '"' for d in batch) + ')'
        coverage = {'input_dois': batch, 'offset': offset}
        try:
            response = requests.get(url, params={'pid': query, 'pageSize': 100}, timeout=(10, 30))
            coverage['http_status'] = response.status_code
            coverage['response_sha256'] = hashlib.sha256(response.content).hexdigest()
            if response.status_code != 200:
                coverage['status'] = 'http_error'
                payload['coverage'].append(coverage)
                out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
                print(json.dumps(coverage), flush=True)
                break
            data = response.json()
            coverage['num_found'] = data.get('header', {}).get('numFound')
            found = data.get('results', [])
            coverage['returned_count'] = len(found)
            coverage['complete_response'] = len(found) == coverage['num_found']
            indexed = {}
            for item in found:
                ids = {p.get('value', '').lower() for p in item.get('pids', []) if p.get('scheme') == 'doi'}
                descriptions = [str(v).strip() for v in item.get('descriptions', []) if v]
                for doi in ids.intersection(batch):
                    indexed[doi] = {
                        'doi': doi, 'doi_match': True, 'status': 'matched',
                        'source_id': item.get('id'), 'source_url': url + '/' + item.get('id', ''),
                        'description_count': len(descriptions),
                        'description_candidate_word_counts': [len(v.split()) for v in descriptions],
                        'description_candidate_sha256': [hashlib.sha256(v.encode()).hexdigest() for v in descriptions],
                        'abstract_available': False,
                        'description_is_verified_abstract': False,
                        'publication_date_candidate': item.get('publicationDate'),
                        'publication_date_is_online_first_proof': False,
                        'type': item.get('type'), 'abstract_not_archived': True,
                    }
            payload['results'].extend(indexed.get(d, {'doi': d, 'doi_match': False,
                                                   'status': 'not_indexed' if coverage['complete_response'] else 'incomplete_response',
                                                   'abstract_available': False}) for d in batch)
        except requests.RequestException as exc:
            coverage['error_class'] = type(exc).__name__
        payload['coverage'].append(coverage)
        payload['complete'] = len(payload['results']) == len(dois) and all(c.get('complete_response') for c in payload['coverage'])
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(json.dumps({'offset': offset, 'http_status': coverage.get('http_status'),
                          'processed': len(payload['results']), 'target': len(dois),
                          'num_found': coverage.get('num_found')}, ensure_ascii=False), flush=True)
        if coverage.get('error_class') or not coverage.get('complete_response'):
            break
        time.sleep(2)
    print(json.dumps({'matched': sum(r['doi_match'] for r in payload['results']),
                      'description_candidates': sum(bool(r.get('description_count')) for r in payload['results'])}))


if __name__ == '__main__':
    main()
