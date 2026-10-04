"""Whitelisted journal bibliography collection and publisher reconciliation; metadata only."""
import argparse
from run_inputs import freeze_inputs, load_inputs
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
          'published-online', 'published-print', 'published', 'issued', 'URL', 'resource']
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
    def __init__(self, year, journal=None):
        super().__init__(convert_charrefs=True)
        self.journal = journal or {"name": "Nature Machine Intelligence", "issns": ["2522-5839"], "collection": {"url": DIRECTORY}}
        self.directory = self.journal["collection"]["url"]
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
                self.card['article_url'] = urljoin(self.directory, attrs.get('href', ''))
                role = 'card_title'
            elif 'c-meta__type' in classes:
                role = 'card_type'
            elif tag == 'time':
                self.card['date'] = attrs.get('datetime')
        if tag == 'title':
            role = 'page_title'
        if tag == 'a' and 'c-pagination__link' in classes:
            parsed = urlsplit(urljoin(self.directory, attrs.get('href', '')))
            query = parse_qs(parsed.query)
            if (parsed.hostname == 'www.nature.com'
                    and parsed.path == urlsplit(self.directory).path
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
        if any(issn in text for issn in self.journal['issns']):
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
        if (self.journal['name'] not in title
                or str(self.year) not in title or not self.issn_seen):
            raise ValueError('Not an identified journal annual directory')
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


class CollectionStopped(RuntimeError):
    """A process-wide stop, never interpreted as an empty publisher result."""


class Client:
    def __init__(self, interval=1.0, log=None):
        self.log = log
        self.interval = interval
        self.last = 0
        self.attempts = []
        self.stopped = False

    def get(self, url):
        if self.stopped:
            raise CollectionStopped('HTTP 429: subsequent requests and channels stopped')
        time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        attempt = {'url': url, 'retrieved_at': now()}
        self.attempts.append(attempt)
        request = Request(url, headers={
            'User-Agent': 'ComplexNetworkPapers/0.2 (bounded bibliographic collection)'})
        try:
            with urlopen(request, timeout=25) as response:
                attempt['http_status'] = response.status
                # Do not persist redirect cookie/error codes or response HTML.
                attempt['final_host'] = urlsplit(response.url).hostname
                payload = response.read(8_000_001)
                if len(payload) > 8_000_000:
                    raise ValueError('Response exceeds pilot byte limit')
                attempt['bytes'] = len(payload)
                if self.log:
                    self.log.add('request', attempt)
                return payload.decode('utf-8')
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            attempt['error'] = type(exc).__name__
            if isinstance(exc, HTTPError):
                attempt['http_status'] = exc.code
                if exc.code == 429:
                    self.stopped = True
            if self.log:
                self.log.add('request', attempt)
            raise


def collect_crossref(client, start, end, rows=100, max_pages=5, journal=None, log=None):
    journal = journal or {"issns": ["2522-5839"], "short": "NMI"}
    records = {}
    queries = []
    for issn, kind in [(i,k) for i in journal['issns'] for k in ('online-pub-date', 'print-pub-date', 'pub-date')]:
        query = {'issn': issn, 'kind': kind, 'pages': [], 'complete': False}
        key = f"crossref:{journal['short']}:{issn}:{kind}"
        cached = log.latest('crossref_query', key) if log else None
        if cached and cached['complete']:
            queries.append(cached['query'])
            for doi, observations in cached['records'].items():
                records.setdefault(doi, []).extend(observations)
            continue
        local = {}
        queries.append(query)
        if getattr(client, 'stopped', False):
            query.update(error='not_started_rate_limit', reported_totals=[], unique_dois=0)
            if cached:
                local = cached['records']
                for doi, observations in local.items():
                    records.setdefault(doi, []).extend(observations)
            if log:
                log.add('crossref_query', {'key':key, 'complete':False, 'query':query, 'records':local})
            continue
        cursor = '*'
        seen_cursors = set()
        seen_dois = set()
        totals = set()
        try:
            for page in range(1, max_pages + 1):
                params = {'filter': f'from-{kind}:{start},until-{kind}:{end}',
                          'select': ','.join(FIELDS), 'rows': rows, 'cursor': cursor}
                url = f'https://api.crossref.org/journals/{issn}/works?' + urlencode(params)
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
                    if not doi or not set(journal['issns']) & set(item.get('ISSN', [])):
                        raise ValueError('Crossref DOI or journal identity missing')
                    if doi in seen_dois:
                        raise ValueError('Repeated DOI within cursor query')
                    seen_dois.add(doi)
                    page_dois.append(doi)
                    observation = {'query': kind, 'page': page,
                                   'retrieved_at': client.attempts[-1]['retrieved_at'],
                                   'metadata': item, 'metadata_sha256': digest(item)}
                    records.setdefault(doi, []).append(observation)
                    local.setdefault(doi, []).append(observation)
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
        if cached and not query['complete']:
            # A failed resume may be shorter; retain prior allowed metadata.
            for doi, observations in cached['records'].items():
                for observation in observations:
                    if observation not in local.setdefault(doi, []):
                        local[doi].append(observation)
                        records.setdefault(doi, []).append(observation)
            query['retained_previous_evidence'] = True
        query['reported_totals'] = sorted(totals)
        query['unique_dois'] = len(seen_dois)
        if log:
            log.add('crossref_query', {'key':key, 'complete':query['complete'], 'query':query, 'records':local})
        print(journal['short'], issn, kind, query['unique_dois'], query['complete'], flush=True)
    return records, queries


class EventLog:
    """Append-only bibliographic evidence; verify the entire chain before resuming."""
    def __init__(self, path):
        self.path = path
        self.events = []
        if path.exists():
            # JSON strings can contain U+2028/U+2029; JSONL separators are literal LF only.
            for line in path.read_text(encoding='utf-8').split('\n'):
                if not line:
                    continue
                event = json.loads(line)
                checksum = event.pop('sha256')
                if event['previous_sha256'] != self.head or digest(event) != checksum:
                    raise ValueError('Collection log hash chain mismatch')
                event['sha256'] = checksum
                self.events.append(event)

    @property
    def head(self):
        return self.events[-1]['sha256'] if self.events else None

    def add(self, kind, data):
        event = {'sequence': len(self.events)+1, 'at': now(), 'kind': kind,
                 'previous_sha256': self.head, 'data': data}
        event['sha256'] = digest(event)
        with self.path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(',', ':'))+'\n')
            handle.flush()
        self.events.append(event)
        return event['sequence']

    def latest(self, kind, key):
        for event in reversed(self.events):
            if event['kind'] == kind and event['data'].get('key') == key:
                return event['data']
        return None


def english_date(text):
    return datetime.strptime(' '.join(text.replace(',', '').split()), '%d %B %Y').date().isoformat()


def parse_aps(text, journal, channel):
    """Extract only linked titles and their explicit Published/Accepted date spans."""
    expected = journal['name']+' - '+('Recent Articles' if channel == 'recent' else 'Accepted Papers')
    head = re.search(r'<head\b[^>]*>(.*?)</head>', text, re.S)
    titles = re.findall(r'<title[^>]*>(.*?)</title>', head[1] if head else text, re.S)
    if len(titles) != 1 or plain(titles[0]) != expected:
        raise ValueError('Not an identified APS directory')
    pattern = r'<h2 class="title">(.*?)</h2>(.*?)(?=<h2 class="title">|Select page:|</main>)'
    records = []
    label = 'Published' if channel == 'recent' else 'Accepted'
    for heading, rest in re.findall(pattern, text, re.S):
        link = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', heading, re.S)
        if not link:
            continue  # Login/filter headings also use h2.title, but are not article cards.
        match = re.fullmatch(r'/'+journal['collection']['slug']+r'/(?:abstract|accepted)/(10\.1103/[^?#]+)', unescape(link[1]))
        dates = re.findall(r'<span[^>]*>[^<]*'+label+r'\s+(\d+ [A-Z][a-z]+,? \d{4})\s*</span>', rest)
        if not match or len(dates) != 1:
            raise ValueError('APS directory identity/date ambiguous')
        records.append({'doi': match[1].lower(), 'title': plain(link[2]),
                        'article_url': urljoin('https://journals.aps.org', link[1]),
                        'date': english_date(dates[0]), 'date_basis': label.lower(),
                        'article_type': None, 'publication_status': label.lower()})
    totals = re.findall(r'(\d+)\s*-\s*(\d+) of ([\d,]+) Results', plain(text))
    if not records or len(set(totals)) != 1:
        raise ValueError('APS directory count missing or empty')
    first, last, total = map(lambda s:int(s.replace(',', '')), totals[0])
    if last-first+1 != len(records):
        raise ValueError('APS range does not equal extracted count')
    return {'records': records, 'total': total, 'range_start': first,
            'range_end': last, 'last_page': (total+19)//20}


def collect_official(client, journal, start, end, log, channel=None):
    family = journal['collection']['family']
    browser = log.latest('browser_directory', journal['short'])
    if family in {'science','pnas','aip'} and browser:
        return browser['result']
    if family == 'aip':
        result = {'channel':'directory', 'complete':False,
                  'completion_basis':None, 'error':'browser_directory_not_imported',
                  'pages':[], 'reported_totals':[], 'records':[],
                  'max_pages':journal['collection']['max_pages']}
        log.add('official_result', {'key':f"official:{journal['short']}:directory:0", 'result':result})
        return result
    revision = log.latest('directory_revision', journal['short'])
    key = f"official:{journal['short']}:{channel or 'directory'}:{revision['revision'] if revision else 0}"
    records, pages = [], []
    totals, extent = set(), None
    complete, reason, error = False, None, None
    previous_date = None
    seen = set()
    budget = journal['collection']['max_pages']
    try:
        if getattr(client, 'stopped', False):
            raise ValueError('not_started_rate_limit')
        for page in range(1, budget+1):
            page_key = key+':'+str(page)
            cached = log.latest('official_page', page_key)
            if cached:
                parsed, url, stamp = cached['parsed'], cached['url'], cached['retrieved_at']
            else:
                if family == 'nature':
                    url = journal['collection']['url']+'?'+urlencode({'year': start[:4], 'page':page, 'sort':'PubDate', 'searchType':'journalSearch'})
                    parser = DirectoryParser(int(start[:4]), journal)
                    parser.feed(client.get(url))
                    parsed = parser.finish()
                elif family == 'aps':
                    url = 'https://journals.aps.org/'+journal['collection']['slug']+'/'+channel+'?'+urlencode({'page':page})
                    parsed = parse_aps(client.get(url), journal, channel)
                else:
                    # Never label a successful challenge/cookie page as an empty directory.
                    url = journal['collection']['url']
                    client.get(url)
                    raise ValueError('Publisher directory requires a verified parser; not enumerated')
                stamp = client.attempts[-1]['retrieved_at']
                log.add('official_page', {'key':page_key, 'url':url, 'retrieved_at':stamp, 'parsed':parsed})
            totals.add(parsed['total'])
            if extent is None:
                extent = parsed['last_page']
            if parsed['last_page'] != extent:
                raise ValueError('Directory pagination changed')
            if family == 'aps' and parsed['range_start'] != (page-1)*20+1:
                raise ValueError('APS ignored requested page')
            for row in parsed['records']:
                identity = row.get('doi') or str(url_key(row['article_url']))
                if identity in seen:
                    raise ValueError('Duplicate official record across pages')
                seen.add(identity)
                day = row['date']
                if not day or (previous_date and day > previous_date):
                    raise ValueError('Directory date missing or descending sort violated')
                previous_date = day
                records.append(dict(row, directory_url=url, directory_page=page, retrieved_at=stamp))
            pages.append({'page':page, 'url':url, 'count':len(parsed['records']),
                          'records_sha256':digest(parsed['records']),
                          'newest_date':parsed['records'][0]['date'], 'oldest_date':previous_date})
            print(journal['short'], channel or 'directory', 'page', page, 'oldest', previous_date, flush=True)
            if previous_date < start:
                complete, reason = True, 'descending_prefix_crossed_start_boundary'
                break
            if page == extent:
                complete = len(records) == parsed['total']
                reason = 'exhausted_directory_with_total_match' if complete else None
                if not complete:
                    error = 'directory_total_mismatch'
                break
        else:
            error = 'directory_page_budget_exhausted'
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
        error = type(exc).__name__+': '+str(exc)[:180]
        log.add('failure', {'key':key, 'error':error})
    verification = {'required':len(totals)>1, 'complete':False, 'pages':[]}
    if complete and len(totals)>1:
        # An annual counter is not a monthly total. Require a second identical
        # traversal of the entire prefix before accepting an unstable counter.
        complete = False
        try:
            for evidence in pages:
                text = client.get(evidence['url'])
                if family == 'nature':
                    parser = DirectoryParser(int(start[:4]),journal)
                    parser.feed(text)
                    checked = parser.finish()
                else:
                    checked = parse_aps(text,journal,channel)
                log.add('official_prefix_verification',{'key':key+':'+str(evidence['page']),
                        'url':evidence['url'],'parsed':checked,'retrieved_at':now()})
                if digest(checked['records']) != evidence['records_sha256'] or checked['last_page'] != extent:
                    raise ValueError('Directory prefix changed between independent traversals')
                verification['pages'].append(evidence['page'])
                print(journal['short'],'verify page',evidence['page'],flush=True)
            complete = verification['complete'] = True
            reason = 'two_identical_descending_prefix_traversals_with_start_guard'
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            error = type(exc).__name__+': '+str(exc)[:180]
            log.add('failure',{'key':key+':verification','error':error})
    result = {'channel':channel or 'directory', 'complete':complete, 'completion_basis':reason,
              'error':error, 'pages':pages, 'reported_totals':sorted(totals),
              'expected_last_page':extent, 'records':records, 'max_pages':budget,
              'annual_counter_varied':len(totals)>1, 'prefix_verification':verification}
    if not complete:
        previous = [e for e in log.events if e['kind']=='official_result'
                    and e['data']['key'].startswith(f"official:{journal['short']}:{channel or 'directory'}:")]
        if previous:
            best = max(previous, key=lambda e:len(e['data']['result']['records']))
            if len(best['data']['result']['records']) > len(records):
                result['retained_records_from_sequence'] = best['sequence']
                result['records'] = best['data']['result']['records']
                result['retained_evidence_reason'] = 'Failed shorter traversal must not discard earlier bibliographic evidence; completion remains false'
    log.add('official_result', {'key':key, 'result':result})
    return result


def supplement_crossref(client,journal,records,official,start,end,log):
    known = set()
    for src in official:
        for row in src['records']:
            if row.get('date') and not start <= row['date'] <= end:
                continue
            identity = log.latest('publisher_identity', 'identity:'+row.get('article_url',''))
            doi = row.get('doi') or (identity or {}).get('metadata', {}).get('citation_doi')
            if doi:
                known.add(doi.lower())
    missing = sorted(known-set(records))
    if len(missing)>100:
        log.add('failure', {'key':'supplement:'+journal.get('short','unknown'),
                           'error':'Crossref DOI supplement budget exhausted', 'missing_count':len(missing)})
    for doi in missing[:100]:
        if getattr(client, 'stopped', False):
            break
        key = 'supplement:'+doi
        evidence = log.latest('crossref_supplement',key)
        if not evidence:
            url = 'https://api.crossref.org/works?'+urlencode({'filter':'doi:'+doi,'select':','.join(FIELDS),'rows':1})
            evidence = {'key':key,'url':url,'retrieved_at':now(),'metadata':None}
            try:
                message = json.loads(client.get(url))['message']
                if message['total-results']==1 and len(message['items'])==1:
                    item = message['items'][0]
                    if item.get('DOI','').lower()!=doi or set(item)-set(FIELDS) or not set(item.get('ISSN',[]))&set(journal['issns']):
                        raise ValueError('Supplement DOI/ISSN/field mismatch')
                    evidence['metadata']=item
                else:
                    evidence['error']='exact_DOI_not_found'
            except (HTTPError,URLError,TimeoutError,OSError,ValueError,KeyError) as exc:
                evidence['error']=type(exc).__name__+': '+str(exc)[:160]
            log.add('crossref_supplement',evidence)
        if evidence['metadata']:
            item=evidence['metadata']
            records[doi]=[{'query':'exact_doi_supplement','retrieved_at':evidence['retrieved_at'],
                           'metadata':item,'metadata_sha256':digest(item)}]
    return len(missing)


def aps_history(client, journal, doi, log):
    key = 'history:'+doi
    cached = log.latest('publisher_history', key)
    if cached:
        return cached
    url = 'https://journals.aps.org/'+journal['collection']['slug']+'/abstract/'+doi
    text = client.get(url)
    parser = CitationParser()
    parser.feed(text)
    if parser.fields.get('citation_doi', '').lower() != doi or parser.fields.get('citation_journal_title') != journal['name']:
        raise ValueError('APS history citation identity mismatch')
    result = {'key':key, 'url':url, 'retrieved_at':now(), 'doi':doi}
    for label in ['Accepted', 'Published']:
        values = {english_date(x) for x in re.findall(label+r'\s+(\d+ [A-Z][a-z]+,? \d{4})',text)}
        if len(values) == 1:
            result[label.lower()] = next(iter(values))
        elif len(values) > 1:
            raise ValueError('Conflicting APS history dates')
    log.add('publisher_history', result)
    return result


def reconcile(crossref, official, journal, start, end, as_of, client, log):
    candidates = {}
    by_url = {}
    for doi, observations in crossref.items():
        for obs in observations:
            item = obs['metadata']
            for url in [item.get('URL'),item.get('resource',{}).get('primary',{}).get('URL')]:
                if url:
                    key = url_key(url)
                    if key in by_url and by_url[key] != doi:
                        raise ValueError('Ambiguous Crossref publisher URL')
                    by_url[key] = doi
        item = observations[0]['metadata']
        candidates[doi] = {'doi':doi, 'journal':journal['short'], 'title':plain(' '.join(item.get('title',[]))),
                           'issns':item.get('ISSN',[]), 'crossref':item, 'publisher_records':[],
                           'crossref_metadata_hashes':sorted({x['metadata_sha256'] for x in observations}),
                           'issues':[]}
    identity_count = 0
    for source in official:
        for row in source['records']:
            # Preserve guard-page evidence in the log, not in the candidate pool.
            if row['date'] and not start <= row['date'] <= end:
                continue
            doi = row.get('doi') or by_url.get(url_key(row['article_url']))
            identity = None
            failure = None
            if not doi:
                key = 'identity:'+row['article_url']
                identity = log.latest('publisher_identity', key)
                try:
                    if not identity:
                        if getattr(client, 'stopped', False):
                            raise ValueError('not_started_rate_limit')
                        if identity_count >= 40:
                            raise ValueError('Identity lookup budget exhausted')
                        identity_count += 1
                        parser = CitationParser()
                        parser.feed(client.get(row['article_url']))
                        identity = {'key':key,'metadata':parser.fields,'url':row['article_url'],'retrieved_at':now()}
                        log.add('publisher_identity', identity)
                    fields = identity['metadata']
                    if (fields.get('citation_doi') and fields.get('citation_issn') in journal['issns']
                            and normalized_title(fields.get('citation_title')) == normalized_title(row['title'])):
                        doi = fields['citation_doi'].lower()
                except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                    failure = type(exc).__name__+': '+str(exc)[:160]
                    log.add('failure', {'key':key,'error':failure})
            key = doi or row['article_url']
            candidate = candidates.setdefault(key, {'doi':doi,'journal':journal['short'],'title':row.get('title'),
                                                    'issns':[],'crossref':None,'crossref_metadata_hashes':[],
                                                    'publisher_records':[],'issues':[]})
            candidate['publisher_records'].append(row)
            if identity:
                candidate['publisher_identity'] = identity
            if not doi:
                candidate['issues'].append('doi_identity_unconfirmed')
            if failure:
                candidate['identity_failure'] = failure
    histories = 0
    for c in candidates.values():
        issues = c['issues']
        item = c['crossref']
        recheck = log.latest('bibliographic_recheck', c['doi'])
        if recheck:
            c['bibliographic_recheck'] = recheck
            if recheck.get('publication_verification_status') == 'user_confirmed_published':
                c['publication_status'] = 'published'
        publisher = log.latest('publisher_metadata', c['doi'])
        if publisher:
            if publisher['doi'] != c['doi'] or not set(publisher['issns']) & set(journal['issns']):
                raise ValueError('Publisher metadata DOI/ISSN mismatch')
            c['publisher_metadata'] = publisher
            if not c['title']:
                c['title'] = publisher['title']
            if not c['issns']:
                c['issns'] = publisher['issns']
        if c.get('publisher_identity') and not c['issns']:
            c['issns'] = [c['publisher_identity']['metadata']['citation_issn']]
        chosen, basis, error = crossref_date(item) if item else (None,None,'crossref_metadata_unavailable')
        if not item and publisher and publisher.get('date'):
            chosen, basis = publisher['date'], publisher['date_basis']
        if error:
            issues.append(error)
        if len(c['crossref_metadata_hashes']) > 1:
            issues.append('crossref_metadata_changed_between_queries')
        published = [r for r in c['publisher_records'] if r.get('publication_status') != 'accepted']
        accepted = [r for r in c['publisher_records'] if r.get('publication_status') == 'accepted']
        if published:
            c['publication_status'] = 'published'
        if any(r.get('title_identity_conflict') for r in c['publisher_records']):
            issues.append('publisher_directory_article_title_conflict')
        if not chosen and not item and published and len({r['date'] for r in published}) == 1:
            chosen, basis = published[0]['date'], 'publisher.directory_item_date'
        article_check = log.latest('publisher_article_check',c['doi'])
        if article_check and article_check.get('metadata',{}).get('citation_doi','').lower() == c['doi']:
            fields = article_check['metadata']
            if fields.get('citation_issn') in journal['issns']:
                c['publisher_article_check'] = article_check
                if not c['issns']:
                    c['issns'] = [fields['citation_issn']]
        resolution = log.latest('publisher_date_resolution',c['doi'])
        if resolution:
            c['publisher_date_evidence'] = resolution
            chosen,basis = resolution['date'],resolution['date_basis']
            c['date_resolution'] = resolution['reason']
            if item:
                issues = c['issues'] = [x for x in issues if x not in {'crossref_date_unavailable'}]
        if journal['collection']['family'] == 'aps' and item and ((not published and not accepted) or any(r['date'] != chosen for r in published)):
            try:
                if getattr(client, 'stopped', False):
                    raise ValueError('not_started_rate_limit')
                if histories >= journal['collection'].get('history_lookups', 700):
                    raise ValueError('APS publication history budget exhausted')
                histories += 1
                history = aps_history(client,journal,c['doi'],log)
                c['publisher_history'] = history
                if history.get('published') and history.get('accepted') == chosen and basis == 'published-online':
                    c['date_resolution'] = 'authorized_APS_online_equals_accepted_use_published'
                    chosen, basis = history['published'], 'publisher.published'
                elif history.get('published') and history['published'] != chosen:
                    issues.append('unresolved_APS_date_conflict')
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                c['history_failure'] = type(exc).__name__+': '+str(exc)[:160]
                issues.append('APS_history_unverified')
                log.add('failure',{'key':'history:'+str(c['doi']),'error':c['history_failure']})
        if accepted and not published:
            # A citation to an accepted list proves status, not absence of publication elsewhere.
            if c.get('publisher_history',{}).get('published'):
                issues.append('accepted_list_publication_status_conflict')
            elif (chosen and {r['date'] for r in accepted} == {chosen}) or (not chosen and len({r['date'] for r in accepted}) == 1):
                chosen = accepted[0]['date']
                c['publication_status'] = 'accepted'
                basis = 'publisher.accepted'
                c['date_resolution'] = 'authorized_accepted_paper_exception'
            else:
                issues.append('accepted_date_unresolved')
        if published and chosen and {r['date'] for r in published} != {chosen}:
            issues.append('publisher_crossref_date_conflict')
        if any(r.get('title') is not None and normalized_title(r['title']) != normalized_title(c['title']) for r in c['publisher_records']):
            issues.append('publisher_crossref_title_conflict')
        c['publisher_title_compared'] = bool(c['publisher_records']) and all(r.get('title') is not None for r in c['publisher_records'])
        if chosen and start <= chosen <= end and not c['publisher_records']:
            issues.append('not_found_in_official_target_window')
        if chosen and chosen > as_of:
            issues.append('future_date')
        c['date'], c['date_basis'] = chosen, basis
        c['window_status'] = 'needs_check' if issues else 'in_window' if chosen and start <= chosen <= end else 'out_of_window'
        c['subject_scope_status'] = 'not_assessed'
        if not c['title']:
            issues.append('title_missing')
            c['window_status'] = 'needs_check'
        # Count membership separately from spelling/metadata reconciliation.
        # Different complete days inside September do not change its DOI inventory.
        days = ([chosen] if chosen else []) + [r['date'] for r in c['publisher_records'] if r.get('date')]
        membership = {start <= day <= end for day in days}
        date_errors = {'incomplete_preferred_date', 'invalid_preferred_date', 'missing_date',
                       'future_date', 'unresolved_APS_date_conflict', 'APS_history_unverified',
                       'accepted_list_publication_status_conflict', 'accepted_date_unresolved'}
        c['window_membership'] = ('unresolved' if not c['doi'] or not days or len(membership) != 1
                                  or date_errors & set(issues)
                                  else 'in_window' if True in membership else 'out_of_window')
        c['identity_verified'] = bool(c['doi']) and bool(set(c['issns']) & set(journal['issns']))
    return sorted(candidates.values(),key=lambda c:(c['date'] or '',c['doi'] or c['title']))


def inventory_summary(rows, enumeration_complete):
    """A source-relative inventory gate, distinct from strict field reconciliation."""
    counts = dict(Counter(c['window_membership'] for c in rows))
    pending = [c['doi'] for c in rows if c['window_membership'] == 'unresolved' or not c['identity_verified']]
    human_confirmed = {c['doi'] for c in rows if c['window_membership']=='in_window' and c['identity_verified']
                       and c.get('bibliographic_recheck',{}).get('publication_verification_status')=='user_confirmed_published'
                       and c['bibliographic_recheck'].get('window_date_independently_confirmed')}
    publisher_confirmed = {c['doi'] for c in rows if c['window_membership']=='in_window'
                           and c['identity_verified'] and (c['publisher_records'] or c.get('publisher_article_check'))}
    unexplained = [c['doi'] for c in rows if c['window_membership'] == 'in_window'
                   and not c['publisher_records'] and not c.get('publisher_article_check') and c['doi'] not in human_confirmed]
    return {'window_membership_counts': counts, 'window_inventory_count': counts.get('in_window', 0),
            'publication_status_counts':dict(Counter(c.get('publication_status','unconfirmed')
                                                    for c in rows if c['window_membership']=='in_window')),
            'publisher_verified_inventory_count':len(publisher_confirmed),
            'user_confirmed_inventory_count':len(human_confirmed),
            'confirmed_inventory_count':len(publisher_confirmed | human_confirmed),
            'inventory_pending_dois': pending, 'unexplained_crossref_only_dois': unexplained,
            'candidate_inventory_complete': enumeration_complete and not pending and not unexplained,
            'metadata_reconciliation_complete': not any(c.get('issues') for c in rows)}


def cached_nmi_pilot(log, config):
    """Reuse historical evidence already in this log; fresh runs collect normally."""
    key = 'import:NMI'
    cached = log.latest('pilot_import',key)
    if not cached:
        return None
    packet, coverage = cached['packet'], cached['coverage']
    if not coverage['window_reconciliation_complete'] or packet['window_start'] != config['initial_trial']['start'] or packet['window_end'] != config['initial_trial']['end']:
        raise ValueError('NMI pilot does not match window or is incomplete')
    for row in packet['records']:
        for obs in row['crossref_observations']:
            if obs['metadata_sha256'] != digest(obs['metadata']):
                raise ValueError('NMI import metadata hash mismatch')
    return cached


def write_state(out, name, value, log):
    path = out/name
    # Previous raw versions are already in journal_result / earlier state events.
    # Reference them instead of repeatedly copying the whole nine-journal pool.
    previous = log.latest('state_update',name)
    log.add('state_update',{'key':name,'previous_state_sha256':previous.get('new_sha256') if previous else None,
                          'new_sha256':digest(value),
                          'rebuild_from_journal_result_events_through_sequence':len(log.events)})
    with path.open('w',encoding='utf-8',newline='\n') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2)
        handle.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--as-of',required=True,type=date.fromisoformat)
    parser.add_argument('--resume',action='store_true',help='Verify log and reuse completed queries/pages in this output')
    parser.add_argument('--journals',nargs='+',help='Journals belonging to this run (frozen on creation)')
    args = parser.parse_args()
    if args.resume:
        if not (args.out/'collection-log.jsonl').exists():
            raise ValueError('Resume requires existing collection log')
        config, _, inputs = load_inputs(args.out)
    else:
        # Validate selection and window before creating output.
        current = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
        names = {j['short'] for j in current['journals']}
        if args.journals and (len(args.journals) != len(set(args.journals)) or not set(args.journals) <= names):
            raise ValueError('Unknown or duplicate journal requested')
        if current['initial_trial']['start'][:4] != current['initial_trial']['end'][:4] or date.fromisoformat(current['initial_trial']['end']) > args.as_of:
            raise ValueError('Requires a past single-year window')
        args.out.mkdir(parents=True,exist_ok=False)
        config, _, inputs = freeze_inputs(args.out, ROOT, args.journals)
    start,end = config['initial_trial']['start'],config['initial_trial']['end']
    if start[:4] != end[:4] or date.fromisoformat(end) > args.as_of:
        raise ValueError('Requires a past single-year window')
    names = set(inputs['journals'])
    if args.journals and not set(args.journals) <= names:
        raise ValueError('Resume journals outside frozen run selection')
    log = EventLog(args.out/'collection-log.jsonl')
    settings = {'key':'settings','config_sha256':digest(config),'start':start,'end':end,'as_of':args.as_of.isoformat()}
    previous = log.latest('settings','settings')
    if previous and previous != settings:
        raise ValueError('Resume configuration/window/as-of mismatch')
    if not previous:
        log.add('settings',settings)
    log.add('run_start',{'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         'requested_journals':args.journals or sorted(names),
                         'budgets':{'crossref_rows':500,'crossref_pages_per_date_and_issn':8,
                                    'timeout_seconds':25,'min_request_interval_seconds':1,
                                    'automatic_retries':0,'APS_history_lookups_per_journal':700,'identity_lookups_per_journal':40,
                                    'journal_overrides':{j['short']:j['collection'] for j in config['journals']}}})
    client = Client(log=log)
    packet = json.loads((args.out/'candidates.json').read_text(encoding='utf-8')) if (args.out/'candidates.json').exists() else {'window_start':start,'window_end':end,'as_of_date':args.as_of.isoformat(),'records':[]}
    coverage = json.loads((args.out/'coverage.json').read_text(encoding='utf-8')) if (args.out/'coverage.json').exists() else {'window_start':start,'window_end':end,'journals':{},'subject_scope_screening_performed':False,
        'full_abstracts_requested_or_stored':False,'limitations':['Coverage is relative to enumerated sources at retrieval time; missing or later deposits remain possible.',
        'Descending directories are traversed from their first page to an earlier-than-window guard page; full annual directories are not claimed.',
        'Publisher access failures, unverified dates/identities, and pending journals prevent a selected-run completeness claim.',
        'No later recheck for delayed deposits; no content relevance or type screening.']}
    if args.resume:
        for name,value in [('candidates.json',packet),('coverage.json',coverage)]:
            previous_state = log.latest('state_update',name)
            if previous_state and digest(value) != previous_state['new_sha256']:
                raise ValueError('Output state differs from verified log: '+name)
    for journal in config['journals']:
        short = journal['short']
        if args.journals and short not in args.journals:
            continue
        print('START',short,flush=True)
        if short == 'NMI' and (imported := cached_nmi_pilot(log,config)):
            old = imported['coverage']
            rows = []
            for original in imported['packet']['records']:
                obs = original['crossref_observations']
                rows.append(dict(original,journal=short,crossref=obs[0]['metadata'],issns=obs[0]['metadata'].get('ISSN',[])))
                rows[-1].pop('crossref_observations')
                rows[-1]['window_membership'] = rows[-1]['window_status']
                rows[-1]['identity_verified'] = bool(set(rows[-1]['issns']) & set(journal['issns']))
            summary = {k:old[k] for k in ['crossref_queries','crossref_unique_dois','official_window_count','official_window_matched_crossref_count','official_only_urls','crossref_only_dois','window_status_counts','source_enumeration_complete','window_reconciliation_complete']}
            summary['official_sources'] = [{k:v for k,v in old['official_directory'].items() if k != 'records'}]
            summary['reused_pilot_sources'] = imported['source_files']
        else:
            cr,queries = collect_crossref(client,start,end,rows=500,max_pages=8,journal=journal,log=log)
            channels = ['recent','accepted'] if journal['collection']['family']=='aps' else [None]
            official = [collect_official(client,journal,start,end,log,ch) for ch in channels]
            query_union_count = len(cr)
            supplement_count = supplement_crossref(client,journal,cr,official,start,end,log)
            rows = reconcile(cr,official,journal,start,end,args.as_of.isoformat(),client,log)
            pub = [r for src in official for r in src['records'] if r.get('date') and start <= r['date'] <= end]
            matched = [r for c in rows if c['crossref'] for r in c['publisher_records']]
            complete = all(q['complete'] for q in queries) and all(src['complete'] for src in official)
            counts = dict(Counter(c['window_status'] for c in rows))
            summary = {'crossref_queries':queries,'crossref_query_unique_dois':query_union_count,
                       'crossref_supplement_lookups':supplement_count,'crossref_unique_dois':len(cr),'official_window_count':len(pub),
                       'official_window_matched_crossref_count':len(matched),
                       'official_sources':[{k:v for k,v in src.items() if k!='records'} for src in official],
                       'official_only_urls':[r['article_url'] for c in rows if not c['crossref'] for r in c['publisher_records']],
                       'crossref_only_dois':[c['doi'] for c in rows if c['crossref'] and not c['publisher_records']],
                       'window_status_counts':counts,'source_enumeration_complete':complete,
                       'window_reconciliation_complete':complete and not counts.get('needs_check',0)}
        summary.update(inventory_summary(rows, summary['source_enumeration_complete']))
        result = {'key':short,'records':rows,'summary':summary}
        previous_result = log.latest('journal_result',short)
        if previous_result == result:
            log.add('journal_result_reuse',{'key':short,'result_sha256':digest(result)})
        else:
            log.add('journal_result',result)
        packet['records'] = [r for r in packet['records'] if r['journal']!=short]+rows
        coverage['journals'][short] = summary
        coverage['requested_journals'] = sorted(names)
        coverage['pending_journals'] = sorted(names-set(coverage['journals']))
        coverage['nine_journal_reconciliation_complete'] = not coverage['pending_journals'] and all(s['window_reconciliation_complete'] for s in coverage['journals'].values())
        coverage['nine_journal_inventory_complete'] = not coverage['pending_journals'] and all(s.get('candidate_inventory_complete',False) for s in coverage['journals'].values())
        coverage['selected_journal_inventory_complete'] = coverage['nine_journal_inventory_complete']
        coverage['selected_journal_reconciliation_complete'] = coverage['nine_journal_reconciliation_complete']
        coverage['updated_at'] = now()
        write_state(args.out,'candidates.json',packet,log)
        write_state(args.out,'coverage.json',coverage,log)
        print('DONE',short,json.dumps(summary['window_status_counts']),summary['window_reconciliation_complete'],flush=True)
        if getattr(client, 'stopped', False):
            log.add('run_stopped', {'reason':'HTTP 429', 'pending_journals':coverage['pending_journals']})
            break
    log.add('run_finish',{'key':'latest','candidate_count':len(packet['records']),'nine_journal_reconciliation_complete':coverage['nine_journal_reconciliation_complete']})
    return 0 if coverage['nine_journal_reconciliation_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
