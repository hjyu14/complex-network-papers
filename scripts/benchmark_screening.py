"""Fixed-cohort real-network concurrency benchmark and frozen review manifests."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time

from screen_candidates import Workflow, ROOT, NON_TARGET_TYPES, BufferedLog, digest, now, validate_material

WORK = ROOT / '.private/work/benchmark-50'
SCHEDULE = [4, 1, 8, 2, 2, 8, 1, 4]
CHALLENGES = [
    '10.1038/s41467-026-77381-8', '10.1038/s41467-026-77838-w',
    '10.1103/jv51-thxz', '10.1126/sciadv.aef2894',
    '10.1073/pnas.2614238123', '10.1073/pnas.2537815123',
    '10.1073/pnas.2620995123', '10.1126/sciadv.aeh8819',
    '10.1038/s41467-026-77447-7', '10.1103/96lr-z7tb']


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def prepare(w):
    selected = {d for e in w.log.events if e['kind'] in {'run_started', 'batch_selected'}
                for d in e['data']['batch_dois']}
    queues = [sorted((r for r in w.records.values() if r['window_membership'] == 'in_window'
                      and r['doi'] not in selected and r['journal'] == j['short']),
                     key=lambda r: (r['date'], r['doi'])) for j in w.config['journals']]
    sample = []
    while len(sample) < 40 and any(queues):
        for q in queues:
            if q and len(sample) < 40:
                sample.append(q.pop(0)['doi'])
    if len(sample) != 40 or any(d in selected or d in sample or d not in w.records
          or w.records[d]['window_membership'] != 'in_window' for d in CHALLENGES):
        raise ValueError('Fixed 40+10 cohort cannot be selected safely')
    sample += CHALLENGES
    w.batch(50, sample)
    w.log.add('benchmark_design', {'sample_dois': sample, 'sample_sha256': digest(sample),
                  'selection': '40 remaining journal-round-robin candidates plus 10 preregistered title-based boundary examples',
                  'schedule': SCHEDULE, 'replicates_per_level': 2, 'fresh_network': True,
                  'server_cache_controlled': False, 'rule_sha256': w.rule_sha,
                  'quality_test': 'Frozen primary baseline, then 3 blinded reviewer shards with 6 overlapping boundary cases; coordinator adjudication and audit timed separately'})
    return sample


def trial(w, sample, workers, number):
    begin = now()
    start = time.monotonic()
    stop = threading.Event()
    # Each trial makes actual requests; never let an earlier trial's cache/attempt
    # event affect which channels are requested in a later trial.
    snapshot = [e for e in w.log.events if e['data'].get('doi') not in sample]
    w.log.add('benchmark_trial_started', {'trial': number, 'workers': workers,
                  'sample_sha256': digest(sample), 'fresh_network': True, 'started_at': begin})

    def collect(doi):
        job = object.__new__(Workflow)
        job.__dict__ = {**w.__dict__, 'log': BufferedLog(snapshot), 'collection_doi': doi,
                        'fresh_network': True, 'request_stop': stop}
        t = time.monotonic()
        r = w.records[doi]
        types = {a['article_type'] for a in r.get('publisher_records', []) if a.get('article_type')}
        if len(types) == 1 and types <= NON_TARGET_TYPES:
            status, material = 'type_evidence_ready', None
        else:
            try:
                job.fetch_active()
                material = job.current_material()
                status = 'abstract_ready' if material else 'deferred'
            except Exception as e:
                job.log.add('benchmark_collection_failed', {'doi': doi, 'error_type': type(e).__name__})
                status, material = 'deferred', None
        refs = [e['data'] for e in job.log.pending if e['kind'] == 'material_cached']
        return {'doi': doi, 'result': status, 'seconds': round(time.monotonic()-t, 4),
                'abstract_sha256': material['abstract_sha256'] if material else None,
                'abstract_basis': material['abstract_basis'] if material else None,
                'cache_path': refs[-1]['cache_path'] if refs else None,
                'material_sha256': digest(material) if material else None}, job.log.pending

    results = []
    remaining = iter(sample)
    submitted = set()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        active = {}
        def submit():
            if stop.is_set():
                return False
            doi = next(remaining, None)
            if doi is None:
                return False
            active[executor.submit(collect, doi)] = doi
            submitted.add(doi)
            return True
        for _ in range(workers):
            submit()
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future)
                result, events = future.result()
                for e in events:
                    w.log.add(e['kind'], {**e['data'], 'benchmark_trial': number,
                                         'benchmark_workers': workers, 'observed_at': e['at']})
                results.append(result)
                submit()
    for doi in sample:
        if doi not in submitted:
            results.append({'doi': doi, 'result': 'not_started_rate_limit', 'seconds': None,
                            'abstract_sha256': None, 'cache_path': None, 'material_sha256': None})
    order = {doi: i for i, doi in enumerate(sample)}
    results.sort(key=lambda r: order[r['doi']])
    requests = [e['data'] for e in w.log.events if e['kind'] == 'source_attempt'
                and e['data'].get('benchmark_trial') == number and e['data']['channel'] != 'cache']
    durations = sorted(r['seconds'] for r in results if r['seconds'] is not None and r['result'] != 'type_evidence_ready')
    data = {'trial': number, 'workers': workers, 'started_at': begin, 'finished_at': now(),
            'seconds': round(time.monotonic()-start, 4), 'sample_sha256': digest(sample),
            'counts': dict(Counter(r['result'] for r in results)), 'requests': len(requests),
            'http_429': sum(r.get('http_status') == 429 for r in requests),
            'http_errors': dict(Counter(str(r['http_status']) for r in requests if r.get('result') == 'http_error')),
            'per_paper_p50_seconds': durations[len(durations)//2] if durations else None,
            'per_paper_p95_seconds': durations[min(len(durations)-1, int(len(durations)*.95))] if durations else None,
            'papers': results}
    w.log.add('benchmark_trial_completed', data)
    print(json.dumps({k: v for k, v in data.items() if k != 'papers'}, ensure_ascii=False), flush=True)
    return data


def freeze(w, sample, trials, filename):
    fixed = []
    for doi in sample:
        success = next((r for t in trials for r in t['papers'] if r['doi'] == doi and r['result'] == 'abstract_ready'), None)
        r = w.records[doi]
        fixed.append({'doi': doi, 'record': r, 'record_sha256': digest(r),
                      'cache_path': success['cache_path'] if success else None,
                      'material_sha256': success['material_sha256'] if success else None,
                      'abstract_sha256': success['abstract_sha256'] if success else None,
                      'review_input_sha256': digest({'record': r, 'material_sha256': success['material_sha256'] if success else None,
                                                    'rule_sha256': w.rule_sha}),
                      'stratum': 'challenge' if doi in CHALLENGES else 'consecutive'})
    manifest = {'created_at': now(), 'rule_sha256': w.rule_sha, 'candidate_sha256': w.input_sha,
                'sample_sha256': digest(sample), 'records': fixed}
    save_new(WORK/filename, manifest)
    w.log.add('benchmark_material_frozen', {'manifest_path': (WORK/filename).relative_to(ROOT).as_posix(),
                 'manifest_sha256': digest(manifest), 'sample_sha256': digest(sample),
                 'abstracts': sum(bool(x['cache_path']) for x in fixed), 'rule_sha256': w.rule_sha})
    return manifest


def run():
    w = Workflow(ROOT/'reports/2026-09')
    if WORK.exists() and any(WORK.iterdir()):
        raise ValueError('Benchmark workspace already exists; preserve it and use recorded results')
    sample = prepare(w)
    trials = []
    for number, workers in enumerate(SCHEDULE, 1):
        t = trial(w, sample, workers, number)
        trials.append(t)
        if number == 1:
            freeze(w, sample, trials, 'initial-manifest.json')
        if t['http_429']:
            w.log.add('benchmark_stopped_rate_limit', {'after_trial': number, 'reason': '429; remaining trials not run'})
            break
    # Reviewers compare the same first-trial inputs, including its honest failures.
    # Later recovery is measured but must not change material halfway through review.
    manifest = freeze(w, sample, trials[:1], 'manifest.json')
    reference = {r['doi']: r for r in manifest['records']}
    differences = []
    for t in trials:
        for r in t['papers']:
            if r['abstract_sha256'] and r['abstract_sha256'] != reference[r['doi']]['abstract_sha256']:
                differences.append({'trial': t['trial'], 'doi': r['doi'], 'abstract_sha256': r['abstract_sha256'],
                                    'reference_sha256': reference[r['doi']]['abstract_sha256']})
    data = {'sample_sha256': digest(sample), 'trials_completed': len(trials),
            'cross_trial_abstract_hash_differences': differences,
            'trials': [{k: v for k, v in t.items() if k != 'papers'} for t in trials]}
    w.log.add('benchmark_collection_summary', data)
    save_new(WORK/'collection-summary.json', data)
    print(json.dumps(data, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    run()
