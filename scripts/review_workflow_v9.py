"""One active paper: route -> cache -> AI/editorial assessment -> durable decision.

No keyword classifier. `next` cannot fetch a second paper until `submit` saves
the active paper's assessment. `defer` is only for actual acquisition failure.
Full reviewer packets are printed only with `show`; never redirect them to logs.
"""
import argparse
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from private_abstract_cache import AbstractCache, ROOT, digest
from review_routes_v9 import TRIAL, load
from review_fetch_v9 import fetch


def now():
    return datetime.now(timezone.utc).isoformat()


def hashed(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True))


class Workflow:
    def __init__(self, repository=ROOT, routes=None, fetcher=fetch):
        self.root = Path(repository)
        self.directory = self.root / '.private/review-workflow/v9'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state_path = self.directory/'active.json'
        self.cache = AbstractCache(self.root)
        self.fetcher = fetcher
        self.routes = routes if routes is not None else load(self.root/'reports/v9-2026-09/historical-routes-v1.json')['records']
        self.output = self.root/'reports/v9-2026-09/closed-loop-decisions-v1'
        self.output.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def lock(self):
        path = self.directory/'workflow.lock'
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(os.getpid()).encode())
            yield
        finally:
            os.close(fd)
            path.unlink()

    def state(self):
        return load(self.state_path) if self.state_path.exists() else None

    def status(self):
        records = [load(p) for p in self.output.glob('*.json')]
        active = self.state()
        unresolved = [r['doi'] for r in records if r.get('disposition') == 'acquisition_unresolved']
        return {'queue_total': len(self.routes), 'closed_records': len(records),
                'subject_scope_assessed': sum(r.get('subject_scope_assessed', False) for r in records),
                'acquisition_unresolved': unresolved,
                'not_yet_closed': len(self.routes)-len(records),
                'active_doi': active['doi'] if active and active['status'] != 'closed' else None,
                'active_status': active['status'] if active else None,
                'all_material_resolved': not unresolved and len(records)==len(self.routes)}

    def save(self, state):
        tmp = self.state_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        tmp.replace(self.state_path)

    def decision_path(self, doi):
        return self.output/(digest(doi)+'.json')

    def policy_hashes(self):
        return {name: digest((self.root/name).read_text(encoding='utf-8')) for name in
                ('config/screening-policy-v9.json', 'config/sources.json', 'docs/screening-protocol-v9.md')}

    def packet(self, state, cached):
        return {'article': state['article'], 'source': cached,
                'policy_hashes': state['policy_hashes'],
                'boundary': 'Title, abstract and article metadata only; no full text or outside topic evidence.'}

    def next(self, doi=None):
        with self.lock():
            state = self.state()
            if state and self.decision_path(state['doi']).exists():
                state = None  # Recover a crash after decision commit but before closing state.
            if state and doi and state['doi'] != doi:
                raise ValueError('Active paper must be assessed or deferred first')
            if state and state['status'] == 'needs_browser_or_source_review' and self.cache.get(state['doi']):
                state['status'] = 'fetching'
            if state and state['status'] != 'fetching':
                return state
            if not state:
                todo = [r for r in self.routes if not self.decision_path(r['doi']).exists()]
                if doi:
                    todo = [r for r in todo if r['doi'] == doi]
                else:
                    # Reuse cached-but-unreviewed articles before making network calls.
                    todo.sort(key=lambda r: not self.cache._directory(r['doi'])[1].exists())
                if not todo:
                    return {'status': 'queue_complete' if not doi else 'already_done_or_unknown'}
                article = todo[0]
                state = dict(doi=article['doi'], article=article, status='fetching',
                             attempts=[], policy_hashes=self.policy_hashes(), started_at=now())
                self.save(state)  # Reserve before I/O; restart resumes this DOI.
            cached = self.cache.get(state['doi'])
            if not cached:
                done = {a['url'] for a in state['attempts']}
                for route in state['article']['routes']:
                    if route['url'] in done:
                        continue
                    try:
                        metadata, abstract = self.fetcher(state['doi'], dict(route, expected_title=state['article']['title']))
                        cached = self.cache.put(metadata, abstract)
                        state['attempts'].append({'url': route['url'], 'kind': route['kind'], 'status': 'cached', 'at': now()})
                    except Exception as exc:
                        state['attempts'].append({'url': route['url'], 'kind': route['kind'],
                                                  'status': 'failed', 'error_type': type(exc).__name__,
                                                  'http_status': getattr(exc, 'code', None), 'at': now()})
                        self.save(state)
                        # Stop the current turn on rate limiting; do not try to evade it.
                        if isinstance(exc, HTTPError) and exc.code == 429:
                            break
                        continue
                    self.save(state)
                    break
            if cached:
                state.update(status='awaiting_review', abstract_sha256=cached['abstract_sha256'],
                             review_input_sha256=hashed(self.packet(state, cached)))
            else:
                state.update(status='needs_browser_or_source_review')
            self.save(state)
            return state

    def retry(self):
        with self.lock():
            state = self.state()
            if not state or state['status'] != 'needs_browser_or_source_review':
                raise ValueError('Only unresolved acquisition can be retried')
            state.setdefault('previous_attempts', []).extend(state['attempts'])
            state.update(status='fetching', attempts=[])
            self.save(state)
        return self.next(state['doi'])

    def import_browser(self, metadata, abstract):
        """Accept a browser-reader packet saved privately, bound to the active DOI."""
        with self.lock():
            state = self.state()
            if not state or state['status'] != 'needs_browser_or_source_review':
                raise ValueError('No active browser handoff')
            from review_routes_v9 import publisher_url
            if metadata.get('doi') != state['doi'] or not publisher_url(metadata.get('source_url')):
                raise ValueError('Browser DOI or publisher URL mismatch')
            if metadata.get('abstract_basis') not in ('publisher.Abstract','publisher.citation_abstract'):
                raise ValueError('Browser must read an explicit abstract field')
            self.cache.put(metadata, abstract)
        return self.next(state['doi'])

    def show(self):
        state = self.state()
        if not state or state['status'] != 'awaiting_review':
            raise ValueError('No cached article awaiting review')
        cached = self.cache.get(state['doi'])
        packet = self.packet(state, cached)
        if hashed(packet) != state['review_input_sha256']:
            raise ValueError('Cached input changed; cannot apply the old assessment')
        return dict(packet, review_input_sha256=state['review_input_sha256'])

    def submit(self, assessment):
        with self.lock():
            state = self.state()
            packet = self.show()
            if self.policy_hashes() != state['policy_hashes']:
                raise ValueError('Policy changed during review')
            if assessment.get('doi') != state['doi'] or assessment.get('review_input_sha256') != state['review_input_sha256']:
                raise ValueError('Assessment DOI/input hash mismatch')
            cls = assessment.get('class')
            if cls not in ('core', 'transferable_application', 'excluded', 'review'):
                raise ValueError('Invalid class')
            for k in ('reason', 'reviewer', 'evidence'):
                if not isinstance(assessment.get(k), str) or not assessment[k].strip():
                    raise ValueError('Missing assessment field: '+k)
            if len(assessment['reason']) > 1200 or len(assessment['evidence'].split()) > 35:
                raise ValueError('Only short reasoning and evidence belong in ordinary reports')
            if assessment['evidence'].casefold() not in (packet['source']['abstract']+' '+packet['source']['title']).casefold():
                raise ValueError('Evidence must be a literal short phrase in the reviewed input')
            if cls in ('core','transferable_application'):
                checks = assessment.get('hard_checks') or {}
                if any(checks.get(k) is not True for k in ('doi_identity','whitelisted_issn','eligible_type','date_in_window','title_matches','date_conflicts_resolved')):
                    raise ValueError('Inclusion requires explicit metadata checks')
                if not isinstance(assessment.get('hard_check_evidence'), dict) or not all(
                    assessment['hard_check_evidence'].get(k) for k in checks):
                    raise ValueError('Inclusion checks require per-field source evidence references')
                summary = assessment.get('screening_summary','')
                if not 12 <= len(summary.split()) <= 30 or not summary.endswith('.') or summary.count('.') != 1:
                    raise ValueError('Inclusion requires one 12–30 word summary')
            # Whitelist fields: never propagate an abstract supplied in a review file.
            record = {k: assessment[k] for k in ('doi','class','reason','evidence','reviewer','hard_checks','hard_check_evidence','screening_summary') if k in assessment}
            record.update(review_input_sha256=state['review_input_sha256'], abstract_sha256=state['abstract_sha256'],
                          source_url=packet['source']['source_url'], retrieved_at=packet['source']['retrieved_at'],
                          policy_hashes=state['policy_hashes'], reviewed_at=now(), subject_scope_assessed=True,
                          attempts=state.get('previous_attempts',[])+state['attempts'])
            self.commit(state, record)
            return record

    def commit(self, state, record):
        destination = self.decision_path(state['doi'])
        if destination.exists():
            raise FileExistsError(destination)
        tmp = self.directory/'decision.tmp'
        with tmp.open('w', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
        tmp.rename(destination)
        state['status'] = 'closed'
        self.save(state)

    def exclude_publisher_type(self, evidence):
        """Close a verified ineligible type without inventing an abstract."""
        from review_routes_v9 import publisher_url
        from urllib.parse import urlsplit
        with self.lock():
            state = self.state()
            if not state or state['status'] not in ('needs_browser_or_source_review', 'awaiting_review'):
                raise ValueError('No active paper for type verification')
            if self.policy_hashes() != state['policy_hashes']:
                raise ValueError('Policy changed during review')
            if evidence.get('doi') != state['doi'] or evidence.get('doi_match') is not True:
                raise ValueError('Publisher DOI verification required')
            if str(evidence.get('title', '')).casefold() != state['article']['title'].casefold():
                raise ValueError('Publisher title mismatch')
            url = publisher_url(evidence.get('source_url'))
            if not url or url != evidence.get('source_url'):
                raise ValueError('Require a clean publisher page URL')
            label = evidence.get('publisher_type', '')
            # Only directly observed Nature labels; never infer type from a DOI prefix.
            if label not in ('RESEARCH BRIEFINGS', 'CLINICAL BRIEFINGS', 'POLICY BRIEF'):
                raise ValueError('Unsupported ineligible publisher type')
            if urlsplit(url).hostname not in ('nature.com', 'www.nature.com'):
                raise ValueError('Briefing labels require a Nature publisher page')
            for key in ('retrieved_at', 'reviewer', 'reason'):
                if not isinstance(evidence.get(key), str) or not evidence[key].strip():
                    raise ValueError('Missing type evidence field: '+key)
            if len(evidence['reason']) > 1200:
                raise ValueError('Require short type exclusion reasoning')
            verified = {k: evidence[k] for k in ('doi', 'doi_match', 'title', 'source_url',
                                                'publisher_type', 'retrieved_at')}
            record = dict(doi=state['doi'], **{'class': 'excluded'},
                          reason=evidence['reason'], evidence=label, reviewer=evidence['reviewer'],
                          publisher_type_evidence=verified, review_input_sha256=hashed(verified),
                          source_url=url, retrieved_at=evidence['retrieved_at'],
                          policy_hashes=state['policy_hashes'], reviewed_at=now(),
                          subject_scope_assessed=False, disposition='publisher_type_excluded',
                          attempts=state.get('previous_attempts', [])+state['attempts'])
            self.commit(state, record)
            return record

    def defer(self, reason):
        with self.lock():
            state = self.state()
            if not state or state['status'] != 'needs_browser_or_source_review' or self.cache.get(state['doi']):
                raise ValueError('Cannot defer an unread cached abstract')
            if not reason.strip() or len(reason) > 600:
                raise ValueError('Require a short specific acquisition failure reason')
            record = dict(doi=state['doi'], **{'class':'review'}, reason=reason,
                          subject_scope_assessed=False, disposition='acquisition_unresolved',
                          reviewed_at=now(), policy_hashes=state['policy_hashes'], attempts=state.get('previous_attempts',[])+state['attempts'])
            self.commit(state, record)
            return record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['next','show','submit','status','defer','import-browser','retry','exclude-type'])
    ap.add_argument('--doi')
    ap.add_argument('--assessment', type=Path)
    ap.add_argument('--reason')
    ap.add_argument('--private-packet', type=Path)
    args = ap.parse_args()
    workflow = Workflow()
    if args.command == 'next':
        result = workflow.next(args.doi)
    elif args.command == 'show':
        result = workflow.show()
    elif args.command == 'retry':
        result = workflow.retry()
    elif args.command == 'submit':
        result = workflow.submit(load(args.assessment))
    elif args.command == 'exclude-type':
        result = workflow.exclude_publisher_type(load(args.assessment))
    elif args.command == 'defer':
        result = workflow.defer(args.reason or '')
    elif args.command == 'import-browser':
        path = args.private_packet.resolve()
        if not path.is_relative_to((ROOT/'.private').resolve()):
            raise ValueError('Browser packets must stay under .private')
        packet = load(path)
        result = workflow.import_browser(packet['metadata'], packet['abstract'])
    else:
        result = workflow.status()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
