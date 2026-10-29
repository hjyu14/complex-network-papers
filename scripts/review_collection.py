"""Build the explicitly selected historical review collection, without network access."""
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from run_inputs import digest

ROOT = Path(__file__).resolve().parents[1]


def attach_reviews(artifacts, root=ROOT):
    config_path = root/'config/review-collection.json'
    if not config_path.exists():
        return artifacts
    config = json.loads(config_path.read_text(encoding='utf8'))
    sources = [config['source'], *config.get('supplemental_sources', [])]
    rows, limitations = [], []
    for source in sources:
        path = (root/Path(source['path'])).resolve()
        if not path.is_relative_to((root/'reports/reviews').resolve()):
            raise ValueError('Review source must be a formal editorial collection')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('Review collection source changed')
        collection = json.loads(raw)
        if collection['version'] != 'editorial-review-collection-1':
            raise ValueError('Unsupported review collection')
        rows.extend(collection['records'])
        limitations.extend(x for x in collection['limitations'] if x not in limitations)
    if len(rows) != config['count'] or len({r['paper']['doi'] for r in rows}) != len(rows):
        raise ValueError('Review collection count or duplicate DOI mismatch')
    topics = {c['id'] for c in artifacts['papers.json']['categories']}
    existing = {p['doi']: p for p in artifacts['papers.json']['papers']}
    papers = []
    for record in rows:
        p, evidence = record['paper'], record['evidence']
        if digest({k:v for k,v in record.items() if k != 'sha256'}) != record['sha256']:
            raise ValueError('Review record binding changed: '+p['doi'])
        if (p['publication_status'] != 'published' or p['article_type'] != 'Review'
                or not p['authors'] or any(not a.strip() for a in p['authors'])
                or not p['note_en'] or not p['note_zh']
                or not p['categories'] or not set(p['categories']) <= topics
                or p['journal_short'] not in config['journals']
                or not evidence['registration_checked'] or not evidence['abstract_read']
                or evidence['fulltext_read'] or not evidence['date_basis']
                or not evidence['review_type_basis'] or not evidence['author_resolution']
                or p['material_sha256'] != evidence['material_sha256']
                or not evidence['selection_basis']):
            raise ValueError('Incomplete review metadata: '+p['doi'])
        date.fromisoformat(p['date'])
        if not config['start_date'] <= p['date'] <= config['cutoff_date']:
            raise ValueError('Review date outside selected collection')
        for url in [p['url'], p['doi_url']]:
            if urlparse(url).scheme != 'https':
                raise ValueError('Review links must use HTTPS')
        for key in ['material_sha256', 'abstract_sha256', 'registration_record_sha256',
                    'registration_check_event_sha256', 'material_review_event_sha256']:
            if len(evidence[key]) != 64 or any(c not in '0123456789abcdef' for c in evidence[key]):
                raise ValueError('Review evidence lacks a valid hash')
        if p['doi'] in existing:
            # A DOI has one canonical identity. Resolve differences explicitly.
            current = existing[p['doi']]
            if any(current[k] != p[k] for k in ['title', 'authors', 'date', 'note_en', 'note_zh', 'categories']):
                raise ValueError('Conflicting review and daily record: '+p['doi'])
        else:
            papers.append(p)
    collection_dois = {r['paper']['doi'] for r in rows}
    # Reuse canonical records only for explicitly selected DOI identities.
    # Other reviews in the daily collection do not expand this curated set.
    current_dois = sorted(collection_dois & existing.keys())
    result = {**artifacts, 'reviews.json': {
        'version': 'review-collection-1', 'source': config['source'],
        'supplemental_sources': config.get('supplemental_sources', []),
        'selection_count': len(rows), 'start_date': config['start_date'],
        'cutoff_date': config['cutoff_date'], 'papers': papers,
        'current_collection_dois': current_dois,
        'total_count': len(papers) + len(current_dois),
        'limitations': limitations}}
    return result
