"""Read public metadata with identity checks and labelled date provenance.

Raw responses, full abstracts, cookies and PDFs are never persisted.
Availability is evidence of a transient read, not a completed semantic review.
"""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from automated_material_batch_v9 import TRIAL, fetch_url, parse_meta, clean, publisher


def iso_date(value):
    value = clean(value)
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d %B, %Y', '%d %B %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse(doi, url, page):
    soup = BeautifulSoup(page, 'html.parser')
    meta = parse_meta(page)
    title = clean(meta.get('citation_title') or meta.get('dc.title') or '')
    if not title:
        heading = soup.select_one('h1.heading-lg-bold')
        title = clean(heading.get_text(' ', strip=True)) if heading else ''
    identity = clean(meta.get('citation_doi') or meta.get('dc.identifier') or '')
    identities = [identity.lower().removeprefix('https://doi.org/').removeprefix('doi:').strip()]
    identities += [a.get('href', '').lower().removeprefix('https://doi.org/') for a in soup.select('a[href^="https://doi.org/"]')]
    visible_text = clean(soup.get_text(' ', strip=True))
    identities += [m.lower() for m in re.findall(r'DOI:\s*(?:https?://doi\.org/)?(10\.\d{4,9}/[^\s<>]+)', visible_text, re.I)]
    match = doi.lower() in identities
    # Only labelled abstract nodes or explicit abstract metadata are accepted.
    abstract = clean(meta.get('citation_abstract'))
    basis = 'citation_abstract' if abstract else None
    if not abstract:
        for selector in ('#abstract-section', 'section[data-title="Abstract"]', 'section[aria-labelledby="Abs1"]', '#Abs1-content', '.abstractSection', '#enc-abstract'):
            node = soup.select_one(selector)
            if node:
                abstract = re.sub(r'^Abstract\s*', '', clean(node.get_text(' ', strip=True)), flags=re.I)
                basis = selector
                if len(abstract.split()) >= 10:
                    break
    if len(abstract.split()) < 10:
        abstract = ''
        basis = None
    if any(s in abstract.lower() for s in ('verify you are human', 'access denied', 'enable javascript')):
        abstract = ''
        basis = None
    text = visible_text
    accepted_page = '/accepted/' in url and 'Accepted Paper' in text
    published_match = re.search(r'Published\s+(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})', text)
    accepted_match = re.search(r'Accepted\s+(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})', text)
    online = iso_date(meta.get('citation_online_date'))
    published = iso_date(meta.get('citation_publication_date'))
    aps_date = iso_date(meta.get('citation_date')) if doi.startswith('10.1103/') else None
    aps_published = iso_date(published_match.group(1)) if published_match else None
    accepted = iso_date(accepted_match.group(1)) if accepted_match else None
    if doi.startswith('10.1103/') and not accepted_page:
        online = online or aps_published or aps_date
    article_type = clean(meta.get('citation_article_type') or meta.get('dc.type')) or None
    journal = meta.get('citation_journal_title')
    if doi.startswith('10.1103/') and not journal:
        heading = soup.select_one('h1.journal-title')
        journal = clean(heading.get_text(' ', strip=True)) if heading else None
    date_evidence = []
    for name in ('citation_online_date', 'citation_publication_date', 'citation_date'):
        if meta.get(name):
            date_evidence.append({'label': name, 'value': meta[name], 'url': url})
    for label, value in [('Published', aps_published), ('Accepted', accepted)]:
        if value:
            date_evidence.append({'label': label, 'value': value, 'url': url})
    terms = sorted(set(re.findall(r'\b(?:networks?|graphs?|hypergraphs?|synchroni\w+|percolation|communities|centralit\w+|epidemic\w+|topolog\w+|coupl\w+|spreading|connectiv\w+)\b', abstract, re.I)), key=str.lower)
    return {
        'doi': doi, 'source_url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'title': title or None, 'doi_match': match,
        'journal': journal,
        'issn': meta.get('citation_issn') or meta.get('prism.issn') or None,
        'article_type': article_type,
        'online_date': online, 'publication_date': published, 'accepted_date': accepted,
        'date_evidence': date_evidence,
        'publisher_status': 'accepted_paper' if accepted_page else ('published' if online else 'unverified'),
        'abstract_available': bool(abstract) and match,
        'abstract_basis': basis, 'abstract_word_count': len(abstract.split()) if match else 0,
        'abstract_sha256': hashlib.sha256(abstract.encode()).hexdigest() if abstract and match else None,
        'scope_terms': terms if match else [],
        'classification_deferred': True,
        'abstract_not_archived': True,
        'status': 'identity_confirmed' if match else 'identity_unconfirmed',
    }


def urls(row):
    doi = row['doi']
    if doi.startswith('10.1103/'):
        from automated_material_batch_v9 import APS_JOURNALS
        journal = ' '.join(row.get('retrieved_by', [])).replace('journal:', '').strip().lower()
        code = APS_JOURNALS.get(journal)
        if journal == 'reviews of modern physics':
            code = 'rmp'
        if code:
            return [f'https://journals.aps.org/{code}/abstract/{doi}', f'https://journals.aps.org/{code}/accepted/{doi}']
    if doi.startswith('10.1038/'):
        return ['https://www.nature.com/articles/' + doi.split('/', 1)[1]]
    if doi.startswith('10.1007/'):
        return ['https://link.springer.com/article/' + doi]
    return []


def one(row):
    attempts = []
    best = {'doi': row['doi'], 'publisher': publisher(row), 'status': 'no_target_url', 'abstract_available': False}
    for url in urls(row):
        try:
            final_url, status, page = fetch_url(url)
            result = parse(row['doi'], final_url, page)
            attempts.append({'url': url, 'final_url': final_url, 'http_status': status, 'status': result['status']})
            if result['doi_match']:
                best.update(result)
                if result['abstract_available'] or result['publisher_status'] == 'published':
                    break
        except Exception as exc:
            attempts.append({'url': url, 'status': 'error', 'http_status': getattr(exc, 'code', None), 'error': type(exc).__name__})
    if best['status'] == 'no_target_url' and attempts:
        best['status'] = 'identity_or_access_unresolved'
    best['attempts'] = attempts
    return best


def run(out, workers=6):
    pending = json.loads((TRIAL/'material-pending-after-elsevier-verification-corrected.json').read_text(encoding='utf-8'))
    queue = pending['missing_abstract'] + pending['missing_preferred_date_with_abstract']
    targets = [row for row in queue if row['doi'].startswith(('10.1103/', '10.1038/', '10.1007/'))]
    results = json.loads(out.read_text(encoding='utf-8')).get('results', []) if out.exists() else []
    results = [r for r in results if r.get('doi_match')]
    done = {r['doi'] for r in results}
    todo = [r for r in targets if r['doi'] not in done]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, row) for row in todo]
        for idx, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if idx % 10 == 0 or idx == len(todo):
                counts = {'target': len(targets), 'processed': len(results), 'abstract_confirmed': sum(bool(r.get('abstract_available')) for r in results), 'publisher_date_found': sum(bool(r.get('online_date') or r.get('accepted_date')) for r in results), 'identity_confirmed': sum(bool(r.get('doi_match')) for r in results)}
                payload = {'complete': idx == len(todo), 'counts': counts, 'results': sorted(results, key=lambda r: r['doi'])}
                tmp = out.with_suffix('.tmp')
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                tmp.replace(out)
                print(json.dumps(counts), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=6)
    a = ap.parse_args()
    run(a.out, a.workers)
