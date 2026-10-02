"""Bounded NMI bibliography pilot; no abstracts, HTML files, or topic screening."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['DOI', 'title', 'ISSN', 'container-title', 'type',
          'published-online', 'published-print', 'published', 'issued', 'URL']
DATE_FIELDS = ['published-online', 'published-print', 'published', 'issued']
DIRECTORY = 'https://www.nature.com/natmachintell/articles'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr'}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False,
                                   sort_keys=True).encode()).hexdigest()


def plain(value):
    return ' '.join(unescape(re.sub(r'<[^>]+>', '', value or '')).split())


def normalized_title(value):
    return unicodedata.normalize('NFKC', plain(value)).casefold()


def url_key(value):
    parsed = urlsplit(value or '')
    return ((parsed.hostname or '').lower().removeprefix('www.'),
            parsed.path.rstrip('/'))


def crossref_date(item):
    for field in DATE_FIELDS:
        if field not in item:
            continue
        parts = item[field].get('date-parts', [])
        if len(parts) != 1 or len(parts[0]) != 3:
            return None, field, 'incomplete_preferred_date'
        try:
            return date(*parts[0]).isoformat(), field, None
        except (TypeError, ValueError):
            return None, field, 'invalid_preferred_date'
    return None, None, 'missing_date'


class DirectoryParser(HTMLParser):
    """Only card titles, types, time attributes, pagination and year counters."""
    def __init__(self, year):
        super().__init__(convert_charrefs=True)
        self.year = year
        self.stack = []
        self.card = None
        self.cards = []
        self.pages = {1}
        self.counts = set()
        self.page_title = []
        self.issn_seen = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        role = None
        if tag == 'li' and 'app-article-list-row__item' in classes:
            if self.card is not None:
                raise ValueError('Nested or unclosed directory card')
            self.card = {'title': '', 'article_type': '', 'date': None,
                         'article_url': None}
            role = 'card'
        elif self.card is not None:
            if tag == 'a' and 'c-card__link' in classes:
                self.card['article_url'] = urljoin(DIRECTORY, attrs.get('href', ''))
                role = 'card_title'
            elif 'c-meta__type' in classes:
                role = 'card_type'
            elif tag == 'time':
                self.card['date'] = attrs.get('datetime')
        if tag == 'title':
            role = 'page_title'
        if tag == 'a' and 'c-pagination__link' in classes:
            parsed = urlsplit(urljoin(DIRECTORY, attrs.get('href', '')))
            query = parse_qs(parsed.query)
            if (parsed.hostname == 'www.nature.com'
                    and parsed.path == '/natmachintell/articles'
                    and query.get('year') == [str(self.year)]):
                self.pages.add(int(query.get('page', ['1'])[0]))
        # The current page is a span, not a link (especially on the last page).
        if tag == 'li' and 'c-pagination__item' in classes:
            number = attrs.get('data-page', '')
            if number.isdigit():
                self.pages.add(int(number))
        if tag not in VOID:
            self.stack.append((tag, role))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError('Unexpected directory markup nesting')
        _, role = self.stack.pop()
        if role == 'card':
            row = self.card
            row['title'] = plain(row['title'])
            row['article_type'] = plain(row['article_type'])
            if not row['title'] or not row['article_type'] or not row['article_url']:
                raise ValueError('Directory card lacks bibliographic fields')
            if url_key(row['article_url'])[0] != 'nature.com':
                raise ValueError('Directory card has non-publisher URL')
            if row['date']:
                date.fromisoformat(row['date'])
            self.cards.append(row)
            self.card = None

    def handle_data(self, text):
        if '2522-5839' in text:
            self.issn_seen = True
        roles = {role for _, role in self.stack}
        if 'card_title' in roles:
            self.card['title'] += text
        elif 'card_type' in roles:
            self.card['article_type'] += text
        elif 'page_title' in roles:
            self.page_title.append(text)
        # The selected year appears both in the facet button and its list.
        if any(tag == 'span' for tag, _ in self.stack):
            match = re.fullmatch(r'\s*' + str(self.year) + r'\s*\((\d+)\)\s*', text)
            if match:
                self.counts.add(int(match.group(1)))

    def finish(self):
        if self.stack or self.card is not None:
            raise ValueError('Unclosed directory markup')
        title = plain(' '.join(self.page_title))
        if ('Nature Machine Intelligence' not in title
                or str(self.year) not in title or not self.issn_seen):
            raise ValueError('Not an identified NMI annual directory')
        if len(self.counts) != 1 or not self.cards:
            raise ValueError('Missing/ambiguous annual count or empty directory')
        return {'records': self.cards, 'total': next(iter(self.counts)),
                'last_page': max(self.pages)}


class CitationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        key = attrs.get('name', '').lower()
        if tag == 'meta' and key in {'citation_doi', 'citation_title',
                                    'citation_issn', 'citation_journal_title'}:
            self.fields[key] = attrs.get('content', '')


class Client:
    def __init__(self, interval=1.0):
        self.interval = interval
        self.last = 0
        self.attempts = []

    def get(self, url):
        time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        attempt = {'url': url, 'retrieved_at': now()}
        self.attempts.append(attempt)
        request = Request(url, headers={
            'User-Agent': 'ComplexNetworkPapers/0.1 (NMI bibliographic pilot)'})
        try:
            with urlopen(request, timeout=25) as response:
                attempt['http_status'] = response.status
                # Do not persist redirect cookie/error codes or response HTML.
                attempt['final_host'] = urlsplit(response.url).hostname
                payload = response.read(8_000_001)
                if len(payload) > 8_000_000:
                    raise ValueError('Response exceeds pilot byte limit')
                attempt['bytes'] = len(payload)
                return payload.decode('utf-8')
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            attempt['error'] = type(exc).__name__
            if isinstance(exc, HTTPError):
                attempt['http_status'] = exc.code
            raise


def collect_crossref(client, start, end, rows=100, max_pages=5):
    records = {}
    queries = []
    for kind in ('online-pub-date', 'print-pub-date', 'pub-date'):
        query = {'kind': kind, 'pages': [], 'complete': False}
        queries.append(query)
        cursor = '*'
        seen_cursors = set()
        seen_dois = set()
        totals = set()
        try:
            for page in range(1, max_pages + 1):
                params = {'filter': f'from-{kind}:{start},until-{kind}:{end}',
                          'select': ','.join(FIELDS), 'rows': rows, 'cursor': cursor}
                url = 'https://api.crossref.org/journals/2522-5839/works?' + urlencode(params)
                payload = json.loads(client.get(url))
                if payload.get('status') != 'ok':
                    raise ValueError('Crossref returned non-ok envelope')
                message = payload['message']
                items = message['items']
                totals.add(message['total-results'])
                page_dois = []
                for item in items:
                    if set(item) - set(FIELDS):
                        raise ValueError('Unexpected/unselected Crossref fields')
                    doi = item.get('DOI', '').lower().strip()
                    if not doi or '2522-5839' not in item.get('ISSN', []):
                        raise ValueError('Crossref DOI or journal identity missing')
                    if doi in seen_dois:
                        raise ValueError('Repeated DOI within cursor query')
                    seen_dois.add(doi)
                    page_dois.append(doi)
                    observation = {'query': kind, 'page': page,
                                   'retrieved_at': client.attempts[-1]['retrieved_at'],
                                   'metadata': item, 'metadata_sha256': digest(item)}
                    records.setdefault(doi, []).append(observation)
                query['pages'].append({'page': page, 'url': url, 'dois': page_dois,
                                       'count': len(items), 'selected_items_sha256': digest(items)})
                if len(items) < rows:
                    query['complete'] = (len(totals) == 1 and len(seen_dois) == next(iter(totals)))
                    if not query['complete']:
                        query['error'] = 'returned_unique_count_or_total_changed'
                    break
                next_cursor = message.get('next-cursor')
                if not next_cursor or next_cursor == cursor or next_cursor in seen_cursors:
                    raise ValueError('Missing/repeated pagination cursor before terminal page')
                seen_cursors.add(cursor)
                cursor = next_cursor
            else:
                query['error'] = 'page_budget_exhausted'
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            query['error'] = type(exc).__name__ + ': ' + str(exc)[:160]
        query['reported_totals'] = sorted(totals)
        query['unique_dois'] = len(seen_dois)
    return records, queries


def collect_directory(client, year, max_pages=12, resume=None):
    coverage = {'year': year, 'pages': list(resume['pages']) if resume else [], 'complete': False}
    records = list(resume['records']) if resume else []
    seen_urls = {url_key(row['article_url']) for row in records}
    totals = set(resume['reported_totals']) if resume else set()
    expected_last = resume['expected_last_page'] if resume else None
    first_page = len(coverage['pages']) + 1
    if resume:
        if [page['page'] for page in coverage['pages']] != list(range(1, first_page)):
            raise ValueError('Resume directory pages are not consecutive')
        if len(seen_urls) != len(records):
            raise ValueError('Resume directory contains duplicate records')
        for page in coverage['pages']:
            extracted = [{k:row[k] for k in ('title','article_type','date','article_url')}
                         for row in records if row['directory_page'] == page['page']]
            if digest(extracted) != page['records_sha256'] or len(extracted) != page['count']:
                raise ValueError('Resume directory evidence hash/count mismatch')
    try:
        for page in range(first_page, max_pages + 1):
            params = {'year': year, 'page': page, 'sort': 'PubDate',
                      'searchType': 'journalSearch'}
            url = DIRECTORY + '?' + urlencode(params)
            parser = DirectoryParser(year)
            parser.feed(client.get(url))
            parsed = parser.finish()
            totals.add(parsed['total'])
            if expected_last is None:
                expected_last = parsed['last_page']
            if parsed['last_page'] != expected_last:
                raise ValueError('Directory pagination extent changed during run')
            for row in parsed['records']:
                key = url_key(row['article_url'])
                if key in seen_urls:
                    raise ValueError('Repeated article across directory pages')
                seen_urls.add(key)
                records.append(dict(row, directory_url=url, directory_page=page,
                                    retrieved_at=client.attempts[-1]['retrieved_at']))
            coverage['pages'].append({'page': page, 'url': url,
                                      'count': len(parsed['records']),
                                      'records_sha256': digest(parsed['records'])})
            if page == expected_last:
                coverage['complete'] = (len(totals) == 1 and len(records) == next(iter(totals)))
                if not coverage['complete']:
                    coverage['error'] = 'annual_count_mismatch_or_changed'
                break
        else:
            coverage['error'] = 'page_budget_exhausted'
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
        coverage['error'] = type(exc).__name__ + ': ' + str(exc)[:160]
    coverage['reported_totals'] = sorted(totals)
    coverage['expected_last_page'] = expected_last
    coverage['unique_records'] = len(records)
    coverage['records'] = records
    return coverage


def merge_records(crossref, directory, start, end, as_of, client, identity_cache=None):
    by_url = {}
    candidates = {}
    for doi, observations in crossref.items():
        item = observations[0]['metadata']
        key = url_key(item.get('URL'))
        if key[0] == 'nature.com' and key[1]:
            if key in by_url and by_url[key] != doi:
                raise ValueError('Ambiguous DOI for publisher URL')
            by_url[key] = doi
        candidates[doi] = {'doi': doi, 'title': plain(' '.join(item.get('title', []))),
                           'crossref_observations': observations,
                           'publisher_records': [], 'issues': []}
    # Only the requested window and uncertain dates need article-page identity checks.
    identity_lookups = 0
    for row in directory['records']:
        if row['date'] and not start <= row['date'] <= end:
            continue
        doi = by_url.get(url_key(row['article_url']))
        identity = None
        if doi is None:
            try:
                identity = (identity_cache or {}).get(url_key(row['article_url']))
                if identity:
                    fields = identity['metadata']
                else:
                    if identity_lookups >= 20:
                        raise ValueError('Publisher identity lookup budget exhausted')
                    identity_lookups += 1
                    parser = CitationParser()
                    parser.feed(client.get(row['article_url']))
                    fields = parser.fields
                    identity = {'metadata': fields, 'retrieved_at': client.attempts[-1]['retrieved_at'],
                                'url': row['article_url'], 'basis': 'publisher.citation_metadata'}
                if (fields.get('citation_doi')
                        and fields.get('citation_issn') == '2522-5839'
                        and normalized_title(fields.get('citation_title')) == normalized_title(row['title'])):
                    doi = fields['citation_doi'].lower().strip()
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                pass  # Kept as an explicit unresolved identity, not discarded.
        key = doi or row['article_url']
        candidate = candidates.setdefault(key, {'doi': doi, 'title': row['title'],
                                                'crossref_observations': [],
                                                'publisher_records': [], 'issues': []})
        candidate['publisher_records'].append(row)
        if identity:
            candidate['publisher_identity'] = identity
        if not doi:
            candidate['issues'].append('doi_identity_unconfirmed')
    for candidate in candidates.values():
        observations = candidate['crossref_observations']
        publisher = candidate['publisher_records']
        issues = candidate['issues']
        chosen = field = None
        if observations:
            versions = {observation['metadata_sha256'] for observation in observations}
            if len(versions) != 1:
                issues.append('crossref_metadata_changed_between_queries')
            chosen, field, error = crossref_date(observations[0]['metadata'])
            if error:
                issues.append(error)
        else:
            issues.append('crossref_date_unavailable')
        if publisher:
            dates = {row['date'] for row in publisher}
            if None in dates:
                issues.append('publisher_directory_date_missing')
            if chosen and dates != {chosen}:
                issues.append('publisher_crossref_date_conflict')
            if any(normalized_title(row['title']) != normalized_title(candidate['title']) for row in publisher):
                issues.append('publisher_crossref_title_conflict')
        elif chosen and start <= chosen <= end:
            issues.append('not_found_in_official_target_window')
        if chosen and chosen > as_of:
            issues.append('future_date')
        candidate['date'] = chosen
        candidate['date_basis'] = field
        candidate['window_status'] = ('needs_check' if issues else
                                      'in_window' if chosen and start <= chosen <= end else 'out_of_window')
        candidate['subject_scope_status'] = 'not_assessed'
    return sorted(candidates.values(), key=lambda row: (row['date'] or '', row['doi'] or row['title']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='New run directory; never overwritten')
    parser.add_argument('--as-of', required=True, type=date.fromisoformat)
    parser.add_argument('--resume-from', type=Path, help='Reuse hash-checked metadata and completed pages from a prior run')
    args = parser.parse_args()
    config = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
    journal = next(j for j in config['journals'] if j['short'] == 'NMI')
    if journal['issns'] != ['2522-5839']:
        raise ValueError('NMI pilot journal configuration changed')
    start, end = config['initial_trial']['start'], config['initial_trial']['end']
    if start[:4] != end[:4] or date.fromisoformat(end) > args.as_of:
        raise ValueError('Pilot requires a past single-year window')
    args.out.mkdir(parents=True, exist_ok=False)
    started = now()
    client = Client()
    previous = None
    identities = {}
    inherited_attempts = []
    parent_run = None
    if args.resume_from:
        previous = json.loads((args.resume_from/'coverage.json').read_text(encoding='utf-8'))
        old_packet = json.loads((args.resume_from/'candidates.json').read_text(encoding='utf-8'))
        if (previous['config_sha256'] != digest(config)
                or previous['window_start'] != start or previous['window_end'] != end
                or previous['as_of_date'] != args.as_of.isoformat()
                or not all(query['complete'] for query in previous['crossref_queries'])):
            raise ValueError('Resume requires the same configuration/window/as-of and complete Crossref queries')
        crossref = {}
        for row in old_packet['records']:
            for observation in row['crossref_observations']:
                item = observation['metadata']
                if (observation['metadata_sha256'] != digest(item)
                        or set(item) - set(FIELDS) or item['DOI'].lower() != row['doi']
                        or '2522-5839' not in item.get('ISSN', [])):
                    raise ValueError('Resume Crossref evidence hash/identity mismatch')
                crossref.setdefault(row['doi'], []).append(observation)
            if row.get('publisher_identity'):
                identity = row['publisher_identity']
                identities[url_key(identity['url'])] = identity
        queries = previous['crossref_queries']
        inherited_attempts = previous['attempts']
        parent_run = {'directory': str(args.resume_from), 'code_sha256': previous['code_sha256'],
                      'coverage_sha256': hashlib.sha256((args.resume_from/'coverage.json').read_bytes()).hexdigest(),
                      'candidates_sha256': hashlib.sha256((args.resume_from/'candidates.json').read_bytes()).hexdigest()}
        print('Reusing recorded Crossref metadata and completed directory pages...', flush=True)
    else:
        print('Collecting NMI Crossref bibliography...', flush=True)
        crossref, queries = collect_crossref(client, start, end)
    print('Reading all NMI annual directory pages...', flush=True)
    directory = collect_directory(client, int(start[:4]),
                                  resume=previous['official_directory'] if previous else None)
    rows = merge_records(crossref, directory, start, end, args.as_of.isoformat(), client, identities)
    official = {url_key(row['article_url']) for row in directory['records']
                if row['date'] and start <= row['date'] <= end}
    matched = {url_key(row['article_url']) for candidate in rows
               if candidate['crossref_observations'] for row in candidate['publisher_records']}
    counts = dict(Counter(row['window_status'] for row in rows))
    collection_complete = all(query['complete'] for query in queries) and directory['complete']
    report = {
        'run_started_at': started, 'run_finished_at': now(), 'as_of_date': args.as_of.isoformat(),
        'journal': journal, 'window_start': start, 'window_end': end,
        'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'config_sha256': digest(config),
        'budgets': {'crossref_rows': 100, 'crossref_max_pages_per_query': 5,
                    'directory_max_pages': 12, 'timeout_seconds': 25, 'min_interval_seconds': 1,
                    'publisher_identity_max_lookups': 20, 'automatic_retries': 0},
        'crossref_queries': queries, 'crossref_unique_dois': len(crossref),
        'official_directory': directory, 'official_window_count': len(official),
        'official_window_matched_crossref_count': len(official & matched),
        'official_only_urls': [row['article_url'] for row in directory['records']
                               if url_key(row['article_url']) in official - matched],
        'crossref_only_dois': [row['doi'] for row in rows if row['crossref_observations']
                              and not row['publisher_records']],
        'candidate_count': len(rows), 'window_status_counts': counts,
        'attempts': inherited_attempts + client.attempts, 'parent_run': parent_run,
        'new_requests_this_run': len(client.attempts), 'source_enumeration_complete': collection_complete,
        'window_reconciliation_complete': collection_complete and not counts.get('needs_check', 0),
        'subject_scope_screening_performed': False, 'full_abstracts_requested_or_stored': False,
        'limitations': [
            'Completeness is relative to the named official annual directory at retrieval time, not all possible publisher records.',
            'Records missing all Crossref queried dates can be found only if present in the official directory.',
            'Official directory dates are compared with Crossref; article publication histories are not audited.',
            'No separate accepted-paper channel was verified for NMI.',
            'No later recheck for delayed deposits or metadata corrections has been performed.']}
    packet = {'journal': journal['name'], 'window_start': start, 'window_end': end,
              'run_started_at': started, 'records': rows}
    for name, payload in [('candidates.json', packet), ('coverage.json', report)]:
        with (args.out/name).open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    print(json.dumps({'out': str(args.out), 'crossref_unique_dois': len(crossref),
                      'official_window_count': len(official), 'window_status_counts': counts,
                      'source_enumeration_complete': collection_complete,
                      'window_reconciliation_complete': report['window_reconciliation_complete']}, ensure_ascii=False), flush=True)
    return 0 if report['window_reconciliation_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
