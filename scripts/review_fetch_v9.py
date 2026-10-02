"""Bounded source adapters. Return explicit abstracts only, never descriptions."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from automated_material_batch_v9 import clean, parse_meta
from review_routes_v9 import publisher_url


def request(url):
    req = Request(url, headers={'User-Agent': 'ComplexNetworkPapers/0.1 (v9 bounded review)',
                                'Accept': 'application/json,text/html,application/xml'})
    with urlopen(req, timeout=25) as response:
        body = response.read(4_000_001)
        if len(body) > 4_000_000:
            raise ValueError('Response exceeds bound; not parsing truncated content')
        return response.geturl(), body.decode('utf-8')


def norm_doi(value):
    return str(value or '').lower().removeprefix('https://doi.org/').removeprefix('doi:').strip()


def publisher_extract(doi, page, url='', expected_title=''):
    meta = parse_meta(page)
    soup = BeautifulSoup(page, 'html.parser')
    # Citation identity only: a DOI in the references is insufficient.
    identities = [norm_doi(meta.get(k)) for k in ('citation_doi', 'dc.identifier', 'prism.doi')]
    heading = soup.select_one('h1.heading-lg-bold')
    header_title = clean(heading.get_text(' ', strip=True)) if heading else ''
    target = urlsplit(url)
    # APS accepted pages omit citation metadata. Require the exact DOI path,
    # publisher host, visible Accepted Paper label and matching article heading.
    accepted_identity = (target.hostname == 'journals.aps.org' and '/accepted/' in target.path
                         and unquote(target.path).lower().endswith('/'+doi)
                         and 'Accepted Paper' in soup.get_text(' ', strip=True)
                         and expected_title and header_title.casefold() == clean(expected_title).casefold())
    if doi not in identities and not accepted_identity:
        raise ValueError('Publisher citation DOI not confirmed')
    abstract = clean(meta.get('citation_abstract'))
    basis = 'publisher.citation_abstract'
    if not abstract:
        for selector in ('#abstract-section', 'section[data-title="Abstract"]',
                         '#Abs1-content', 'section[aria-labelledby="Abs1"]',
                         '.abstractSection', '#enc-abstract', '.abstract.author'):
            node = soup.select_one(selector)
            if node:
                abstract = re.sub(r'^Abstract\s*', '', clean(node.get_text(' ', strip=True)), flags=re.I)
                if abstract:
                    basis = 'publisher.Abstract'
                    break
    return {'title': clean(meta.get('citation_title') or meta.get('dc.title')) or header_title,
            'issns': [meta[k] for k in ('citation_issn', 'prism.issn') if meta.get(k)],
            'article_type': meta.get('citation_article_type') or meta.get('dc.type'),
            'abstract_basis': basis,
            'online_date': meta.get('citation_online_date'),
            'publication_date': meta.get('citation_publication_date') or meta.get('citation_date')}, abstract


def fetch(doi, route):
    url, body = request(route['url'])
    kind = route['kind']
    meta = {}
    abstract = ''
    if kind == 'crossref':
        item = json.loads(body)['message']
        if norm_doi(item.get('DOI')) != doi:
            raise ValueError('Crossref DOI mismatch')
        abstract = clean(item.get('abstract'))
        meta = dict(title=clean(' '.join(item.get('title', []))), issns=item.get('ISSN', []),
                    article_type=item.get('type'), published_online=item.get('published-online'),
                    published_print=item.get('published-print'), abstract_basis='crossref.abstract')
    elif kind == 'openalex':
        item = json.loads(body)
        if norm_doi(item.get('doi')) != doi:
            raise ValueError('OpenAlex DOI mismatch')
        words = [(pos, word) for word, positions in (item.get('abstract_inverted_index') or {}).items() for pos in positions]
        if words and sorted(p for p,w in words) != list(range(len(words))):
            raise ValueError('Noncontiguous abstract positions')
        abstract = ' '.join(w for p,w in sorted(words))
        meta = dict(title=item.get('title'), abstract_basis='openalex.abstract_inverted_index',
                    issns=((item.get('primary_location') or {}).get('source') or {}).get('issn') or [],
                    article_type=item.get('type'))
    elif kind == 'europepmc':
        matches = [r for r in json.loads(body).get('resultList', {}).get('result', []) if norm_doi(r.get('doi')) == doi and r.get('abstractText')]
        if not matches:
            raise ValueError('No DOI-matched Europe PMC abstract')
        item = matches[0]
        abstract = clean(item['abstractText'])
        journal = (item.get('journalInfo') or {}).get('journal') or {}
        meta = dict(title=clean(item.get('title')), abstract_basis='europepmc.abstractText',
                    issns=[journal[k] for k in ('issn','essn') if journal.get(k)])
    elif kind == 'pubmed':
        ids = json.loads(body).get('esearchresult', {}).get('idlist', [])
        if not ids or len(ids) > 10:
            raise ValueError('PubMed DOI search empty or ambiguous')
        url, xml = request('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id='+quote(','.join(ids)))
        for item in ET.fromstring(xml).findall('.//PubmedArticle'):
            if doi not in [norm_doi(n.text) for n in item.findall('.//ArticleId[@IdType="doi"]')]:
                continue
            title = item.find('.//ArticleTitle')
            abstract = ' '.join((n.get('Label','')+' '+''.join(n.itertext())).strip() for n in item.findall('.//Abstract/AbstractText'))
            meta = dict(title=''.join(title.itertext()) if title is not None else '',
                        abstract_basis='pubmed.Abstract', issns=[n.text for n in item.findall('.//Journal/ISSN') if n.text])
            break
    elif kind == 'publisher':
        if not publisher_url(url):
            raise ValueError('Unexpected publisher redirect')
        meta, abstract = publisher_extract(doi, body, url, route.get('expected_title',''))
    else:
        raise ValueError('Unsupported route kind')
    if len(abstract.split()) < 10 or any(s in abstract.lower() for s in ('verify you are human', 'access denied', 'are you a robot')):
        raise ValueError('No sufficient explicit abstract')
    if not meta.get('title'):
        raise ValueError('Missing source title')
    meta.update(doi=doi, doi_match=True, source_url=url,
                retrieved_at=datetime.now(timezone.utc).isoformat())
    return meta, abstract
