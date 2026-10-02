"""Merge round 2 paraphrases into separate trial files, preserving prior inputs."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports/v9-2026-09'


def read(name):
    return json.loads((TRIAL / name).read_text(encoding='utf-8'))


def main():
    source = 'material-after-browser-round1.json'
    evidence_name = 'browser-round2-13-evidence.json'
    previous = read(source)
    evidence = read(evidence_name)
    rows = {r['doi']: dict(r) for r in previous['results']}
    observations = {r['doi']: r for r in evidence['results']}
    assert len(observations) == len(evidence['results']) == 13
    assert all(d in rows and not rows[d]['abstract_level_material'] for d in observations)
    type_resolved = set()
    for doi, note in observations.items():
        r = rows[doi]
        r['round2_evidence_reference'] = {'file': evidence_name, 'doi': doi}
        r['metadata_sources'] = r['metadata_sources'] + [evidence_name]
        if note['material_obtained']:
            r['abstract_level_material'] = True
            r['abstract_sources'] = r['abstract_sources'] + [evidence_name]
            r['abstract_and_complete_preferred_date'] = bool(r['preferred_date'])
            r['screening_evidence'] = {k: note[k] for k in
                ('research_object', 'methods', 'contribution', 'network_evidence', 'caveat')}
            r['screening_evidence']['basis'] = 'Visible publisher abstract only; classification deferred.'
        if note.get('type_evidence_obtained'):
            type_resolved.add(doi)
            r['publisher_type_evidence'] = {'label': note['publisher_type'],
                'source_url': note['source_url'], 'note': note['note']}
            r['further_abstract_collection_required'] = False
            r['article_type_review_deferred'] = True
        if note.get('date'):
            r['round2_date_evidence'] = {'date': note['date'], 'kind': note['date_kind'],
                'source_url': note['source_url'], 'status': note['status']}
            r['round2_date_reconciliation'] = ('same_value' if r['preferred_date'] == note['date']
                else 'different_or_missing_original_date')
            if note['status'] == 'accepted':
                r['round2_status_badge'] = {'zh': '已接收', 'en': 'Accepted Paper'}
        r['classification_deferred'] = True
    missing = [r for r in rows.values() if not r['abstract_level_material']]
    actionable = [r for r in missing if r['doi'] not in type_resolved]
    date_gaps = [r for r in rows.values() if r['abstract_level_material'] and not r['preferred_date']]
    counts = dict(previous['counts'])
    counts.update({
        'round2_processed': 13,
        'round2_new_abstract_material': 5,
        'round2_non_target_type_evidence': len(type_resolved),
        'round2_access_blocked': sum(r['status'] == 'captcha_blocked' for r in observations.values()),
        'abstract_level_material': sum(r['abstract_level_material'] for r in rows.values()),
        'abstract_and_complete_crossref_preferred_date': sum(r['abstract_and_complete_preferred_date'] for r in rows.values()),
        'still_missing_abstract': len(missing),
        'still_requiring_abstract_collection': len(actionable),
        'abstract_but_missing_crossref_preferred_date': len(date_gaps),
        'missing_abstract_or_crossref_preferred_date': len(missing) + len(date_gaps),
        'remaining_material_collection_records': len(actionable) + len(date_gaps),
        'material_including_previously_retained': 25 + sum(r['abstract_level_material'] for r in rows.values()),
    })
    assert counts['abstract_level_material'] == 2683
    assert len(missing) == 1167 and len(actionable) == 1161 and len(date_gaps) == 105
    assert counts['remaining_material_collection_records'] == 1266
    outputs = {
        'material-after-browser-round2.json': {
            'version': 'v9', 'created_at': evidence['finished_at'], 'window': previous['window'],
            'counts': counts, 'classification_deferred': True,
            'input_sha256': {n: hashlib.sha256((TRIAL / n).read_bytes()).hexdigest()
                             for n in (source, evidence_name)},
            'missing_abstract_by_journal': dict(Counter(r['retrieved_by'][0] for r in actionable)),
            'notes': ['Six publisher-confirmed non-target types need no research abstract; they are not counted as collected abstracts.',
                      'Existing Crossref dates preserved; publisher date and acceptance evidence stored separately.',
                      'The prior 439-record APS status audit is retained separately; this round adds three new accepted records outside that audited cohort.',
                      '13-record timed batch is not random or representative; total completion cannot be guaranteed.'],
            'results': sorted(rows.values(), key=lambda r: r['doi'])},
        'material-pending-after-browser-round2.json': {
            'counts': counts, 'missing_abstract': sorted(actionable, key=lambda r: r['doi']),
            'missing_crossref_preferred_date_with_abstract': sorted(date_gaps, key=lambda r: r['doi']),
            'non_target_type_evidence_for_later_review': [rows[d] for d in sorted(type_resolved)],
            'round2_access_blocked': [r for r in observations.values() if r['status'] == 'captcha_blocked'],
            'round2_date_differences': [rows[d] for d, r in observations.items()
                if r.get('date') and rows[d]['round2_date_reconciliation'] != 'same_value']},
    }
    for name in outputs:
        if (TRIAL / name).exists():
            raise FileExistsError('Preserve existing report: ' + name)
    for name, data in outputs.items():
        (TRIAL / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    main()
