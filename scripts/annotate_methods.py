"""Annotate the existing feed without changing its inclusion decisions.

Fetch abstracts transiently. A separate DOI-keyed sidecar keeps the original
screening snapshot and its provenance intact. Any fetch failure aborts output.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import quote

from collect import CONFIG, ROOT, classify_methods, clean, request_json, write_json


def main():
    source = ROOT / 'site/data/papers.json'
    raw = source.read_bytes()
    data = json.loads(raw)
    config = json.loads(CONFIG.read_text(encoding='utf-8'))

    def annotate(paper):
        item = request_json('https://api.crossref.org/works/' + quote(paper['doi'], safe=''))
        if item.get('DOI', '').lower() != paper['doi'].lower():
            raise ValueError('DOI mismatch')
        title = clean(' '.join(item.get('title', [])))
        abstract = clean(item.get('abstract', ''))
        methods, evidence = classify_methods(title + ' ' + abstract, config['screening'])
        sources = {}
        for field, value in [('title', title), ('abstract', abstract)]:
            _, hits = classify_methods(value, config['screening'])
            for method in hits:
                sources.setdefault(method, []).append(field)
        print(paper['doi'], ','.join(methods) or 'unlabelled', flush=True)
        return paper['doi'], {'methods': methods, 'method_evidence': evidence,
                             'method_sources': sources, 'abstract_available': bool(abstract)}

    with ThreadPoolExecutor(max_workers=3) as pool:
        annotations = dict(pool.map(annotate, data['papers']))
    if source.read_bytes() != raw:
        raise ValueError('Source snapshot changed during annotation')
    write_json(ROOT / 'site/data/methods.json', {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_snapshot_sha256': hashlib.sha256(raw).hexdigest(),
        'source_screening_version': data['screening_version'],
        'source_generated_at': data['generated_at'],
        'method_rules_version': config['version'],
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'papers': annotations,
    })
    print(f'Annotated {len(annotations)} papers; inclusion decisions unchanged.', flush=True)


if __name__ == '__main__':
    main()
