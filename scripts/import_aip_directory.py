"""Validate browser-extracted AIP bibliography and append it to a frozen run.

No network access. Input contains allowed bibliographic observations, not HTML.
Dates must come from the visible article-date field, never issue-month metadata.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs

from collect_candidates import EventLog, digest, normalized_title
from run_inputs import load_inputs


def check_keys(value, allowed):
    if set(value) - set(allowed):
        raise ValueError('Unselected input fields: '+','.join(sorted(set(value)-set(allowed))))


def official_url(url, kind):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'pubs.aip.org':
        raise ValueError('Non-AIP source URL')
    if not re.match(r'^/(?:aip/)?cha/'+kind, parsed.path):
        raise ValueError('Wrong journal/source URL')


def normalize(bundle, journal, start, end, live_as_of=None):
    check_keys(bundle, ['version','journal','window_start','window_end','pages','issues','articles'])
    if (bundle['version'] != 'aip-browser-bibliography-1' or bundle['journal'] != journal['short']
            or [bundle['window_start'],bundle['window_end']] != [start,end]):
        raise ValueError('Browser bibliography does not match frozen run')
    if not bundle['pages'] or len(bundle['pages']) > journal['collection']['max_pages']:
        raise ValueError('Missing directory or page budget exceeded')
    if len(bundle['articles']) > journal['collection']['article_lookups']:
        raise ValueError('Article lookup budget exceeded')
    articles = {}
    for a in bundle['articles']:
        check_keys(a,['doi','title','journal','issn','date_text','citation_date','url','retrieved_at'])
        official_url(a['url'], 'article/')
        if a['doi'] in articles or a['journal'] != journal['name'] or a['issn'] not in journal['issns']:
            raise ValueError('Duplicate or mismatched article identity')
        datetime.fromisoformat(a['retrieved_at'].replace('Z','+00:00'))
        day = datetime.strptime(a['date_text'], '%B %d %Y').date().isoformat()
        articles[a['doi']] = dict(a, date=day)
    seen, records, pages = set(), [], []
    previous = None
    for number, p in enumerate(bundle['pages'], 1):
        check_keys(p,['url','retrieved_at','sort','records'])
        official_url(p['url'], 'search-results')
        q = parse_qs(urlsplit(p['url']).query)
        if (int(q.get('page',['1'])[0]) != number or p['sort'] != 'Date - Newest First'
                or q.get('q') != ['*'] or q.get('sort') != ['Date - Newest First']):
            raise ValueError('Unverified pagination, sorting or whole-journal query')
        # Reject topic/collection filters and queries not using the observed all-types entry.
        if any(k.startswith('f_') for k in q) or q.get('fl_SiteID',['1000025']) != ['1000025']:
            raise ValueError('Filtered or wrong-journal directory')
        if len(p['records']) != 20:
            raise ValueError('Expected a full 20-card directory page including guard')
        datetime.fromisoformat(p['retrieved_at'].replace('Z','+00:00'))
        for r in p['records']:
            check_keys(r,['doi','title','article_url','month'])
            official_url(r['article_url'],'article/')
            doi = r['doi']
            if not re.fullmatch(r'10\.1063/[^\s]+',doi) or doi in seen:
                raise ValueError('Missing/duplicate directory DOI')
            seen.add(doi)
            a = articles.get(doi)
            if not a or urlsplit(a['url']).path != urlsplit(r['article_url']).path:
                raise ValueError('Every enumerated card needs matching article date evidence')
            # A change in title is retained as a conflict, not silently normalized away.
            row = dict(r, date=a['date'], date_basis='publisher.article_date',
                       article_type=None, publication_status='published',
                       directory_url=p['url'], directory_page=number, retrieved_at=p['retrieved_at'],
                       publisher_date_observation=a, publisher_date_observation_sha256=digest(a))
            if normalized_title(r['title']) != normalized_title(a['title']):
                row['title_identity_conflict'] = True
            if previous and row['date'] > previous:
                raise ValueError('Explicit article dates are not descending; cannot use a prefix guard')
            previous = row['date']
            records.append(row)
        pages.append({'page':number,'url':p['url'],'count':len(p['records']),
                      'records_sha256':digest(p['records']),'retrieved_at':p['retrieved_at'],
                      'newest_date':records[-20]['date'],'oldest_date':previous})
    if set(articles) != seen:
        raise ValueError('Article observations outside enumerated directory')
    if live_as_of is not None:
        if live_as_of != end:
            raise ValueError('Live snapshot must end at the frozen run as-of date')
        stamps = [p['retrieved_at'] for p in bundle['pages']]
        stamps += [a['retrieved_at'] for a in bundle['articles']]
        stamps += [i['retrieved_at'] for i in bundle['issues']]
        for stamp in stamps:
            observed = datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if observed.tzinfo is None or observed.astimezone(timezone(timedelta(hours=8))).date().isoformat() != live_as_of:
                raise ValueError('Live observations must have explicit timezone and match the as-of calendar day (Asia/Shanghai)')
        if any(r['date'] > live_as_of for r in records):
            raise ValueError('Future article in live snapshot')
    if not previous < start or (live_as_of is None and not any(r['date'] >= end for r in records)):
        raise ValueError('Directory lacks lower guard or upper boundary coverage')
    # Whole-issue DOI sets independently cross-check the in-window month and later issue(s).
    issue_months = set()
    issue_checks = []
    for issue in bundle['issues']:
        check_keys(issue,['url','month','dois','retrieved_at'])
        official_url(issue['url'],'issue/')
        date.fromisoformat(issue['month']+'-01')
        if issue['month'] in issue_months or len(issue['dois']) != len(set(issue['dois'])):
            raise ValueError('Duplicate issue month or DOI')
        issue_months.add(issue['month'])
        search_dois = {r['doi'] for r in records if datetime.strptime(r['month'],'Published: %B %Y').strftime('%Y-%m') == issue['month']}
        if set(issue['dois']) != search_dois:
            raise ValueError('Issue/search directory DOI sets differ')
        issue_checks.append(dict(issue, count=len(issue['dois']), records_sha256=digest(issue['dois'])))
    required_months = {datetime.strptime(r['month'],'Published: %B %Y').strftime('%Y-%m') for r in records if r['date'] >= start}
    if not required_months <= issue_months:
        raise ValueError('In-window and subsequent issue cross-checks missing')
    return {'channel':'directory','complete':True,
            'boundary_mode':'live_as_of_snapshot' if live_as_of else 'historical_upper_boundary',
            'as_of_date':live_as_of,
            'retrieval_interval':{'start':min(stamps),'end':max(stamps)} if live_as_of else None,
            'completion_basis':'all_type_search_prefix_with_explicit_article_dates_and_earlier_guard_plus_issue_DOI_set_checks',
            'error':None,'pages':pages,'reported_totals':[], 'records':records,
            'max_pages':journal['collection']['max_pages'],'issue_checks':issue_checks,
            'limitations':['Source-relative browser enumeration at retrieval time; no claim about later deposits or backdated unseen records.',
                           'Issue-month citation_publication_date is preserved but never used as explicit online date.'] +
                          (['Live as-of snapshot is not complete-day coverage; latest available article may precede the window end.'] if live_as_of else [])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--live-as-of', action='store_true', help='Explicit same-day source snapshot; not complete-day coverage')
    args = p.parse_args()
    from report_io import run_directory
    args.out = run_directory(args.out, Path(__file__).resolve().parents[1], writable=True)
    config, _, _ = load_inputs(args.out)
    journal = next(j for j in config['journals'] if j['short']=='Chaos' and j['collection']['family']=='aip')
    bundle = json.loads(args.input.read_text(encoding='utf-8'))
    live_as_of = None
    if args.live_as_of:
        settings = EventLog(args.out/'collection-log.jsonl').latest('settings','settings')
        if not settings:
            raise ValueError('Missing frozen collection settings')
        live_as_of = settings['as_of']
    result = normalize(bundle,journal,config['initial_trial']['start'],config['initial_trial']['end'],live_as_of)
    log = EventLog(args.out/'collection-log.jsonl')
    log.add('browser_directory', {'key':journal['short'],'input_sha256':digest(bundle),
                                 'code_sha256':__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest(),
                                 'result':result})
    print(json.dumps({'records':len(result['records']),'pages':len(result['pages']),'complete':True}))


if __name__ == '__main__':
    main()
