"""Inspect official PMC abstract elements only; do not persist XML or prose."""
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

from europepmc_fallback_v9 import fetch

TRIAL = Path(__file__).resolve().parents[1] / 'reports' / 'v9-2026-09'


def inspect_nih_ids():
    mapping = json.loads((TRIAL / 'remaining-nih-pmc-id-audit-v1.json').read_text(encoding='utf8'))
    assert mapping['complete_response'] and mapping['response_status'] == 'ok'
    rows = [r for r in mapping['results'] if r['new_pmc_identifier'] and r['doi_match']]
    out = TRIAL / 'remaining-nih-pmc-abstract-probe-v1.json'
    payload = json.loads(out.read_text(encoding='utf8')) if out.exists() else {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'input_dois': [r['doi'] for r in rows], 'results': [],
        'mapping_source': 'remaining-nih-pmc-id-audit-v1.json',
        'policy': 'Only explicit front/article-meta/abstract inspected. No body used for screening; XML and prose not archived.',
    }
    done = {r['doi'] for r in payload['results']}
    for mapped in rows:
        doi = mapped['doi']
        if doi in done:
            continue
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{mapped['pmcid']}/fullTextXML"
        row = {'doi': doi, 'pmcid': mapped['pmcid'], 'source_url': url,
               'abstract_available': False, 'abstract_not_archived': True,
               'body_used_for_semantic_screening': False,
               'retrieved_at': datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.get(url, timeout=(10, 30))
            row['http_status'] = response.status_code
            if response.status_code != 200:
                row['status'] = 'xml_http_error'
            else:
                root = ET.fromstring(response.content)
                for element in root.iter():
                    element.tag = element.tag.split('}')[-1]
                front = root.find('./front/article-meta')
                ids = [n.text.strip().lower() for n in front.findall('article-id')
                       if n.get('pub-id-type') == 'doi' and n.text] if front is not None else []
                row['doi_match'] = doi.lower() in ids
                abstracts = front.findall('abstract') if front is not None else []
                row['abstract_element_types'] = [n.get('abstract-type') for n in abstracts]
                candidates = [' '.join(' '.join(n.itertext()).split()) for n in abstracts
                              if n.get('abstract-type') in (None, 'abstract', 'summary', 'synopsis')]
                abstract = max(candidates, key=len, default='')
                row['abstract_available'] = row['doi_match'] and len(abstract.split()) >= 10
                row['abstract_word_count'] = len(abstract.split()) if row['doi_match'] else 0
                row['abstract_sha256'] = hashlib.sha256(abstract.encode()).hexdigest() if row['abstract_available'] else None
                row['abstract_basis'] = 'PMC JATS front/article-meta/abstract' if row['abstract_available'] else None
                row['archive_article_type'] = root.get('article-type')
                row['status'] = 'xml_identity_confirmed' if row['doi_match'] else 'xml_identity_unconfirmed'
        except (requests.RequestException, ET.ParseError) as exc:
            row['status'] = 'xml_request_or_parse_error'
            row['error_class'] = type(exc).__name__
        payload['results'].append(row)
        payload['complete'] = len(payload['results']) == len(rows)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(json.dumps({'processed': len(payload['results']), 'target': len(rows),
                          'last_http_status': row.get('http_status'),
                          'identity_confirmed': sum(r.get('doi_match', False) for r in payload['results']),
                          'abstract_found': sum(r['abstract_available'] for r in payload['results'])}), flush=True)
        if row.get('http_status') in (401, 403, 429):
            break
        time.sleep(1)


def inspect_oai_front():
    mapping = json.loads((TRIAL / 'remaining-nih-pmc-id-audit-v1.json').read_text(encoding='utf8'))
    assert mapping['complete_response'] and mapping['response_status'] == 'ok'
    rows = [r for r in mapping['results'] if r.get('pmcid') and r['doi_match']]
    out = TRIAL / 'remaining-nih-oai-front-probe-v1.json'
    payload = json.loads(out.read_text(encoding='utf8')) if out.exists() else {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'input_dois': [r['doi'] for r in rows], 'results': [],
        'mapping_source': 'remaining-nih-pmc-id-audit-v1.json',
        'documentation': 'https://pmc.ncbi.nlm.nih.gov/tools/oai/',
        'policy': 'Official pmc_fm metadata only; no full text requested or used for screening; abstracts transient only.',
    }
    done = {r['doi'] for r in payload['results']}
    for mapped in rows:
        doi = mapped['doi']
        if doi in done:
            continue
        url = 'https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/'
        params = {'verb': 'GetRecord', 'metadataPrefix': 'pmc_fm',
                  'identifier': 'oai:pubmedcentral.nih.gov:' + mapped['pmcid'].removeprefix('PMC')}
        row = {'doi': doi, 'pmcid': mapped['pmcid'], 'abstract_available': False,
               'archive_live': mapped.get('live'), 'archive_release_date': mapped.get('release_date'),
               'abstract_not_archived': True, 'body_used_for_semantic_screening': False,
               'retrieved_at': datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.get(url, params=params, headers={'Accept-Encoding': 'gzip, deflate'}, timeout=(10, 30))
            row['source_url'] = response.url
            row['http_status'] = response.status_code
            if response.status_code != 200:
                row['status'] = 'metadata_http_error'
            else:
                root = ET.fromstring(response.content)
                for element in root.iter():
                    element.tag = element.tag.split('}')[-1]
                error = root.find('error')
                if error is not None:
                    row['status'] = 'oai_error'
                    row['oai_error_code'] = error.get('code')
                else:
                    article = root.find('.//metadata/article')
                    front = article.find('./front/article-meta') if article is not None else None
                    ids = [n.text.strip().lower() for n in front.findall('article-id')
                           if n.get('pub-id-type') == 'doi' and n.text] if front is not None else []
                    row['doi_match'] = doi.lower() in ids
                    abstracts = front.findall('abstract') if front is not None else []
                    row['abstract_element_types'] = [n.get('abstract-type') for n in abstracts]
                    candidates = [' '.join(' '.join(n.itertext()).split()) for n in abstracts
                                  if n.get('abstract-type') in (None, 'abstract', 'summary', 'synopsis')]
                    abstract = max(candidates, key=len, default='')
                    row['abstract_available'] = row['doi_match'] and len(abstract.split()) >= 10
                    row['abstract_word_count'] = len(abstract.split()) if row['doi_match'] else 0
                    row['abstract_sha256'] = hashlib.sha256(abstract.encode()).hexdigest() if row['abstract_available'] else None
                    row['abstract_basis'] = 'PMC OAI pmc_fm front/article-meta/abstract' if row['abstract_available'] else None
                    row['archive_article_type'] = article.get('article-type') if article is not None else None
                    row['body_present_in_metadata'] = article.find('body') is not None if article is not None else None
                    row['status'] = 'metadata_identity_confirmed' if row['doi_match'] else 'metadata_identity_unconfirmed'
        except (requests.RequestException, ET.ParseError) as exc:
            row['status'] = 'metadata_request_or_parse_error'
            row['error_class'] = type(exc).__name__
        payload['results'].append(row)
        payload['complete'] = len(payload['results']) == len(rows)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(json.dumps({'processed': len(payload['results']), 'target': len(rows),
                          'last_http_status': row.get('http_status'),
                          'last_status': row['status'],
                          'identity_confirmed': sum(r.get('doi_match', False) for r in payload['results']),
                          'abstract_found': sum(r['abstract_available'] for r in payload['results'])}), flush=True)
        if row.get('http_status') in (401, 403, 429):
            break
        time.sleep(1)


def main():
    merged = json.loads((TRIAL / 'material-after-programmatic-v1.json').read_text(encoding='utf8'))
    dois = [r['doi'] for r in merged['results'] if r['collection_state'] == 'needs_material']
    requested, data, error = fetch(dois)
    assert requested == dois
    hits = data.get('resultList', {}).get('result', [])
    complete = not error and data.get('hitCount') == len(hits)
    metadata = {r.get('doi', '').lower(): r for r in hits if r.get('doi', '').lower() in dois}
    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'input_dois': dois,
               'core_response_complete': complete, 'core_hit_count': data.get('hitCount'),
               'core_error': error, 'results': [],
               'documentation': 'https://europepmc.org/RestfulWebService',
               'policy': 'Only explicit front/article-meta/abstract elements inspected; no body used for semantic screening; XML and abstract prose never archived.'}
    out = TRIAL / 'remaining-pmc-abstract-probe-v1.json'
    if not complete:
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(json.dumps({'core_complete': False, 'error': error}), flush=True)
        return
    for doi in dois:
        core = metadata.get(doi)
        row = {'doi': doi, 'doi_match': bool(core), 'abstract_available': False,
               'abstract_not_archived': True, 'body_used_for_semantic_screening': False,
               'retrieved_at': datetime.now(timezone.utc).isoformat()}
        if not core:
            row['status'] = 'not_indexed_in_core'
        else:
            row.update({'pmid': core.get('pmid'), 'pmcid': core.get('pmcid'),
                        'is_open_access': core.get('isOpenAccess'),
                        'in_pmc': core.get('inPMC'), 'in_epmc': core.get('inEPMC')})
            core_abstract = core.get('abstractText') or ''
            row['core_abstract_available'] = bool(core_abstract.strip())
            row['core_abstract_word_count'] = len(core_abstract.split())
            if core_abstract.strip():
                row['abstract_available'] = len(core_abstract.split()) >= 10
                row['abstract_sha256'] = hashlib.sha256(core_abstract.encode()).hexdigest()
                row['abstract_basis'] = 'Europe PMC core abstractText'
            pmcid = core.get('pmcid')
            if not pmcid:
                row['status'] = 'no_pmc_identifier'
            elif str(core.get('isOpenAccess')).upper() != 'Y':
                row['status'] = 'non_open_access_xml_not_requested'
            else:
                url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML'
                row['source_url'] = url
                try:
                    response = requests.get(url, timeout=(10, 30))
                    row['http_status'] = response.status_code
                    if response.status_code != 200:
                        row['status'] = 'xml_http_error'
                    else:
                        root = ET.fromstring(response.content)
                        for element in root.iter():
                            element.tag = element.tag.split('}')[-1]
                        front = root.find('./front/article-meta')
                        ids = [n.text.strip().lower() for n in front.findall('article-id')
                               if n.get('pub-id-type') == 'doi' and n.text] if front is not None else []
                        row['xml_doi_match'] = doi.lower() in ids
                        abstracts = front.findall('abstract') if front is not None else []
                        row['abstract_element_types'] = [n.get('abstract-type') for n in abstracts]
                        candidates = [' '.join(' '.join(n.itertext()).split()) for n in abstracts
                                      if n.get('abstract-type') in (None, 'abstract', 'summary', 'synopsis')]
                        abstract = max(candidates, key=len, default='')
                        row['abstract_available'] = row['xml_doi_match'] and len(abstract.split()) >= 10
                        row['abstract_word_count'] = len(abstract.split()) if row['xml_doi_match'] else 0
                        row['abstract_sha256'] = hashlib.sha256(abstract.encode()).hexdigest() if row['abstract_available'] else None
                        row['abstract_basis'] = 'PMC JATS front/article-meta/abstract' if row['abstract_available'] else None
                        row['status'] = 'xml_identity_confirmed' if row['xml_doi_match'] else 'xml_identity_unconfirmed'
                except (requests.RequestException, ET.ParseError) as exc:
                    row['status'] = 'xml_request_or_parse_error'
                    row['error_class'] = type(exc).__name__
                time.sleep(1)
        payload['results'].append(row)
        payload['complete'] = len(payload['results']) == len(dois)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        if len(payload['results']) % 10 == 0 or payload['complete']:
            print(json.dumps({'processed': len(payload['results']), 'target': len(dois),
                              'pmcid_found': sum(bool(r.get('pmcid')) for r in payload['results']),
                              'xml_requested': sum(bool(r.get('source_url')) for r in payload['results']),
                              'abstract_found': sum(r['abstract_available'] for r in payload['results'])}), flush=True)


if __name__ == '__main__':
    if '--nih-oai' in sys.argv:
        inspect_oai_front()
    elif '--nih-ids' in sys.argv:
        inspect_nih_ids()
    else:
        main()
