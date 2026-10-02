"""Read current DOI evidence transiently; never save abstracts or modify the feed.

Examples: --indices 2,9,16; --excluded (nonstandard notices and ML exclusions).
Output is for content review, not an automatic adjudication.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from collect import ROOT, clean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--indices', default='')
    parser.add_argument('--excluded', action='store_true')
    args = parser.parse_args()
    papers = json.loads((ROOT / 'site/data/papers.json').read_text(encoding='utf-8'))['papers']
    records = [(str(i), papers[i]) for i in map(int, filter(None, args.indices.split(',')))]
    if args.excluded:
        audit = json.loads((ROOT / 'site/data/screening-report.json').read_text(encoding='utf-8'))
        records += [('excluded', row) for row in audit['decisions'] if row['decision'] == 'excluded' and
                    (row['reason'] != 'notice' or not re.match(
                        r'^(correction|erratum|corrigendum|retraction|author correction|publisher correction|editorial|addendum)\b', row['title'], re.I))]

    def inspect(pair):
        index, row = pair
        url = 'https://api.crossref.org/works/' + quote(row['doi'], safe='')
        result = {'index': index, 'doi': row['doi'], 'snapshot_title': row['title'], 'source': url}
        try:
            request = Request(url, headers={'User-Agent': 'NetworkObservatory/0.1 (https://github.com/hjyu14/complex-network-papers)'})
            with urlopen(request, timeout=30) as response:
                item = json.load(response)['message']
            result.update(title=item.get('title'), abstract=clean(item.get('abstract', '')),
                          update_to=item.get('update-to'), type=item.get('type'),
                          published_online=item.get('published-online'), published=item.get('published'))
        except Exception as exc:
            result['error'] = str(exc)
        return result

    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(inspect, records):
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
