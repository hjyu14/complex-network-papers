import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
trial = root / 'reports/v9-2026-09'
raw = json.loads((trial / 'papers.json').read_text(encoding='utf-8'))
review = json.loads((trial / 'editorial-review.json').read_text(encoding='utf-8'))
excluded = {x['doi'] for x in review['decisions'] if x['editorial_class'] == 'excluded'}
papers = []
for paper in raw['papers']:
    if paper['doi'] in excluded:
        continue
    title_words = paper['title'].replace('�', ' ').split()[:8]
    routes = ', '.join(dict.fromkeys(r['route'].replace('_', ' ') for r in paper['screening_routes']))
    paper = dict(paper)
    paper['screening_summary'] = f"The study examines {' '.join(title_words)}; {routes} evidence makes network science central to the contribution."
    papers.append(paper)
payload = dict(raw)
payload['papers'] = papers
payload['screening_counts'] = dict(raw['screening_counts'])
payload['screening_counts']['included_automated'] = len(raw['papers'])
payload['screening_counts']['excluded_editorial_boundary'] = len(excluded)
payload['screening_counts']['included_editorial'] = len(papers)
payload['editorial_review'] = 'editorial-review.json'
(trial / 'papers-editorial.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'automated_included': len(raw['papers']), 'editorial_excluded': len(excluded), 'editorial_included': len(papers)}, ensure_ascii=False))
