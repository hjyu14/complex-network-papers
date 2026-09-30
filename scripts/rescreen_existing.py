"""Re-screen a fixed DOI cohort; never discover or append new papers.

Abstracts live only in memory. --interactive allows repeated rule evaluation
against the same fetched records, without repeated downloads or abstract files.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import json
import importlib
import shutil
from pathlib import Path
from urllib.parse import quote

try:
    from . import collect as collector
except ImportError:
    import collect as collector

CONFIG, ROOT = collector.CONFIG, collector.ROOT
clean, request_json, write_json = collector.clean, collector.request_json, collector.write_json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def rescreen(baseline, items, config):
    original = {p['doi']: p for p in baseline['papers']}
    if set(items) != set(original) or len(original) != len(baseline['papers']):
        raise ValueError('Fetched DOI set must exactly equal the original cohort')
    papers, decisions = [], []
    for doi, old in original.items():
        item = items[doi]
        if item.get('DOI', '').lower() != doi:
            raise ValueError('DOI response mismatch')
        paper, reason = collector.screen(item, config, date.fromisoformat(baseline['window_end']))
        row = {'doi': doi, 'title': clean(' '.join(item.get('title', []))),
               'previous_decision': 'included',
               'decision': 'included' if paper else 'review' if reason.startswith('review_') or reason == 'missing_or_partial_date' else 'excluded',
               'reason': reason, 'abstract_available': bool(clean(item.get('abstract', ''))),
               'metadata_sha256': digest(item),
               'metadata_url': 'https://api.crossref.org/works/' + quote(doi, safe=''),
               'retrieved_by': ['fixed-cohort DOI lookup']}
        if config['version'] >= 8:
            registry = json.loads((ROOT / config['scope_policy']['review_file']).read_text(encoding='utf-8'))
            row['scope_assessment'] = registry['decisions'].get(doi)
        if paper:
            paper['retrieved_by'] = row['retrieved_by']
            paper['screening_version'] = config['version']
            papers.append(paper)
            row['screening_routes'] = paper['screening_routes']
            row['categories'] = paper['categories']
            if 'scope_class' in paper:
                row['scope_class'] = paper['scope_class']
                row['scope_review_sha256'] = paper['scope_review_sha256']
            elif 'methods' in paper:
                row['methods'] = paper['methods']
        decisions.append(row)
    papers.sort(key=lambda p: (p['date'], p['doi']), reverse=True)
    return papers, decisions


def write_result(baseline, raw_hash, items, out):
    # Interactive trials must use the current implementation, not an import
    # cached before an edit. No abstract is written to disk.
    importlib.reload(collector)
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    papers, decisions = rescreen(baseline, items, config)
    counts = dict(Counter(r['reason'] for r in decisions))
    now = datetime.now(timezone.utc).isoformat()
    provenance = {'scope': 'existing_papers_only', 'source_snapshot_sha256': raw_hash,
                  'source_screening_version': baseline['screening_version'],
                  'source_generated_at': baseline['generated_at'], 'input_count': len(items),
                  'added_dois': [], 'new_candidates_queried': False}
    if config['version'] >= 8:
        provenance['assessment_method'] = 'approved_title_and_abstract_review'
        provenance['scope_review_sha256'] = hashlib.sha256((ROOT / config['scope_policy']['review_file']).read_bytes()).hexdigest()
    coverage = [{'label': 'Existing-paper DOI lookups', 'retrieved': len(items),
                 'total_results': len(items), 'truncated': False, 'failed': False}]
    report = {'attempted_at': now, 'screening_version': config['version'],
              'config_sha256': digest(config), 'window_start': baseline['window_start'],
              'window_end': baseline['window_end'], 'collection_complete': True,
              'rescreening': provenance, 'counts': counts, 'decisions': decisions}
    payload = {'generated_at': now, 'window_start': baseline['window_start'],
               'window_end': baseline['window_end'], 'window_days': baseline['window_days'],
               'source': 'Crossref', 'screening_version': config['version'],
               'config_sha256': digest(config), 'rescreening': provenance,
               'categories': [{'id': c['id'], 'label': c['label']} for c in config['network_categories']] + [{'id': 'other', 'label': '其他'}],
               'featured_journals': config['featured_journals'], 'featured_order_year': config['featured_order_year'],
               'journals': config['journals'], 'coverage': coverage,
               'candidate_count': len(items), 'screening_counts': counts, 'papers': papers}
    write_json(out / 'screening-report.json', report)
    write_json(out / 'papers.json', payload)
    write_json(out / 'status.json', {'attempted_at': now, 'ok': True, 'errors': [],
                                   'coverage': coverage, 'rescreening': provenance})
    print(json.dumps({'included': len(papers), 'input': len(items), 'counts': counts}, ensure_ascii=False), flush=True)
    for row in decisions:
        if row['decision'] != 'included':
            print(json.dumps({'removed': row['doi'], 'title': row['title'], 'reason': row['reason']}, ensure_ascii=False), flush=True)
    return decisions


def promote_trial(source, trial, out):
    """Promote only a complete, current-rule, fixed-cohort trial."""
    raw = source.read_bytes()
    baseline = json.loads(raw)
    payload = json.loads((trial / 'papers.json').read_text(encoding='utf-8'))
    report = json.loads((trial / 'screening-report.json').read_text(encoding='utf-8'))
    status = json.loads((trial / 'status.json').read_text(encoding='utf-8'))
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    original = {p['doi'] for p in baseline['papers']}
    included = {p['doi'] for p in payload['papers']}
    decisions = report['decisions']
    valid = (status['ok'] and report['collection_complete']
             and payload['config_sha256'] == report['config_sha256'] == digest(config)
             and payload['screening_version'] == report['screening_version'] == config['version']
             and payload['rescreening']['source_snapshot_sha256'] == hashlib.sha256(raw).hexdigest()
             and payload['rescreening']['scope'] == 'existing_papers_only'
             and payload['rescreening']['added_dois'] == []
             and len(decisions) == len(original) == payload['candidate_count']
             and {r['doi'] for r in decisions} == original
             and included <= original and len(included) == len(payload['papers'])
             and included == {r['doi'] for r in decisions if r['decision'] == 'included'}
             and payload['window_start'] == baseline['window_start']
             and payload['window_end'] == baseline['window_end'])
    if not valid:
        raise ValueError('Trial is incomplete, stale or outside the fixed cohort')
    if config['version'] >= 8:
        review_hash = hashlib.sha256((ROOT / config['scope_policy']['review_file']).read_bytes()).hexdigest()
        if payload['rescreening'].get('scope_review_sha256') != review_hash:
            raise ValueError('Trial scope review is stale')
    archive = out / 'baseline-v6.json'
    if archive.exists() and archive.read_bytes() != raw:
        raise ValueError('Refusing to overwrite a different baseline')
    out.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        shutil.copyfile(source, archive)
    for name, value in [('screening-report.json', report), ('papers.json', payload), ('status.json', status)]:
        write_json(out / name, value)


def fetch_cohort(baseline, fetch=request_json):
    def retrieve(paper):
        doi = paper['doi']
        item = fetch('https://api.crossref.org/works/' + quote(doi, safe=''))
        print('Fetched ' + doi, flush=True)
        return doi, item
    with ThreadPoolExecutor(max_workers=3) as pool:
        return dict(pool.map(retrieve, baseline['papers']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'site/data/baseline-v6.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'reports/v7-existing')
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--promote-from', type=Path, help='Validate and promote a completed trial without re-fetching')
    args = parser.parse_args()
    if args.promote_from:
        promote_trial(args.source, args.promote_from, args.out)
        return
    raw = args.source.read_bytes()
    baseline = json.loads(raw)
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    if config['version'] >= 8:
        registry = json.loads((ROOT / config['scope_policy']['review_file']).read_text(encoding='utf-8'))
        if registry['source_snapshot_sha256'] != hashlib.sha256(raw).hexdigest():
            raise ValueError('Scope registry is bound to a different baseline')
    if not baseline['papers']:
        raise ValueError('Empty cohort')
    raw_hash = hashlib.sha256(raw).hexdigest()
    # No outputs are replaced unless every request succeeds.
    try:
        items = fetch_cohort(baseline)
    except Exception as exc:
        write_json(args.out / 'status.json', {
            'attempted_at': datetime.now(timezone.utc).isoformat(), 'ok': False,
            'errors': [{'error': type(exc).__name__ + ': ' + str(exc)[:300]}],
            'coverage': [], 'scope': 'existing_papers_only'})
        raise
    if args.source.read_bytes() != raw:
        raise ValueError('Baseline changed during retrieval')
    # Immutable metadata-only cohort for reproducible scoped runs.
    archive = args.out / 'baseline-v6.json'
    if archive.exists() and json.loads(archive.read_text(encoding='utf-8')) != baseline:
        raise ValueError('Refusing to overwrite a different baseline')
    if not archive.exists():
        write_json(archive, baseline)
    write_result(baseline, raw_hash, items, args.out)
    if args.interactive:
        print('Commands: screen | inspect <doi> | quit', flush=True)
        for line in __import__('sys').stdin:
            command = line.strip()
            if command == 'screen':
                write_result(baseline, raw_hash, items, args.out)
            elif command.startswith('inspect '):
                doi = command.split(' ', 1)[1]
                item = items[doi]
                cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
                paper, reason = collector.screen(item, cfg, date.fromisoformat(baseline['window_end']))
                print(json.dumps({'doi': doi, 'title': item.get('title'), 'abstract': clean(item.get('abstract', '')),
                                  'update_to': item.get('update-to'), 'reason': reason,
                                  'routes': paper['screening_routes'] if paper else []}, ensure_ascii=False), flush=True)
            elif command == 'quit':
                break
            else:
                print('Unknown command', flush=True)


if __name__ == '__main__':
    main()
