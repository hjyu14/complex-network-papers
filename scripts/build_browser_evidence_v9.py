"""Assemble human-read browser evidence without storing abstracts or full text."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT/'reports/v9-2026-09'


def read(name):
    return json.loads((TRIAL/name).read_text(encoding='utf-8'))


def run():
    queue=read('browser-round1-50-queue.json'); curated=read('browser-round1-50-curated.json')
    candidates={r['doi']:r for r in queue['records']}
    crossref={r['doi']:r for r in read('crossref-refresh-v2.json')['results']}
    codes={'Physical Review E':'pre','Physical Review Letters':'prl','Physical Review Research':'prresearch',
           'Physical Review X':'prx','Reviews of Modern Physics':'rmp'}
    records=[]
    assert len({r['doi'] for r in queue['records']}) == queue['target_count']
    assert all(not r['abstract_level_material'] for r in queue['records'])
    assert [r['n'] for r in curated['records']] == list(range(1, len(curated['records'])+1))
    for note in curated['records']:
        doi=note['doi']; original=candidates[doi]; journal=original['journal']; pub=note['published']
        accepted=note['accepted']
        for field in ('research_object', 'methods', 'contribution', 'network_evidence', 'caveat'):
            assert note[field].strip(), (doi, field)
        for date in (pub, accepted):
            if date:
                datetime.strptime(date, '%Y-%m-%d')
        if not pub and not accepted:
            raise ValueError('Observed publication/acceptance state missing: '+doi)
        row={'n':note['n'],'doi':doi,'title':original['title'],'journal':journal,
             'issns':original['whitelist_issns'],'issn_basis':'Matched visible publisher journal footer to configured whitelist; retained all displayed whitelist identifiers.',
             'source_url':'https://journals.aps.org/'+codes[journal]+('/abstract/' if pub else '/accepted/')+doi,
             'abstract_available':True,'abstract_read_in_browser':True,'doi_confirmed_on_page':True,
             'title_confirmation': 'Matching title/subject on publisher page; mathematical formatting may differ from Crossref.',
             'article_type':'journal-article','article_type_basis':'Original Crossref whitelist-journal query filtered type:journal-article; this alone does not establish publication.',
             'content_form':note['kind'],'content_form_basis':'Reading of visible title and abstract, not a publisher metadata field.',
             'publication_evidence':{'page_status':'published_article_page' if pub else 'accepted_paper_page',
                'publisher_published_date':pub,'publisher_accepted_date':accepted,
                'published_date_label':'Published' if pub else None,
                'crossref_preferred_date':crossref.get(doi,{}).get('date'),
                'crossref_date_source':crossref.get(doi,{}).get('date_source'),
                'accepted_date_is_publication_date':False,
                'publication_confirmed':bool(pub),
                'needs_publication_reconciliation':not bool(pub)},
             'screening_evidence':{'research_object':note['research_object'],'methods_or_operations':note['methods'],
                'main_contribution':note['contribution'],'network_scope_observations':note['network_evidence'],
                'uncertainty_or_boundary':note['caveat'],'basis':'Visible abstract only; no full-text evidence used.'},
             'topic_evidence_complete':True,
             'published_cohort_evidence_complete':bool(pub and '2026-09-01'<=pub<='2026-09-30'),
             'classification_deferred':True}
        records.append(row)
    assert len({r['doi'] for r in records})==len(records)
    counts={'target':queue['target_count'],'processed':len(records),'abstracts_read':len(records),
            'topic_evidence_complete':sum(r['topic_evidence_complete'] for r in records),
            'published_cohort_evidence_complete':sum(r['published_cohort_evidence_complete'] for r in records),
            'accepted_page_publication_unconfirmed':sum(not r['publication_evidence']['publication_confirmed'] for r in records),
            'not_yet_processed':queue['target_count']-len(records)}
    report={'version':'v9','created_at':datetime.now(timezone.utc).isoformat(),
            'window':['2026-09-01','2026-09-30'],'counts':counts,'selection':queue['selection'],
            'complete':len(records)==queue['target_count'],
            'notes':['Collected for subsequent unified v9 classification, not classified or promoted.',
                     'Accepted Paper date is an acceptance date, not evidence of formal publication.',
                     'No full abstract, full text, PDF or DOM snapshot stored; all descriptions are paraphrased evidence notes.'],
            'results':records}
    out=TRIAL/'browser-round1-50-evidence.json'
    temp=out.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(out)
    print(json.dumps(counts,ensure_ascii=False))


if __name__=='__main__':run()
