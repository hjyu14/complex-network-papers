"""One-paper evidence collection; semantic assessments are supplied by the reviewer."""
import argparse
from collections import Counter
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import date
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from collect_candidates import EventLog, digest, normalized_title, now, plain

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'screening-workflow-1'
PRIVATE = ROOT / '.private/abstract-cache/v9'
OLD_PRIVATE = ROOT.parent / 'papers_of_complex_networks/.private/abstract-cache/v9'
MAX_BYTES = 4 * 1024 * 1024
NON_TARGET_TYPES = {'News', 'Career Column', 'Career Feature', 'News & Views',
                    'News Feature', 'Research Highlight', 'Nature Briefing',
                    'Author Correction', 'Publisher Correction', 'Editorial',
                    'News Q&A', 'Nature Podcast', 'Book Review', 'Obituary',
                    'Career Q&A', 'Career News', 'Retraction', 'News Explainer'}


class BufferedLog:
    """Workers buffer public events; only the coordinator appends the shared log."""
    def __init__(self, events):
        self.events = list(events)
        self.pending = []

    def add(self, kind, data):
        e = {'kind': kind, 'at': now(), 'data': data}
        self.events.append(e)
        self.pending.append(e)


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def safe_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('Expected a public HTTPS URL without query or credentials')
    return url


def validate_identity(m, r):
    if m.get('doi', '').lower() != r['doi'].lower():
        raise ValueError('DOI mismatch')
    if normalized_title(m.get('title')) != normalized_title(r['title']):
        raise ValueError('Title mismatch; resolve identity before using abstract')
    if not set(m.get('issns', [])) & set(r['issns']):
        raise ValueError('Whitelist ISSN mismatch')


def validate_short_comment_review(short_review, r, decision):
    doi = r['doi']
    payload = {k:v for k,v in short_review.items() if k != 'evidence_sha256'}
    if digest(payload) != short_review.get('evidence_sha256'):
        raise ValueError('Short comment observation hash mismatch')
    if (short_review.get('doi') != doi or short_review.get('title') != r['title']
            or short_review.get('journal') != r['journal']
            or not set(short_review.get('issns', [])) & set(r['issns'])
            or short_review.get('source_url') not in decision.get('sources', [])
            or decision['hard_checks']['identity'].get('evidence_sha256') != short_review['evidence_sha256']
            or decision['hard_checks']['type'].get('value') != short_review.get('article_type')):
        raise ValueError('Short comment identity, source, type and decision evidence hash must match')
    if not (short_review.get('full_visible_comment_read') and short_review.get('identity_verified')
            and short_review.get('explicit_abstract_absent')
            and short_review.get('article_type') in {'Commentary','Perspective','Comment','Introduction','Letter','Correspondence','World View','Essay','Opinion','Expert Voices','Policy Forum','Matters Arising'}):
        raise ValueError('Short comment exception requires actual complete accessible review and verified identity/type')
    safe_url(short_review['source_url'])


def validate_material(m, r):
    validate_identity(m, r)
    if m.get('abstract_basis') not in {
            'crossref.abstract', 'publisher.Abstract', 'publisher.Abstract/browser',
            'openalex.abstract_inverted_index', 'arxiv.Abstract/user_authorized_single_record'}:
        raise ValueError('Not an explicit abstract field/section')
    if m.get('abstract_basis') == 'arxiv.Abstract/user_authorized_single_record':
        link = m.get('identity_link', {})
        if (r['doi'] != '10.1103/lvpn-gblk'
                or m.get('source_url') != 'https://arxiv.org/abs/2609.09615v1'
                or link.get('official_source_url') != 'https://journals.aps.org/prl/accepted/10.1103/lvpn-gblk'
                or normalized_title(link.get('source_title')) != normalized_title(r['title'])
                or len(link.get('official_authors', [])) != 13
                or link.get('official_authors') != link.get('source_authors')
                or link.get('authorized_use') != 'scope_exclusion_only'):
            raise ValueError('Author abstract exception is limited to the single authorized DOI and matched author/title record')
    safe_url(m['source_url'])
    if not m.get('retrieved_at'):
        raise ValueError('Missing retrieval time')
    text = m.get('abstract', '')
    if not isinstance(text, str) or not text.strip() or len(text) > 50000:
        raise ValueError('Missing/oversized abstract')
    if text.strip().casefold().rstrip('.') == 'international audience':
        raise ValueError('Repository audience label is not an abstract')
    if text.lstrip().casefold().startswith('data supplement for the publication'):
        raise ValueError('Dataset description is not an article abstract')
    if re.search(r'<(?:html|body|script|p|jats:)\b', text, re.I):
        raise ValueError('Cache must contain plain abstract text only')
    if sha(text) != m.get('abstract_sha256'):
        raise ValueError('Abstract hash mismatch')


def rebuild_abstract(index):
    if not index:
        return None
    words = {}
    for word, positions in index.items():
        for pos in positions:
            if type(pos) is not int or pos < 0 or pos in words:
                raise ValueError('Invalid/duplicate abstract position')
            words[pos] = word
    if sorted(words) != list(range(len(words))):
        raise ValueError('Missing abstract positions')
    return ' '.join(words[pos] for pos in range(len(words))) or None


class AbstractParser(HTMLParser):
    """Only explicit Abstract containers and bibliographic meta; never retain body HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.text, self.meta = [], [], {}
        self.aps_content, self.in_aps_content = [], False
        self.page_title, self.headings, self.visible_dois, self.visible_issns = [], [], set(), set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = a.get('name', '').lower()
            if key.startswith('citation_') or key in {'dc.type', 'dc.identifier'}:
                self.meta.setdefault(key, []).append(a.get('content', ''))
        if tag in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                   'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            return
        explicit = (a.get('data-title', '').lower() == 'abstract'
                    or a.get('id', '').lower() in {'abs1', 'abstract', 'abstract-section'}
                    or 'abstract' in a.get('class', '').split())
        if a.get('id') == 'abstract-section-content':
            self.in_aps_content = True
        blocked = tag in {'script', 'style', 'h2', 'h3', 'dialog'}
        self.stack.append((tag, explicit, blocked, a.get('id') == 'abstract-section-content'))
        if tag == 'h1':
            self.headings.append('')

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                self.in_aps_content = any(s[3] for s in self.stack)
                break

    def handle_data(self, text):
        if any(s[0] == 'title' for s in self.stack) and any(s[0] == 'head' for s in self.stack):
            self.page_title.append(text)
        if self.headings and any(s[0] == 'h1' for s in self.stack):
            self.headings[-1] += text
        # Retain only explicitly labelled bibliographic values, not surrounding body text.
        if not any(s[1] or s[2] for s in self.stack):
            self.visible_dois.update(re.findall(r'DOI:\s*(?:https://doi.org/)?(10\.\d{4,9}/[^\s<>]+)', text, re.I))
            self.visible_issns.update(re.findall(r'ISSN\s+(\d{4}-[\dXx]{4})', text))
        if any(s[1] for s in self.stack) and not any(s[2] for s in self.stack):
            self.text.append(text)
            if self.in_aps_content and any(s[0] == 'p' for s in self.stack):
                self.aps_content.append(text)

    def material(self, url):
        def first(key):
            return next(iter(self.meta.get(key, [])), '')
        material = {'doi': first('citation_doi').lower(), 'title': first('citation_title'),
                'issns': self.meta.get('citation_issn', []),
                'article_type': first('citation_article_type') or first('dc.type'),
                'published_date': first('citation_online_date') or first('citation_publication_date'),
                'source_url': url, 'abstract_basis': 'publisher.Abstract',
                'abstract': plain(' '.join(self.aps_content if self.aps_content else self.text)), 'retrieved_at': now()}
        # APS accepted pages have no citation meta. Require visible DOI, journal/page
        # title, article heading and footer ISSN together; URL alone is insufficient.
        p = urlsplit(url)
        match = re.fullmatch(r'/(prx|prl)/accepted/(10\.1103/[^/]+)', p.path)
        journals = {'prx': 'Physical Review X', 'prl': 'Physical Review Letters'}
        page_title = plain(' '.join(self.page_title))
        headings = [plain(h) for h in self.headings]
        if not material['doi'] and p.hostname == 'journals.aps.org' and match:
            journal, doi = journals[match[1]], match[2].lower()
            prefix = journal+' - Accepted Paper: '
            if page_title.startswith(prefix) and journal in headings and doi in {d.lower() for d in self.visible_dois}:
                # The HTML title may omit math (isotopes/subscripts). Use the
                # actual primary article h1; downstream candidate matching remains mandatory.
                title = headings[1] if len(headings)>1 and headings[0]==journal else ''
                if title and self.visible_issns:
                    material.update(doi=doi, title=title, issns=sorted(self.visible_issns),
                                    identity_basis='APS accepted-page journal/title prefix, visible DOI, primary article h1 and footer ISSN')
        # Regular APS pages omit citation_issn but expose the journal ISSN in
        # their footer. Require the explicit journal metadata and matching DOI/title.
        if not material['issns'] and p.hostname == 'journals.aps.org':
            expected = {'prl': 'Physical Review Letters', 'prx': 'Physical Review X'}
            part = p.path.split('/')[1] if len(p.path.split('/')) > 1 else ''
            if (first('citation_journal_title') == expected.get(part)
                    and material['doi'] in self.visible_dois
                    and plain(material['title']) in headings and self.visible_issns):
                material.update(issns=sorted(self.visible_issns),
                                identity_basis='Explicit APS citation DOI/title/journal plus visible footer ISSN')
        return material


class Workflow:
    def __init__(self, out, allow_rule_change=False):
        self.out = Path(out).resolve()
        self.pool = json.loads((self.out/'candidates.json').read_text(encoding='utf-8'))
        self.records = {r['doi']: r for r in self.pool['records']}
        self.config = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
        self.input_sha = hashlib.sha256((self.out/'candidates.json').read_bytes()).hexdigest()
        self.rule_sha = digest({'protocol': (ROOT/'docs/screening-protocol.md').read_text(encoding='utf-8'),
                                'config': self.config, 'version': VERSION})
        self.log = EventLog(self.out/'screening-log.jsonl')
        # Public Crossref permits one simultaneous request. Four paper workers
        # may still overlap requests to different sources.
        self.crossref_gate = threading.Lock()
        self.crossref_schedule = {'last_started': 0.0}
        if self.log.events:
            start = self.log.events[0]['data']
            expected_rule = next((e['data']['rule_sha256'] for e in reversed(self.log.events)
                                  if e['kind'] == 'rules_revised'), start['rule_sha256'])
            if start['candidate_sha256'] != self.input_sha or (expected_rule != self.rule_sha and not allow_rule_change):
                raise ValueError('Fixed input/rules changed; preserve log and create a separate review run')

    def adopt_rules(self):
        if self.active():
            raise ValueError('Finish active paper before adopting a workflow revision')
        old = next((e['data']['rule_sha256'] for e in reversed(self.log.events)
                    if e['kind'] == 'rules_revised'), self.log.events[0]['data']['rule_sha256'])
        self.log.add('rules_revised', {'previous_rule_sha256': old, 'rule_sha256': self.rule_sha,
                     'authorization': 'User requested larger batches and automatic acquisition detection with difficult sources deferred',
                     'change': 'Acquisition scheduling only; scientific scope, date/type criteria and privacy constraints unchanged; preserve previous assessments and their rule hashes'})
        return self.status()

    def init(self):
        if self.log.events:
            raise ValueError('Run already initialized')
        inside = [r for r in self.records.values() if r['window_membership'] == 'in_window']
        sample = []
        for j in self.config['journals']:
            sample.append(min((r for r in inside if r['journal'] == j['short']),
                              key=lambda r: (r['date'], r['doi']))['doi'])
        # A declared targeted example checks the semantic boundary; no automatic label.
        extra = '10.1038/s41467-026-75453-3'
        if extra not in {r['doi'] for r in inside}:
            raise ValueError('Expected targeted example is not in fixed window')
        sample.append(extra)
        self.log.add('run_started', {'version': VERSION, 'candidate_sha256': self.input_sha,
                     'rule_sha256': self.rule_sha, 'window': [self.pool['window_start'], self.pool['window_end']],
                     'eligible_inventory': len(inside), 'batch_dois': sample,
                     'selection': 'Earliest (date, doi) per configured journal; plus declared NC network-science example. Not a prevalence sample.',
                     'original_sha256': {name: hashlib.sha256((self.out/name).read_bytes()).hexdigest()
                        for name in ['candidates.json', 'coverage.json', 'collection-log.jsonl']}})

    def active(self):
        if getattr(self, 'collection_doi', None):
            return self.collection_doi
        active = None
        for e in self.log.events:
            if e['kind'] == 'paper_started':
                if active:
                    raise ValueError('Multiple active papers')
                active = e['data']['doi']
            if e['kind'] == 'assessment':
                if e['data']['doi'] != active:
                    raise ValueError('Assessment is not for active paper')
                active = None
        return active

    def next(self):
        if not self.log.events:
            raise ValueError('Initialize run first')
        active = self.active()
        if not active:
            assessed = {e['data']['doi'] for e in self.log.events
                        if e['kind'] in {'assessment', 'material_deferred'}}
            batches = [e['data']['batch_dois'] for e in self.log.events
                       if e['kind'] in {'run_started', 'batch_selected'}]
            active = next((d for batch in batches for d in batch if d not in assessed), None)
            if active:
                self.log.add('paper_started', {'doi': active, 'record_sha256': digest(self.records[active])})
        if not active:
            return {'batch_complete': True, **self.status()}
        r = self.records[active]
        material = self.current_material()
        return {'doi': active, 'title': r['title'], 'journal': r['journal'], 'date': r['date'],
                'date_basis': r['date_basis'], 'issues': r['issues'],
                'publisher_records': r.get('publisher_records', []),
                'material_ready': bool(material), 'abstract': material['abstract'] if material else None,
                'abstract_sha256': material['abstract_sha256'] if material else None}

    def batch(self, size, dois=None):
        if not self.log.events or self.active():
            raise ValueError('Finish the active paper before selecting another batch')
        selected = {d for e in self.log.events if e['kind'] in {'run_started', 'batch_selected'}
                    for d in e['data']['batch_dois']}
        assessed = {e['data']['doi'] for e in self.log.events
                    if e['kind'] in {'assessment', 'material_deferred'}}
        if selected - assessed:
            raise ValueError('Finish the selected batch before adding another')
        if dois:
            if not 1 <= len(dois) <= 100 or len(set(dois)) != len(dois) or any(d in selected or d not in self.records
                   or self.records[d]['window_membership'] != 'in_window' for d in dois):
                raise ValueError('Explicit selection must contain new, distinct, in-window DOIs')
            picked = dois
            basis = 'Explicit targeted DOI selection; not a prevalence sample'
        else:
            if not 1 <= size <= 100:
                raise ValueError('Keep each batch between 1 and 100 papers')
            remaining = [r for r in self.records.values() if r['window_membership'] == 'in_window'
                         and r['doi'] not in selected]
            # One earliest record per journal per round; deterministic and topic-independent.
            queues = [sorted((r for r in remaining if r['journal'] == j['short']),
                             key=lambda r: (r['date'], r['doi'])) for j in self.config['journals']]
            picked = []
            while len(picked) < size and any(queues):
                for q in queues:
                    if q and len(picked) < size:
                        picked.append(q.pop(0)['doi'])
            basis = 'Configured-journal round-robin; earliest remaining (date, doi) within each journal; no topic filter'
        self.log.add('batch_selected', {'batch_dois': picked, 'selection': basis})
        return {'batch_dois': picked, 'selection': basis}

    def collect_batch(self, workers=4):
        if self.active() or not 1 <= workers <= 4:
            raise ValueError('No active single paper; use 1–4 collection workers')
        batch = next(e['data']['batch_dois'] for e in reversed(self.log.events)
                     if e['kind'] in {'run_started', 'batch_selected'})
        done = {e['data']['doi'] for e in self.log.events if e['kind'] in
                {'assessment', 'material_deferred', 'automatic_material_complete'}}
        pending = [d for d in batch if d not in done]
        start = time.monotonic()
        self.log.add('automatic_batch_started', {'batch_dois': pending, 'workers': workers,
                     'channels': ['cache', 'crossref', 'publisher', 'openalex'],
                     'browser_policy': 'Deferred; no browser in automatic detection'})
        snapshot = list(self.log.events)
        stop = threading.Event()

        def collect(doi):
            w = object.__new__(Workflow)
            w.__dict__ = {**self.__dict__, 'log': BufferedLog(snapshot), 'collection_doi': doi,
                          'request_stop': stop}
            t = time.monotonic()
            r = self.records[doi]
            types = {p['article_type'] for p in r.get('publisher_records', []) if p.get('article_type')}
            if len(types) == 1 and types <= NON_TARGET_TYPES:
                return doi, 'type_evidence_ready', time.monotonic()-t, w.log.pending
            try:
                w.fetch_active()
                result = ('abstract_ready' if w.current_material() else
                          'deferred_rate_limit' if stop.is_set() else 'deferred')
            except Exception as e:
                w.log.add('automatic_collection_failed', {'doi': doi, 'error_type': type(e).__name__,
                          'reason': 'Collection failed; no semantic assessment made'})
                result = 'deferred'
            return doi, result, time.monotonic()-t, w.log.pending

        counts = Counter()
        submitted = set()
        remaining = iter(pending)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            active = {}
            def submit():
                if stop.is_set():
                    return
                doi = next(remaining, None)
                if doi is not None:
                    active[executor.submit(collect, doi)] = doi
                    submitted.add(doi)
            for _ in range(workers):
                submit()
            while active:
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for f in done:
                    active.pop(f)
                    doi, result, elapsed, events = f.result()
                    for e in events:
                        self.log.add(e['kind'], {**e['data'], 'observed_at': e['at']})
                    data = {'doi': doi, 'result': result, 'seconds': round(elapsed, 3)}
                    self.log.add('automatic_material_complete', data)
                    if result.startswith('deferred'):
                        self.log.add('material_deferred', {**data, 'subject_scope_status': 'not_assessed',
                                     'reason': ('HTTP 429 stopped this batch before usable material; defer acquisition, not a claim that no abstract exists'
                                                if result == 'deferred_rate_limit' else
                                                'No verified abstract from automatic channels; later browser or user evidence required')})
                    counts[result] += 1
                    print(json.dumps(data, ensure_ascii=False), flush=True)
                    submit()
        for doi in pending:
            if doi not in submitted:
                data = {'doi': doi, 'result': 'not_started_rate_limit', 'seconds': None}
                self.log.add('automatic_material_complete', data)
                self.log.add('material_deferred', {**data, 'subject_scope_status': 'not_assessed',
                             'reason': 'HTTP 429 stopped new submissions; source availability and scientific scope remain unassessed'})
                counts['not_started_rate_limit'] += 1
        result = {'papers': len(pending), 'seconds': round(time.monotonic()-start, 3),
                  'workers': workers, 'results': dict(counts)}
        self.log.add('automatic_batch_completed', result)
        return result

    def review_pack(self, limit=30):
        """Print private material only for actually ready, not-yet-assessed papers."""
        assessed = {d['doi'] for d in self.assessments()}
        selected = [d for e in self.log.events if e['kind'] in {'run_started', 'batch_selected'}
                    for d in e['data']['batch_dois']]
        deferred = {e['data']['doi'] for e in self.log.events if e['kind'] == 'material_deferred'}
        pack = []
        for doi in selected:
            if doi in assessed or doi in deferred:
                continue
            w = object.__new__(Workflow)
            w.__dict__ = {**self.__dict__, 'collection_doi': doi}
            r = self.records[doi]
            m = w.current_material()
            types = {p['article_type'] for p in r.get('publisher_records', []) if p.get('article_type')}
            if not m and not (len(types) == 1 and types <= NON_TARGET_TYPES):
                continue
            pack.append({'doi': doi, 'record': r, 'material': m})
            if len(pack) >= limit:
                break
        return pack

    def decide_pack(self, decisions):
        """Persist reviewer-written decisions; no keyword or automatic semantic labels."""
        for d in decisions:
            active = self.next()
            if active.get('doi') != d['doi']:
                raise ValueError('Review decisions must follow the ready-paper selection order')
            self.decide(d)
        return self.status()

    def current_material(self):
        active = self.active()
        rejected = {e['data']['material_sha256'] for e in self.log.events
                    if e['kind'] == 'material_rejected' and e['data']['doi'] == active}
        for e in reversed(self.log.events):
            if e['kind'] == 'material_cached' and e['data']['doi'] == active:
                if e['data']['material_sha256'] in rejected:
                    continue
                path = ROOT/e['data']['cache_path']
                if not path.resolve().is_relative_to(PRIVATE.resolve()):
                    raise ValueError('Cache path escaped private directory')
                m = json.loads(path.read_text(encoding='utf-8'))
                validate_material(m, self.records[active])
                if digest(m) != e['data']['material_sha256']:
                    raise ValueError('Cache version changed')
                return m
        return None

    def cache(self, m):
        r = self.records[self.active()]
        validate_material(m, r)
        folder = PRIVATE/sha(r['doi'])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/(digest(m)+'.json')
        if not path.exists():
            with path.open('x', encoding='utf-8', newline='\n') as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
                f.write('\n')
        self.log.add('material_cached', {'doi': r['doi'], 'cache_path': path.relative_to(ROOT).as_posix(),
                      'material_sha256': digest(m), 'abstract_sha256': m['abstract_sha256'],
                      'source_url': m['source_url'], 'abstract_basis': m['abstract_basis'],
                      'retrieved_at': m['retrieved_at'], 'imported_from': m.get('imported_from')})

    def attempt(self, channel, url, result, **extra):
        previous = [e for e in self.log.events if e['kind'] == 'source_attempt' and e['data']['doi'] == self.active()]
        self.log.add('source_attempt', {'doi': self.active(), 'order': len(previous)+1,
                     'channel': channel, 'source_url': url, 'result': result, **extra})

    def fetch(self, channel):
        if not self.active():
            raise ValueError('Run next first')
        r = self.records[self.active()]
        if self.current_material():
            raise ValueError('Material ready: assess before continuing channels')
        previous = [e['data']['channel'] for e in self.log.events
                    if e['kind'] == 'source_attempt' and e['data']['doi'] == r['doi']]
        order = ['cache', 'crossref', 'publisher', 'openalex']
        if not getattr(self, 'authorized_supplement_route', False) and (channel in previous or previous != order[:order.index(channel)]):
            raise ValueError('Use each channel once in cache, crossref, publisher, openalex order')
        if channel == 'cache':
            if getattr(self, 'fresh_network', False):
                self.attempt(channel, None, 'benchmark_bypass', next_reason='Fresh-network benchmark: local cache deliberately excluded')
                return {'result': 'benchmark_bypass'}
            paths = list((PRIVATE/sha(r['doi'])).glob('*.json')) + list((OLD_PRIVATE/sha(r['doi'])).glob('*.json'))
            for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    m = json.loads(path.read_text(encoding='utf-8'))
                    validate_material(m, r)
                except (ValueError, KeyError) as e:
                    self.log.add('cache_rejected', {'doi': r['doi'], 'reason': str(e), 'path': str(path)})
                    continue
                m = {**m, 'imported_from': str(path), 'imported_at': now()}
                self.cache(m)
                self.attempt(channel, None, 'usable', stop_reason='Verified DOI, title, ISSN and content hash; assess now')
                return self.next()
            self.attempt(channel, None, 'missing', next_reason='No verified per-DOI cache; try Crossref')
            return {'result': 'missing'}
        if channel == 'crossref':
            url = 'https://api.crossref.org/works/'+quote(r['doi'], safe='')
        elif channel == 'openalex':
            url = 'https://api.openalex.org/works/https://doi.org/'+quote(r['doi'], safe='')
        else:
            url = next((x['article_url'] for x in r.get('publisher_records', []) if x.get('article_url')),
                       r.get('crossref', {}).get('resource', {}).get('primary', {}).get('URL'))
            if not url:
                self.attempt(channel, None, 'missing_url', next_reason='Try OpenAlex')
                return {'result': 'missing_url'}
        safe_url(url)
        response_limits = {}
        try:
            with self.crossref_gate if channel == 'crossref' and hasattr(self, 'crossref_gate') else nullcontext():
                stop = getattr(self, 'request_stop', None)
                if stop is not None and stop.is_set():
                    self.attempt(channel, url, 'stopped_rate_limit',
                                 next_reason='Shared stop signal: no new HTTP request made')
                    return {'result': 'stopped_rate_limit'}
                if channel == 'crossref' and hasattr(self, 'crossref_schedule'):
                    delay = max(0, .25-(time.monotonic()-self.crossref_schedule['last_started']))
                    if delay and stop is not None and stop.wait(delay):
                        self.attempt(channel, url, 'stopped_rate_limit',
                                     next_reason='Rate-limit stop while waiting; no HTTP request made')
                        return {'result': 'stopped_rate_limit'}
                    if delay and stop is None:
                        time.sleep(delay)
                    self.crossref_schedule['last_started'] = time.monotonic()
                with urlopen(Request(url, headers={'User-Agent': 'ComplexNetworkPapers/1.0 (bounded scholarly screening)'}), timeout=30) as response:
                    body = response.read(MAX_BYTES+1)
                    code = response.status
                    final_host = urlsplit(response.url).hostname
                    response_limits = {k: str(response.headers[k])[:100] for k in
                        ['x-api-pool', 'x-rate-limit-limit', 'x-rate-limit-interval', 'x-concurrency-limit', 'retry-after']
                        if response.headers.get(k)}
            if len(body) > MAX_BYTES:
                raise ValueError('Response exceeded 4 MB budget')
            if channel == 'crossref':
                x = json.loads(body)['message']
                m = {'doi': x['DOI'].lower(), 'title': ' '.join(x.get('title', [])),
                     'issns': x.get('ISSN', []), 'source_url': url, 'retrieved_at': now(),
                     'abstract_basis': 'crossref.abstract', 'abstract': plain(x.get('abstract', '')),
                     'transform': 'JATS/HTML tags removed; entities decoded; whitespace collapsed'}
            elif channel == 'openalex':
                x = json.loads(body)
                sources = [a.get('source') or {} for a in x.get('locations', [])]
                m = {'doi': (x.get('doi') or '').removeprefix('https://doi.org/').lower(),
                     'title': x.get('title', ''), 'issns': sorted({s for a in sources for s in a.get('issn', []) or []}),
                     'source_url': url, 'retrieved_at': now(), 'abstract_basis': 'openalex.abstract_inverted_index',
                     'abstract': rebuild_abstract(x.get('abstract_inverted_index')) or ''}
            else:
                parser = AbstractParser()
                parser.feed(body.decode('utf-8'))
                m = parser.material(url)
            if channel == 'publisher' and not m.get('doi'):
                challenged = any(marker in body.lower() for marker in
                                 [b'cf-chl', b'just a moment', '正在进行安全验证'.encode()])
                self.attempt(channel, url, 'access_challenge' if challenged else 'unidentified_response',
                             http_status=code, final_host=final_host,
                             next_reason='Cannot establish article identity; try OpenAlex, then normal browser')
                return {'result': 'access_challenge' if challenged else 'unidentified_response'}
            validate_identity(m, r)
            if not m.get('abstract'):
                self.attempt(channel, url, 'no_explicit_abstract', http_status=code, final_host=final_host,
                             request_limits=response_limits,
                             verified_metadata={k:m.get(k) for k in ['doi','title','issns','article_type','published_date']},
                             next_reason='Try next authorized channel; absence is not scope exclusion')
                return {'result': 'no_explicit_abstract'}
            m['abstract_sha256'] = sha(m['abstract'])
            self.cache(m)
            self.attempt(channel, url, 'usable', http_status=code, final_host=final_host,
                         request_limits=response_limits,
                         abstract_sha256=m['abstract_sha256'], abstract_basis=m['abstract_basis'],
                         stop_reason='Identity-matched explicit abstract cached; assess now')
            return self.next()
        except HTTPError as e:
            if e.code == 429 and getattr(self, 'request_stop', None) is not None:
                self.request_stop.set()
            self.attempt(channel, url, 'http_error', http_status=e.code,
                         request_limits={k: str(e.headers[k])[:100] for k in
                            ['x-api-pool', 'x-rate-limit-limit', 'x-rate-limit-interval', 'x-concurrency-limit', 'retry-after']
                            if e.headers and e.headers.get(k)},
                         next_reason=('HTTP 429: stop batch submissions and subsequent channels'
                                      if e.code == 429 and getattr(self, 'request_stop', None) is not None
                                      else 'Stop this channel; try next authorized source'))
        except (URLError, TimeoutError, ValueError, KeyError, UnicodeError) as e:
            # Do not log raw network exceptions: they may contain redirected URLs.
            self.attempt(channel, url, 'rejected_or_failed', error_type=type(e).__name__,
                         reason=str(e) if isinstance(e, (ValueError, KeyError)) else 'Request failed within budget',
                         next_reason='Try next authorized channel or resolve identity')
        return {'result': 'failed'}

    def import_material(self, path):
        if not self.active() or self.current_material():
            raise ValueError('Import requires an active paper without ready material')
        p = Path(path).resolve()
        if not p.is_relative_to((ROOT/'.private/work').resolve()):
            raise ValueError('Manual material must be staged in new project .private/work')
        m = json.loads(p.read_text(encoding='utf-8'))
        self.cache(m)
        self.attempt('browser', m['source_url'], 'usable', abstract_basis=m['abstract_basis'],
                     abstract_sha256=m['abstract_sha256'], stop_reason='Explicit official Abstract; assess now')
        return self.next()

    def fetch_active(self):
        """Run remaining ordered channels for one active DOI, stopping at usable material."""
        if not self.active():
            raise ValueError('Run next first')
        previous = {e['data']['channel'] for e in self.log.events
                    if e['kind'] == 'source_attempt' and e['data']['doi'] == self.active()}
        for channel in ['cache', 'crossref', 'publisher', 'openalex']:
            if getattr(self, 'request_stop', None) is not None and self.request_stop.is_set():
                break
            if self.current_material():
                break
            if channel not in previous:
                self.fetch(channel)
        return self.next()

    def decide(self, decision):
        doi = self.active()
        if decision.get('doi') != doi or not doi:
            raise ValueError('Decision must match active DOI')
        r = self.records[doi]
        m = self.current_material()
        category = decision['category']
        if category not in {'core', 'transferable_application', 'excluded', 'review'}:
            raise ValueError('Invalid assessment category')
        if not decision.get('reason') or not decision.get('evidence_summary') or not decision.get('reviewer'):
            raise ValueError('An actual reviewer, specific reason and evidence summary are required')
        if len(decision['evidence_summary'].split()) > 40:
            raise ValueError('Public evidence must be a brief paraphrase (at most 40 words)')
        for key in ['identity', 'type', 'date']:
            if not decision.get('hard_checks', {}).get(key):
                raise ValueError('Record identity, type and date checks separately')
        short_review = next((e['data'] for e in reversed(self.log.events)
                             if e['kind'] == 'short_comment_reviewed' and e['data']['doi'] == doi), None)
        if m or category == 'review' or decision.get('exclusion_basis') == 'publisher_non_target_type':
            short_review = None
        if short_review:
            validate_short_comment_review(short_review, r, decision)
        if not m and not (short_review or category == 'review' or
                         (category == 'excluded' and decision.get('exclusion_basis') == 'publisher_non_target_type')):
            raise ValueError('Topic exclusion/inclusion requires an explicit abstract')
        if m and m.get('abstract_basis') == 'arxiv.Abstract/user_authorized_single_record' and category not in {'excluded', 'review'}:
            raise ValueError('Single author-abstract exception does not authorize inclusion or publication checks')
        if category in {'core', 'transferable_application'}:
            if not decision.get('screening_summary'):
                raise ValueError('Included papers require a screening summary')
            if any(decision['hard_checks'][k]['status'] != 'verified' for k in ['identity', 'type', 'date']):
                raise ValueError('Inclusion requires resolved hard checks')
        allowed = {'doi', 'category', 'reason', 'evidence_summary', 'reviewer', 'hard_checks',
                   'exclusion_basis', 'screening_summary', 'sources', 'needs'}
        if set(decision)-allowed:
            raise ValueError('Unexpected public decision fields')
        if m and m['abstract'] in json.dumps(decision, ensure_ascii=False):
            raise ValueError('Complete abstract cannot enter public log')
        checks = decision['hard_checks']
        effective_date = checks['date'].get('value')
        if effective_date:
            date.fromisoformat(effective_date)
        if category in {'core', 'transferable_application'} and (
                not effective_date or not self.pool['window_start'] <= effective_date <= self.pool['window_end']
                or effective_date > self.pool['as_of_date']):
            raise ValueError('Included paper needs a complete, nonfuture date within the fixed window')
        input_hash = digest({'record': r, 'material_sha256': digest(m) if m else None,
                             'hard_checks': checks, 'rule_sha256': self.rule_sha})
        self.log.add('assessment', {**decision, 'assessed_at': now(), 'workflow_version': VERSION,
                     'rule_sha256': self.rule_sha, 'candidate_sha256': self.input_sha,
                     'record_sha256': digest(r), 'input_sha256': input_hash,
                     'material_sha256': digest(m) if m else None,
                     'abstract_sha256': m['abstract_sha256'] if m else None,
                     'material_source': m['source_url'] if m else None,
                     'review_basis': ('official short comment read online under user-authorized no-abstract exception; brief observation retained, no full text stored; assistant screening'
                                      if short_review and not m else 'title, explicit abstract and bibliographic evidence; assistant screening, not full-text expert review'
                                      if m and m.get('abstract_basis') != 'arxiv.Abstract/user_authorized_single_record' else 'user-authorized single-record author abstract; matched title/all authors, accepted-version equivalence unverified; scope exclusion only'
                                      if m else 'title and bibliographic/type evidence only; no abstract reviewed')})
        return self.status()

    def status(self):
        results = self.assessments()
        return {'active_doi': self.active(), 'assessed': len(results),
                'not_assessed': sum(r['window_membership'] == 'in_window' for r in self.records.values())-len(results),
                'deferred_unassessed': len({e['data']['doi'] for e in self.log.events if e['kind'] == 'material_deferred'} - {d['doi'] for d in results}),
                'categories': dict(Counter(r['category'] for r in results)), 'log_sha256': self.log.head}

    def assessments(self):
        latest = {}
        for e in self.log.events:
            if e['kind'] in {'assessment', 'assessment_corrected'}:
                latest[e['data']['doi']] = e['data']
        return list(latest.values())

    def correct_check(self, doi, field, check, reason):
        """Append a metadata correction without rewriting the original assessment."""
        old = next((d for d in self.assessments() if d['doi'] == doi), None)
        if self.active() or not old or old['category'] not in {'excluded', 'review'}:
            raise ValueError('Finish active paper; included papers need a new semantic review')
        if field not in {'identity', 'type', 'date'} or not check.get('status') or not reason:
            raise ValueError('Explicit check and correction reason required')
        r = self.records[doi]
        checks = {**old['hard_checks'], field: check}
        new = {**old, 'hard_checks': checks, 'assessed_at': now(),
               'correction_reason': reason, 'previous_input_sha256': old['input_sha256'],
               'input_sha256': digest({'record': r, 'material_sha256': old['material_sha256'],
                                      'hard_checks': checks, 'rule_sha256': self.rule_sha})}
        if len(json.dumps(check, ensure_ascii=False)) > 3000:
            raise ValueError('Keep metadata correction concise; no source materials')
        self.log.add('assessment_corrected', new)

    def export(self):
        results = self.assessments()
        for d in results:
            r = self.records[d['doi']]
            d = {**d, 'title': r['title'], 'journal': r['journal'],
                 'date': d['hard_checks']['date'].get('value'), 'inventory_date': r['date']}
            print(json.dumps(d, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT/'reports/2026-09')
    sub = ap.add_subparsers(dest='command', required=True)
    for cmd in ['init', 'next', 'status', 'export', 'fetch-active', 'adopt-rules']:
        sub.add_parser(cmd)
    p = sub.add_parser('batch')
    p.add_argument('--size', type=int, default=10)
    p.add_argument('--doi', action='append')
    p = sub.add_parser('collect-batch')
    p.add_argument('--workers', type=int, default=4)
    p = sub.add_parser('review-pack')
    p.add_argument('--limit', type=int, default=30)
    p = sub.add_parser('decide-pack')
    p.add_argument('path', type=Path)
    p = sub.add_parser('fetch')
    p.add_argument('channel', choices=['cache', 'crossref', 'publisher', 'openalex'])
    p = sub.add_parser('import-material')
    p.add_argument('path', type=Path)
    p = sub.add_parser('decide')
    p.add_argument('path', type=Path, help='Reviewer-written JSON; no abstracts')
    args = ap.parse_args()
    w = Workflow(args.out, allow_rule_change=args.command == 'adopt-rules')
    if args.command == 'init':
        w.init()
        result = w.status()
    elif args.command == 'next':
        result = w.next()
    elif args.command == 'adopt-rules':
        result = w.adopt_rules()
    elif args.command == 'batch':
        result = w.batch(args.size, args.doi)
    elif args.command == 'collect-batch':
        result = w.collect_batch(args.workers)
    elif args.command == 'review-pack':
        result = w.review_pack(args.limit)
    elif args.command == 'decide-pack':
        result = w.decide_pack(json.loads(args.path.read_text(encoding='utf-8')))
    elif args.command == 'fetch':
        result = w.fetch(args.channel)
    elif args.command == 'fetch-active':
        result = w.fetch_active()
    elif args.command == 'decide':
        result = w.decide(json.loads(args.path.read_text(encoding='utf-8')))
    elif args.command == 'import-material':
        result = w.import_material(args.path)
    elif args.command == 'export':
        w.export()
        return
    else:
        result = w.status()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
