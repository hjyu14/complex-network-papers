"""Import bounded official Elsevier browser observations without claiming coverage.

The importer records partial bibliography for recovery. Whole-journal boundary
evidence must be established before a separate coverage audit can close the run.
No network, HTML, abstracts, cookies or article body are accepted.
"""
import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from collect_candidates import EventLog, digest, normalized_title
from import_aip_directory import check_keys
from online_date import validate_online_observation
from run_inputs import load_inputs


def normalize(bundle, journal, start, end):
    check_keys(bundle, ['version', 'journal', 'window_start', 'window_end', 'pages', 'articles'])
    if (bundle['version'] != 'elsevier-browser-bibliography-1'
            or bundle['journal'] != journal['short']
            or [bundle['window_start'], bundle['window_end']] != [start, end]
            or journal['collection']['family'] != 'elsevier'):
        raise ValueError('Bibliography does not match frozen Elsevier journal/window')
    if not 0 < len(bundle['pages']) <= journal['collection']['max_pages']:
        raise ValueError('Missing directory or page budget exceeded')
    if len(bundle['articles']) > journal['collection']['article_lookups']:
        raise ValueError('Article budget exceeded')
    articles = {}
    for a in bundle['articles']:
        check_keys(a, ['doi', 'title', 'journal', 'issn', 'available_online', 'date_label',
                       'publication_version', 'url', 'retrieved_at', 'accepted_date'])
        if a['doi'] in articles or not re.fullmatch(r'10\.1016/[^\s]+', a['doi']):
            raise ValueError('Duplicate or missing DOI')
        record = {'doi': a['doi'], 'title': a['title'], 'publisher_online_observations': [a]}
        validate_online_observation(record, journal, a)
        if a.get('accepted_date'):
            date.fromisoformat(a['accepted_date'])
            if a['accepted_date'] > a['available_online']:
                raise ValueError('Accepted date follows first online date')
        articles[a['doi']] = a
    pages, records, seen = [], [], {}
    root = urlsplit(journal['collection']['url']).path
    for p in bundle['pages']:
        check_keys(p, ['url', 'retrieved_at', 'journal', 'all_types', 'records', 'next_url'])
        target = urlsplit(p['url'])
        stamp = datetime.fromisoformat(p['retrieved_at'].replace('Z', '+00:00'))
        if (target.scheme != 'https' or target.hostname != 'www.sciencedirect.com'
                or not (target.path == root or target.path.startswith(root+'/'))
                or target.query or target.fragment or p['journal'] != journal['name']
                or p['all_types'] is not True or stamp.tzinfo is None):
            raise ValueError('Wrong or filtered official directory identity')
        for r in p['records']:
            check_keys(r, ['doi', 'title', 'article_url', 'article_type'])
            article = urlsplit(r['article_url'])
            if (article.scheme != 'https' or article.hostname != 'www.sciencedirect.com'
                    or not article.path.startswith('/science/article/pii/'+journal['collection']['pii_prefix'])
                    or not r['title']):
                raise ValueError('Wrong article/journal PII or missing title')
            identity = r.get('doi') or r['article_url']
            if r.get('doi') and not re.fullmatch(r'10\.1016/[^\s]+', r['doi']):
                raise ValueError('Wrong directory DOI')
            if identity in seen:
                if normalized_title(seen[identity]['title']) != normalized_title(r['title']) or (
                        urlsplit(seen[identity]['article_url']).path != article.path):
                    raise ValueError('Conflicting duplicate directory identity')
                continue  # Issue and press directories legitimately overlap.
            seen[identity] = r
            a = articles.get(r.get('doi'))
            if a and (normalized_title(r['title']) != normalized_title(a['title'])
                      or article.path != urlsplit(a['url']).path):
                raise ValueError('Directory/article identity mismatch')
            records.append({**r, 'date': a['available_online'] if a else None,
                'date_basis': 'publisher.available_online', 'publication_status': 'published',
                'directory_url': p['url'], 'retrieved_at': p['retrieved_at'],
                **({'publisher_date_observation': a,
                    'publisher_date_observation_sha256': digest(a)} if a else {})})
        pages.append({'url': p['url'], 'retrieved_at': p['retrieved_at'],
            'count': len(p['records']), 'records_sha256': digest(p['records']),
            'next_url': p.get('next_url')})
    if set(articles) - {r.get('doi') for r in records}:
        raise ValueError('Article date observations are outside enumerated bibliography')
    return {'channel': 'directory', 'complete': False, 'completion_basis': None,
        'error': 'whole_journal_baseline_and_boundaries_not_yet_verified',
        'pages': pages, 'reported_totals': [], 'records': records,
        'max_pages': journal['collection']['max_pages'],
        'limitations': ['Partial official observations; neither page counts nor article dates alone establish whole-journal coverage.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--input', required=True, type=Path)
    args = p.parse_args()
    from report_io import run_directory
    args.out = run_directory(args.out, Path(__file__).resolve().parents[1], writable=True)
    config, _, _ = load_inputs(args.out)
    bundle = json.loads(args.input.read_text(encoding='utf-8'))
    journal = next(j for j in config['journals'] if j['short'] == bundle['journal'])
    result = normalize(bundle, journal, config['initial_trial']['start'], config['initial_trial']['end'])
    log = EventLog(args.out/'collection-log.jsonl')
    prior = log.latest('browser_directory', journal['short'])
    if prior and not {r.get('doi') or r['article_url'] for r in prior['result']['records']} <= {
            r.get('doi') or r['article_url'] for r in result['records']}:
        raise ValueError('Incremental import must preserve previous observations')
    log.add('browser_directory', {'key': journal['short'], 'input_sha256': digest(bundle),
        'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'result': result})
    print(json.dumps({'records': len(result['records']), 'complete': False}))


if __name__ == '__main__':
    main()
