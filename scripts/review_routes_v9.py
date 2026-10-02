"""Reconstruct DOI-specific historical abstract routes, not topic decisions."""
import json
from collections import Counter
from urllib.parse import quote, urlsplit, urlunsplit

from private_abstract_cache import ROOT, digest

TRIAL = ROOT / 'reports/v9-2026-09'
PUBLISHERS = {'www.nature.com', 'nature.com', 'link.springer.com',
              'link.aps.org', 'journals.aps.org', 'www.pnas.org', 'pnas.org',
              'www.science.org', 'science.org', 'www.sciencedirect.com',
              'sciencedirect.com', 'pubs.aip.org', 'epubs.siam.org', 'academic.oup.com',
              'royalsocietypublishing.org', 'www.cambridge.org', 'link.springernature.com'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def nodes(value, inherited=None):
    if isinstance(value, dict):
        doi = str(value.get('doi') or value.get('DOI') or inherited or '').lower()
        yield doi, value
        for child in value.values():
            yield from nodes(child, doi)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child, inherited)


def publisher_url(url):
    u = urlsplit(url or '')
    if u.hostname not in PUBLISHERS or u.username or u.password:
        return None
    if any(s in u.path.lower() for s in ('.pdf', '/pdf/', '/search')):
        return None
    # Drop redirect diagnostics, tracking and possible credentials.
    return urlunsplit(('https', u.netloc, u.path, '', ''))


def api_url(kind, doi):
    encoded = quote(doi, safe='')
    if kind == 'crossref':
        return 'https://api.crossref.org/works/' + encoded
    if kind == 'openalex':
        return 'https://api.openalex.org/works/https://doi.org/' + encoded
    if kind == 'europepmc':
        return 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=' + quote('DOI:"'+doi+'"') + '&format=json&resultType=core&pageSize=100'
    if kind == 'pubmed':
        return 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&term=' + quote(doi+'[doi]')
    raise ValueError(kind)


def build(trial=TRIAL):
    progress = load(trial/'final-screening-progress-v1.json')
    master = {r['doi']: r for r in load(trial/'material-master-v4.json')['results']}
    remaining = {r['doi']: r for r in progress['results'] if r['decision'] == 'review'}
    routes = {doi: {} for doi in remaining}
    hashes = {}
    unreadable = []

    def add(doi, kind, url, strength, report, basis, transport='http'):
        key = (kind, url)
        candidate = {'kind': kind, 'url': url, 'priority': strength,
                     'historical_basis': basis, 'transport': transport,
                     'evidence_reports': [report]}
        old = routes[doi].get(key)
        if old:
            candidate['evidence_reports'] = sorted(set(old['evidence_reports'] + [report]))
            if old['priority'] < strength:
                candidate.update({k: old[k] for k in ('priority', 'historical_basis', 'transport')})
        routes[doi][key] = candidate

    for doi in remaining:
        if master[doi]['initial_screening_record'].get('abstract_available'):
            add(doi, 'crossref', api_url('crossref', doi), 0, 'screening-report.json', 'explicit_abstract_success')
    for path in sorted(trial.glob('*.json')):
        if path.name.startswith(('final-', 'semantic-review-', 'historical-routes-')):
            continue
        try:
            data = load(path)
        except json.JSONDecodeError as exc:
            # Old progress files can contain appended JSON fragments. They are
            # not per-DOI evidence; disclose rather than repairing old inputs.
            unreadable.append({'file': path.name, 'error': str(exc)})
            continue
        used = False
        for doi, node in nodes(data):
            if doi not in remaining or node.get('abstract_available') is not True:
                continue
            if node.get('doi_match') is False:
                continue
            used = True
            name = str(node.get('source_file') or path.name).lower()
            kind = next((k for k in ('crossref', 'europepmc', 'pubmed', 'openalex') if k in name), None)
            if kind:
                add(doi, kind, api_url(kind, doi), {'crossref': 0, 'europepmc': 2, 'pubmed': 2, 'openalex': 3}[kind],
                    path.name, 'explicit_abstract_success')
                continue
            url = publisher_url(node.get('source_url') or node.get('url'))
            if url:
                explicit = bool(node.get('abstract_basis')) and 'description' not in str(node.get('abstract_basis')).lower()
                add(doi, 'publisher', url, 1 if explicit else 5, path.name,
                    'explicit_abstract_success' if explicit else 'historical_description_or_abstract_unresolved',
                    'browser_previously' if 'browser' in name else 'http')
        if used:
            hashes[path.name] = digest(path.read_text(encoding='utf-8'))
    output = []
    for doi, previous in remaining.items():
        row = master[doi]
        material = row.get('current_material') or row['material']
        # These are fallbacks, never represented as previously successful.
        for kind in ('crossref', 'europepmc', 'openalex'):
            if (kind, api_url(kind, doi)) not in routes[doi]:
                add(doi, kind, api_url(kind, doi), 10, 'derived_from_doi', 'unverified_fallback')
        from structured_material_v9 import urls
        for url in urls(row):
            url = publisher_url(url)
            if url and ('publisher', url) not in routes[doi]:
                add(doi, 'publisher', url, 9, 'derived_from_doi', 'unverified_fallback')
        ordered = sorted(routes[doi].values(), key=lambda r: (r['priority'], r['kind'], r['url']))
        output.append({'doi': doi, 'title': row['title'], 'journal_queries': row['retrieved_by'],
                       'effective_date': material.get('preferred_date'), 'date_source': material.get('date_source'),
                       'previous_reason': previous['reason'], 'routes': ordered,
                       'master_record_sha256': digest(json.dumps(row, ensure_ascii=False, sort_keys=True))})
    return {'schema': 'historical-routes-v1', 'count': len(output), 'source_hashes': hashes,
            'unreadable_reports': unreadable,
            'first_route_counts': dict(Counter(r['routes'][0]['kind'] for r in output)),
            'historical_explicit_success_count': sum(any(x['historical_basis']=='explicit_abstract_success' for x in r['routes']) for r in output),
            'limitations': ['Historical success does not guarantee current access.',
                           'Description-only history requires a fresh explicit abstract field.',
                           'Programmatic access is attempted first; browser work is an explicit handoff.'],
            'records': output}


if __name__ == '__main__':
    path = TRIAL/'historical-routes-v1.json'
    if path.exists():
        raise FileExistsError(path)
    result = build()
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','source_hashes')}, ensure_ascii=False))
