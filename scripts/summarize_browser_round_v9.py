"""Merge paraphrased browser evidence into a new material snapshot; preserve v2."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports/v9-2026-09'


def read(name):
    return json.loads((TRIAL / name).read_text(encoding='utf-8'))


def write_new(name, data):
    path = TRIAL / name
    if path.exists():
        raise FileExistsError('Preserve existing report: ' + str(path))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    baseline_path = TRIAL / 'material-enriched-v2.json'
    baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    baseline = read(baseline_path.name)
    evidence = read('browser-round1-50-evidence.json')
    queue = read('browser-round1-50-queue.json')
    rows = {r['doi']: r for r in baseline['results']}
    observed = {r['doi']: r for r in evidence['results']}
    assert evidence['complete'] and len(observed) == 50
    assert set(observed) == {r['doi'] for r in queue['records']}
    assert all(not rows[d]['abstract_level_material'] for d in observed)
    for doi, r in observed.items():
        assert r['doi_confirmed_on_page'] and r['issns'] and r['abstract_read_in_browser']
        assert r['classification_deferred']
        out = rows[doi]
        out['abstract_level_material'] = True
        out['abstract_sources'].append('browser-round1-50-evidence.json')
        out['metadata_sources'].append('browser-round1-50-evidence.json')
        out['browser_evidence_reference'] = {'file': 'browser-round1-50-evidence.json', 'n': r['n']}
        out['publisher_publication_evidence'] = r['publication_evidence']
        # Keep Crossref completeness distinct from publisher verification.
        out['abstract_and_complete_preferred_date'] = bool(out['preferred_date'])
    ready = [r for r in rows.values() if r['abstract_level_material']]
    missing = [r for r in rows.values() if not r['abstract_level_material']]
    complete = [r for r in ready if r['abstract_and_complete_preferred_date']]
    missing_dates = [r for r in ready if not r['abstract_and_complete_preferred_date']]
    counts = {
        'all_candidates': baseline['counts']['all_candidates'],
        'pending_review': len(rows),
        'previous_abstract_level_material': baseline['counts']['abstract_level_material'],
        'new_unique_browser_abstract_material': len(observed),
        'abstract_level_material': len(ready),
        'abstract_and_complete_crossref_preferred_date': len(complete),
        'abstract_but_missing_crossref_preferred_date': len(missing_dates),
        'still_missing_abstract': len(missing),
        'missing_abstract_or_crossref_preferred_date': len(rows) - len(complete),
        'browser_round1_publisher_confirmed_september_publication': evidence['counts']['published_cohort_evidence_complete'],
        'browser_round1_accepted_page_publication_unconfirmed': evidence['counts']['accepted_page_publication_unconfirmed'],
        'previous_editorially_retained': baseline['counts']['previous_editorially_retained'],
    }
    assert len(ready) + len(missing) == len(rows) == 3850
    assert len(ready) == 2628 + 50
    assert len(missing) == 1222 - 50
    payload = {
        'version': 'v9', 'created_at': datetime.now(timezone.utc).isoformat(),
        'window': baseline['window'], 'counts': counts,
        'baseline_reference': {'file': baseline_path.name, 'sha256': baseline_hash},
        'browser_evidence_reference': 'browser-round1-50-evidence.json',
        'definitions': {
            'abstract_level_material': 'Abstract-level material was read; browser subset retains paraphrased screening evidence. No final classification implied.',
            'complete_crossref_preferred_date': 'Crossref date completeness only, not independent confirmation of formal publication.',
            'browser_round1_publication_counts': 'Counts apply only to this 50-record APS round; no extrapolation to unvisited records.',
            'accepted_page': 'Acceptance established; formal publication date not established. Keep pending publication reconciliation.',
        },
        'missing_abstract_by_journal': dict(Counter(r['retrieved_by'][0] for r in missing)),
        'classification_deferred': True,
        'results': sorted(rows.values(), key=lambda r: r['doi']),
    }
    write_new('material-after-browser-round1.json', payload)
    write_new('material-pending-after-browser-round1.json', {
        'counts': counts, 'missing_abstract': sorted(missing, key=lambda r: r['doi']),
        'missing_crossref_preferred_date_with_abstract': sorted(missing_dates, key=lambda r: r['doi']),
        'browser_publication_reconciliation': [r for r in evidence['results'] if not r['publication_evidence']['publication_confirmed']],
    })
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == baseline_hash
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    main()
