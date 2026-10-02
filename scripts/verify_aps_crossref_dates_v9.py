"""Refresh only date metadata for the 11 DOI-verified APS conflict records."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from refresh_date_gaps_crossref_v9 import fetch

TRIAL = Path(__file__).resolve().parents[1] / 'reports/v9-2026-09'


def main():
    output = TRIAL / 'aps-crossref-date-verification-v1.json'
    if output.exists():
        raise FileExistsError(output)
    browser = json.loads((TRIAL / 'browser-date-conflict-recheck-v1.json').read_text(encoding='utf8'))
    ids = [r['doi'] for r in browser['results']]
    assert browser['complete'] and len(ids) == len(set(ids)) == 11
    assert all(d.startswith('10.1103/') for d in ids)
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(fetch, ids):
            row['retrieved_at'] = datetime.now(timezone.utc).isoformat()
            rows.append(row)
            print(json.dumps({'processed': len(rows), 'total': 11,
                              'doi': row['doi'], 'status': row['status']}, ensure_ascii=False), flush=True)
    payload = {'created_at': datetime.now(timezone.utc).isoformat(),
               'purpose': 'Verify raw date-parts against browser-confirmed acceptance dates; no abstracts stored.',
               'complete': len(rows) == 11 and all(r['status'] == 'ok' for r in rows),
               'results': rows}
    with output.open('x', encoding='utf8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
