"""Reproducible DOI union of September v9 material collection reports."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT/'reports/v9-2026-09'
OLD = ('crossref-fallback.json','crossref-batch-refresh.json','europepmc-fallback.json','openalex-fallback.json')
NEW = ('crossref-refresh-v2.json','europepmc-refresh-v2.json','publisher-structured-v2.json',
       'publisher-canonical-v2.json','openaire-batch-v2.json','pubmed-batch-v2.json','semantic-batch-v2.json',
       'semantic-small-probe-v2.json')


def read(name):
    return json.loads((TRIAL/name).read_text(encoding='utf-8'))


def main():
    initial = read('screening-report.json')
    base = {r['doi'].lower():r for r in initial['decisions'] if r['decision']=='review'}
    old = {d for d,r in base.items() if r.get('abstract_available')}
    for filename in OLD:
        old |= {r['doi'].lower() for r in read(filename)['results'] if r.get('abstract_available') and r['doi'].lower() in base}
    rows = {d:{'doi':d,'title':r['title'],'retrieved_by':r['retrieved_by'],
                'original_reason':r['reason'],'abstract_sources':[], 'metadata_sources':[],
                'abstract_level_material':False,'classification_deferred':True}
            for d,r in base.items()}
    for d,r in base.items():
        if r.get('abstract_available'):
            rows[d]['abstract_sources'].append('screening-report.json')
            rows[d]['abstract_level_material']=True
    channel_counts = {}
    for filename in OLD+NEW:
        if not (TRIAL/filename).exists(): continue
        data = read(filename)
        channel_counts[filename]=data.get('counts',{})
        for r in data.get('results',[]):
            doi=(r.get('doi') or '').lower().replace('https://doi.org/','')
            if doi not in rows: continue
            out=rows[doi]
            out['metadata_sources'].append(filename)
            if r.get('abstract_available'):
                out['abstract_level_material']=True
                out['abstract_sources'].append(filename)
            if r.get('material_observations'):
                out.setdefault('observations',[]).append({'source_file':filename,**r['material_observations']})
            if r.get('bibliographic_metadata'):
                out.setdefault('publisher_metadata',[]).append({'source_file':filename,**r['bibliographic_metadata']})
    fresh_dates={r['doi']:r for r in read('crossref-refresh-v2.json')['results']}
    for doi,out in rows.items():
        out['preferred_date']=fresh_dates.get(doi,{}).get('date')
        out['date_source']=fresh_dates.get(doi,{}).get('date_source')
        out['abstract_and_complete_preferred_date']=bool(out['abstract_level_material'] and out['preferred_date'])
    ready={d for d,r in rows.items() if r['abstract_level_material']}
    complete={d for d,r in rows.items() if r['abstract_and_complete_preferred_date']}
    missing=set(rows)-ready
    counts={'all_candidates':len(initial['decisions']), 'pending_review':len(rows),
            'previous_abstract_level_material':len(old), 'previous_missing_abstract':len(rows)-len(old),
            'new_unique_abstract_material':len(ready-old),'abstract_level_material':len(ready),
            'abstract_and_complete_preferred_date':len(complete), 'abstract_but_missing_preferred_date':len(ready-complete),
            'still_missing_abstract':len(missing), 'missing_abstract_or_preferred_date':len(rows)-len(complete),
            'previous_editorially_retained':len(read('papers-editorial.json')['papers'])}
    assert len(ready)+len(missing)==len(rows)
    assert len(complete)+len(ready-complete)==len(ready)
    assert len(ready-old)+len(old)==len(ready)
    payload={'version':'v9','created_at':datetime.now(timezone.utc).isoformat(),'window':['2026-09-01','2026-09-30'],
        'counts':counts,'channels':channel_counts,
        'missing_abstract_by_journal':dict(Counter(base[d]['retrieved_by'][0] for d in missing)),
        'definitions':{'abstract_level_material':'A recorded abstract or substantive article description; not completed v9 classification.',
                       'complete_preferred_date':'Complete date recorded by refreshed Crossref using project priority; alternative API dates do not override an incomplete preferred date.',
                       'stored_content':'Metadata, source references and derived screening observations only; no complete abstract, PDF, HTML or full text.'},
        'notes':['Earlier 1858/1992 counts omitted the saved OpenAlex result; initial source audit also recovers one original abstract not present in fallback outputs.',
                 'Short publisher teasers from the exploratory first 50 are not counted unless validated in the structured v2 run.',
                 'All records still await unified v9 classification; lack of material is not an exclusion decision.'],
        'results':sorted(rows.values(),key=lambda r:r['doi'])}
    (TRIAL/'material-enriched-v2.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    queue={'counts':counts,'missing_abstract':[rows[d] for d in sorted(missing)],
           'missing_preferred_date_with_abstract':[rows[d] for d in sorted(ready-complete)]}
    (TRIAL/'material-pending-v2.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(counts,ensure_ascii=False))


if __name__=='__main__':main()
