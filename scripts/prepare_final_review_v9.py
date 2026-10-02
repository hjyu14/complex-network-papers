"""Freeze a review queue without treating material availability as scope review.

No network calls, no full abstracts, and no production writes. Existing outputs
are never overwritten. The queue retains historical decisions as provenance.
"""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'reports/v9-2026-09'


def main():
    source = TRIAL / 'material-master-v4.json'
    out = TRIAL / 'final-review-preparation-v1.json'
    if out.exists():
        raise FileExistsError(out)
    original = source.read_bytes()
    rows = json.loads(original)['results']
    results = []
    for row in rows:
        material = row.get('current_material') or row['material']
        hard = row.get('current_hard_check_decision') or {}
        state = row['material_state']
        initial = row['initial_screening_record']
        relation = row['window_relation_on_recorded_date']
        decision, reason = 'review', 'semantic_review_pending'
        if hard.get('decision') == 'excluded':
            decision, reason = 'excluded', hard['reason']
        elif state == 'non_research_type_documented':
            decision, reason = 'excluded', 'documented_non_target_type'
        elif state == 'abstract_and_date_collected' and relation in ('before_window', 'after_window'):
            decision, reason = 'excluded', 'outside_2026_09_window'
        elif initial['reason'] == 'notice' and re.match(
            r'^(correction|erratum|corrigendum|retraction|author correction|publisher correction|editorial|addendum)\b',
            row['title'], re.I
        ):
            decision, reason = 'excluded', 'explicit_notice_title'
        elif state == 'needs_material':
            reason = 'publisher_abstract_still_missing'
        elif initial['reason'] == 'notice':
            reason = 'historical_notice_requires_evidence_review'
        results.append({
            'doi': row['doi'], 'title': row['title'],
            'journal_queries': row['retrieved_by'],
            'decision': decision, 'reason': reason,
            'subject_scope_assessed_this_run': False,
            'effective_date': material.get('preferred_date'),
            'date_source': material.get('date_source'),
            'material_state': state,
            'master_record_sha256': hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            'master_source': source.name,
            'previous_editorial_record': row.get('previous_editorial_record'),
            'previous_retained': bool(row.get('previous_retained_record')),
            'source_references': row['source_references'],
            'hard_check_evidence': hard or row.get('type_hard_check_audit') or material.get('publisher_type_evidence'),
        })
    assert len(results) == len({r['doi'] for r in results}) == 3987
    assert source.read_bytes() == original
    payload = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'window': ['2026-09-01', '2026-09-30'],
        'stage': 'hard_checks_and_semantic_review_queue',
        'final_screening_complete': False,
        'counts': dict(Counter(r['decision'] for r in results)),
        'reason_counts': dict(Counter(r['reason'] for r in results)),
        'input_sha256': hashlib.sha256(original).hexdigest(),
        'policy_sha256': hashlib.sha256((ROOT/'config/screening-policy-v9.json').read_bytes()).hexdigest(),
        'sources_config_sha256': hashlib.sha256((ROOT/'config/sources.json').read_bytes()).hexdigest(),
        'limitations': [
            'Availability flags, word counts, hashes and scope terms do not reproduce abstract meaning.',
            'No keyword-only scope exclusions or automatic reuse of the old 25 retained papers.',
            'Journal/ISSN identity and article-type eligibility must be checked before admitting each paper.',
            'A full abstract is read transiently when required; only short evidence and the decision may be saved.',
        ],
        'results': results,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: payload[k] for k in ('counts', 'reason_counts', 'final_screening_complete')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
