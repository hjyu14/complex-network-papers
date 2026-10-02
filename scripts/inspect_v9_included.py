import json
from collect import request_json, clean
import sys
sys.stdout.reconfigure(encoding='utf-8')
p = json.load(open('reports/v9-2026-09/papers.json', encoding='utf-8'))
for i, x in enumerate(p['papers'], 1):
    try:
        abstract = clean(request_json('https://api.crossref.org/works/' + x['doi']).get('abstract', ''))
    except Exception as exc:
        abstract = 'FETCHERR ' + type(exc).__name__
    print(f'---{i} {x["doi"]}\n{x["title"]}\n{abstract[:700]}')
