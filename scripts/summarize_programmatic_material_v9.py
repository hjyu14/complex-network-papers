"""Merge new evidence on the fixed 1,264 DOI queue without promotion."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from structured_material_v9 import TRIAL, iso_date


def read(name):
    path = TRIAL/name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def main():
    pending_name = 'material-pending-after-elsevier-verification-corrected.json'
    pending = read(pending_name)
    source = pending['missing_abstract'] + pending['missing_preferred_date_with_abstract']
    assert len(source) == len({r['doi'] for r in source}) == 1264
    channels = ('openalex-material-batch-v1.json', 'structured-material-v1.json', 'browser-material-batch-v1.json', 'aps-date-conflict-http-v1.json')
    indexed = {name:{r['doi']:r for r in read(name).get('results', [])} for name in channels}
    nature = {r['doi']:r for r in read('springer-nature-coverage-v1.json').get('records', [])}
    if not nature:
        nature = {r['doi']:r for r in read('springer-nature-coverage-v1.json').get('results', [])}
    rows = []
    for old in source:
        row = dict(old)
        row['new_evidence'] = []
        row['publisher_date_conflict'] = False
        row['article_type'] = None
        for name in channels:
            item = indexed[name].get(old['doi'])
            if not item:
                continue
            row['new_evidence'].append({'source_file':name, **item})
            if item.get('abstract_available') and item.get('doi_match'):
                row['abstract_level_material'] = True
            if name == 'openalex-material-batch-v1.json':
                # This date has no online/print label.  Retain as diagnostic.
                continue
            if item.get('doi_match'):
                if item.get('visible_article_type'):
                    row['article_type'] = item['visible_article_type']
                    row['publisher_visible_article_type'] = item['visible_article_type']
                    row['publisher_article_type_source'] = item.get('source_url')
                    if item.get('article_type'):
                        row['publisher_metadata_article_type'] = item['article_type']
                        if item['article_type'].lower() in ('research article', 'research-article') and item['visible_article_type'].lower() not in ('research article', 'research-article'):
                            row['publisher_article_type_conflict'] = True
                elif item.get('article_type'):
                    row['article_type'] = item['article_type']
                publisher_date = iso_date(item.get('online_date'))
                accepted_date = iso_date(item.get('accepted_date'))
                if accepted_date:
                    row['publisher_accepted_date'] = accepted_date
                if publisher_date:
                    row['publisher_online_date'] = publisher_date
                if publisher_date and accepted_date and old.get('preferred_date') == accepted_date and old.get('date_source') == 'published-online':
                    row['date_conflict_explanation'] = {
                        'status': 'crossref_online_date_matches_publisher_acceptance_date',
                        'crossref_preferred_date': old['preferred_date'],
                        'publisher_accepted_date': accepted_date,
                        'publisher_online_date': publisher_date,
                        'source_file': name,
                        'window_decision_deferred': True,
                    }
                if publisher_date:
                    if row.get('date_source') == 'published-online' and row.get('preferred_date') and row['preferred_date'] != publisher_date:
                        row['publisher_date_conflict'] = True
                    row['preferred_date'] = publisher_date
                    row['date_source'] = 'publisher-online'
                elif item.get('publisher_status') == 'accepted_paper' and accepted_date:
                    row['preferred_date'] = accepted_date
                    row['date_source'] = 'publisher-accepted'
                elif not row.get('preferred_date') and iso_date(item.get('publication_date')):
                    # An unlabelled publication date does not replace an
                    # incomplete higher-priority original date.
                    row['unresolved_date_candidate'] = item['publication_date']
        n = nature.get(row['doi'], {})
        row['documented_non_research_type'] = n.get('nature_type_classification') == 'publisher_non_research_type'
        if row['documented_non_research_type']:
            row['non_research_type_evidence'] = n
        # v9 explicitly excludes editorial content. Do not extend this to
        # Letter, Commentary or other types without a separate decision.
        editorial = next((e for e in reversed(row['new_evidence'])
                          if e.get('doi_match') and
                          str(e.get('visible_article_type') or e.get('article_type') or '').strip().lower() == 'editorial'), None)
        if editorial:
            row['documented_non_research_type'] = True
            row['non_research_type_evidence'] = {
                'article_type': 'Editorial',
                'source_file': editorial['source_file'],
                'source_url': editorial.get('source_url'),
                'doi_match': True,
                'visible_article_type': editorial.get('visible_article_type'),
                'metadata_article_type': editorial.get('article_type'),
                'rule': 'docs/screening-protocol-v9.md section 2: editorial content is not eligible',
                'abstract_required_for_type_check': False,
            }
        row['abstract_and_complete_preferred_date'] = bool(row['abstract_level_material'] and row.get('preferred_date') and not row['publisher_date_conflict'])
        if row['documented_non_research_type']:
            row['collection_state'] = 'non_research_type_documented'
        elif row['publisher_date_conflict']:
            row['collection_state'] = 'date_conflict'
        elif row['abstract_and_complete_preferred_date']:
            row['collection_state'] = 'abstract_and_date_collected'
        else:
            row['collection_state'] = 'needs_material'
        # Type documentation does not constitute semantic exclusion here.
        row['classification_deferred'] = True
        rows.append(row)
    counts = dict(Counter(r['collection_state'] for r in rows))
    counts.update({'fixed_queue':len(rows), 'abstract_material':sum(r['abstract_level_material'] for r in rows), 'new_abstract_material':sum(r['abstract_level_material'] and not o['abstract_level_material'] for r,o in zip(rows,source)), 'missing_abstract':sum(not r['abstract_level_material'] for r in rows), 'missing_preferred_date':sum(not r.get('preferred_date') for r in rows)})
    payload = {'created_at':datetime.now(timezone.utc).isoformat(),'input_sha256':hashlib.sha256((TRIAL/pending_name).read_bytes()).hexdigest(), 'counts':counts, 'results':rows, 'notes':['Fixed original queue preserved; documented non-research types retained without semantic classification.', 'Initial automated-material-batch-v1 uses coarse availability and is not counted as validated evidence here.', 'Abstract/date collected does not establish expert scope review or archived abstract prose.', 'OpenAlex date candidates do not repair preferred-date gaps without publisher labels.']}
    out = TRIAL/'material-after-programmatic-v1.json'
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    todo = [r for r in rows if r['collection_state'] in ('needs_material','date_conflict')]
    (TRIAL/'browser-pending-after-programmatic-v1.json').write_text(json.dumps({'counts':counts, 'by_journal':dict(Counter(' '.join(r.get('retrieved_by', [])) for r in todo)), 'results':todo},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
