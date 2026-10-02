"""Read normal publisher citation exports; archive derived evidence only."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

TRIAL = Path(__file__).resolve().parents[1] / 'reports' / 'v9-2026-09'


def ris_fields(body):
    fields = {}
    key = None
    for line in body.splitlines():
        match = re.match(r'^([A-Z0-9]{2})  - ?(.*)$', line)
        if match:
            key, value = match.groups()
            fields.setdefault(key, []).append(value)
        elif key and line.strip():
            fields[key][-1] += ' ' + line.strip()
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, required=True)
    parser.add_argument('--publisher', choices=['pnas', 'science', 'all'], default='all')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    assert args.limit > 0
    out = TRIAL / args.out
    assert out.parent == TRIAL and out.suffix == '.json'
    merged = json.loads((TRIAL / 'material-after-programmatic-v1.json').read_text(encoding='utf8'))
    rows = []
    for row in merged['results']:
        publisher = 'pnas' if row['doi'].startswith('10.1073/') else 'science' if row['doi'].startswith('10.1126/') else None
        if row['collection_state'] == 'needs_material' and publisher and args.publisher in (publisher, 'all'):
            rows.append((publisher, row))
    payload = json.loads(out.read_text(encoding='utf8')) if out.exists() else {
        'channel': 'official citation export form, discovered in authorised browser',
        'abstracts_not_archived': True, 'results': [],
    }
    done = {r['doi'] for r in payload['results']}
    stopped = set()
    count = 0
    for publisher, row in rows:
        if row['doi'] in done or publisher in stopped or count >= args.limit:
            continue
        doi = row['doi']
        host = 'www.pnas.org' if publisher == 'pnas' else 'www.science.org'
        url = f'https://{host}/action/downloadCitation'
        item = {'doi': doi, 'publisher': publisher, 'source_url': url,
                'format': 'ris', 'method': 'POST', 'abstract_available': False,
                'doi_match': False, 'retrieved_at': datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.post(url, data={'doi': doi, 'format': 'ris'}, timeout=(10, 25))
            item['http_status'] = response.status_code
            item['content_type'] = response.headers.get('Content-Type')
            item['response_sha256'] = hashlib.sha256(response.content).hexdigest()
            if response.status_code != 200:
                item['status'] = 'http_access_error'
                if response.status_code in (401, 403, 429):
                    stopped.add(publisher)
            else:
                fields = ris_fields(response.text)
                item['citation_field_names'] = sorted(fields)
                identifiers = [v.lower().strip().removeprefix('https://doi.org/').removeprefix('doi:').strip() for v in fields.get('DO', [])]
                item['doi_match'] = doi.lower() in identifiers
                abstract = ' '.join(fields.get('AB', []) + fields.get('N2', [])).strip()
                word_count = len(abstract.split())
                item['abstract_available'] = item['doi_match'] and word_count >= 10
                item['abstract_word_count'] = word_count if item['abstract_available'] else 0
                item['abstract_sha256'] = hashlib.sha256(abstract.encode()).hexdigest() if item['abstract_available'] else None
                item['status'] = 'citation_confirmed' if item['doi_match'] else 'unconfirmed_response'
                if not fields or not item['doi_match']:
                    stopped.add(publisher)
        except requests.RequestException as exc:
            item['status'] = 'request_error'
            item['error_class'] = type(exc).__name__
            stopped.add(publisher)
        payload['results'].append(item)
        payload['updated_at'] = datetime.now(timezone.utc).isoformat()
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        print(json.dumps(item), flush=True)
        count += 1
        time.sleep(2)


if __name__ == '__main__':
    main()
