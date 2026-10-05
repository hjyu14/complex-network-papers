"""Collect author-only metadata for the current included DOI set; never rescreen papers."""
import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from screen_candidates import AbstractParser, digest, normalized_title, now, ROOT
from publication_view import publication_workflow, publisher_url
from report_io import run_directory

PLACEHOLDERS = {'anonymous', 'unknown', 'author', 'authors', 'et al.', 'et al'}


def names(values):
    output = []
    for value in values:
        name = ' '.join(str(value).split())
        if name and name.casefold() not in PLACEHOLDERS:
            output.append(name)
        elif output or len(values) > 1:
            raise ValueError('Mixed valid and missing/placeholder authors; full list unresolved')
    return output


class AuthorMeta(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.authors = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta' and a.get('name', '').lower() in {'citation_author', 'dc.creator', 'dc.creator.personalname'}:
            self.authors.append(a.get('content', ''))


def request(url):
    started = time.monotonic()
    with urlopen(Request(url, headers={'User-Agent': 'NetSci-Observatory/author-metadata-1', 'Accept': 'application/json,text/html'}), timeout=30) as response:
        raw = response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:
        raise ValueError('Response exceeds 4 MB')
    return raw, round(time.monotonic()-started, 3)


def reusable_rows(previous, records, selected, refresh=()):
    if not previous:
        return {}
    from publish_snapshot import author_record
    rows={}
    for doi,row in previous['records'].items():
        if doi not in records:
            raise ValueError('Author record outside the frozen inventory')
        author_record(row,records[doi])
        if doi in selected and doi not in refresh and row['status']=='available':
            rows[doi]=row
    return rows


def save_metadata(w, path, result, previous=None):
    if previous:
        changed={doi:row for doi,row in previous['records'].items() if result['records'].get(doi)!=row}
        w.log.add('author_metadata_replaced',{
            'previous_metadata_sha256':digest(previous),'metadata_sha256':digest(result),
            'previous_header':{k:v for k,v in previous.items() if k!='records'},
            'previous_changed_records':changed,
            'added_dois':sorted(set(result['records'])-set(previous['records']))})
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    rows=result['records']
    w.log.add('author_metadata_completed',{'file':path.relative_to(ROOT).as_posix(),'metadata_sha256':digest(result),'included_count':len(rows),'available_count':sum(bool(v['authors']) for v in rows.values()),'unresolved_count':sum(not v['authors'] for v in rows.values()),'scientific_assessments_changed':False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--resume',action='store_true',help='Reuse verified authors; retry only unresolved rows')
    parser.add_argument('--refresh-doi',action='append',default=[],help='Explicitly refresh one included DOI; requires --resume')
    args = parser.parse_args()
    w = publication_workflow(run_directory(args.run, ROOT, writable=True))
    selected = [d for d in w.assessments() if d['category'] in {'core','transferable_application'}]
    path = w.out/'author-metadata.json'
    if args.refresh_doi and not args.resume:
        parser.error('--refresh-doi requires --resume')
    if path.exists() and not args.resume:
        raise ValueError('Author metadata exists; use --resume to preserve verified rows')
    previous=json.loads(path.read_text(encoding='utf8')) if path.exists() else None
    if previous and (previous['candidate_sha256']!=w.input_sha or not any(
            e['kind']=='author_metadata_completed' and e['data']['metadata_sha256']==digest(previous) for e in w.log.events)):
        raise ValueError('Previous author metadata lacks inventory/audit binding')
    selected_dois={d['doi'] for d in selected}
    if not set(args.refresh_doi)<=selected_dois:
        raise ValueError('Refresh DOI outside the current inclusion set')
    rows = reusable_rows(previous,w.records,selected_dois,args.refresh_doi)
    if previous and rows==previous['records'] and set(rows)==selected_dois:
        print('All selected authors already verified; no new output or request.');return
    for d in selected:
        if d['doi'] in rows:
            continue
        r = w.records[d['doi']]
        row = {'doi':r['doi'], 'record_sha256':digest(r), 'title':r['title'], 'issns':r['issns'],
               'authors':[], 'status':'unresolved', 'attempts':[]}
        url = 'https://api.crossref.org/works/'+quote(r['doi'],safe='')
        try:
            raw, seconds = request(url)
            msg = json.loads(raw)['message']
            if msg['DOI'].lower()!=r['doi'].lower() or normalized_title(msg['title'][0])!=normalized_title(r['title']) or not set(msg.get('ISSN',[]))&set(r['issns']):
                raise ValueError('DOI/title/ISSN mismatch')
            authors = names([a.get('name') or ' '.join(filter(None,[a.get('given'),a.get('family')])) for a in msg.get('author',[])])
            row['attempts'].append({'source_url':url,'retrieved_at':now(),'channel':'crossref','outcome':'authors_found' if authors else 'missing_or_placeholder_authors','seconds':seconds})
            if authors:
                row.update(authors=authors,status='available',source_url=url,retrieved_at=row['attempts'][-1]['retrieved_at'],basis='crossref.author; DOI, normalized title and whitelist ISSN matched')
        except HTTPError as e:
            row['attempts'].append({'channel':'crossref','source_url':url,'retrieved_at':now(),'outcome':'http_error','http_status':e.code})
            if e.code==429:
                rows[r['doi']]=row
                break
        except Exception as e:
            row['attempts'].append({'channel':'crossref','source_url':url,'retrieved_at':now(),'outcome':'rejected_or_failed','error_kind':type(e).__name__,'reason':str(e)[:180]})
        time.sleep(0.25)
        if not row['authors']:
            publisher = r.get('crossref',{}).get('resource',{}).get('primary',{}).get('URL')
            if d['hard_checks']['date'].get('publication_status')=='accepted' or d['hard_checks']['date'].get('basis','').startswith('publisher.accepted'):
                publisher=publisher_url(r, d)
            if publisher:
                try:
                    raw, seconds = request(publisher)
                    html=raw.decode('utf-8')
                    identity=AbstractParser();identity.feed(html);m=identity.material(publisher)
                    if m['doi']!=r['doi'] or normalized_title(m['title'])!=normalized_title(r['title']) or not set(m['issns'])&set(r['issns']):
                        raise ValueError('Official author page identity mismatch')
                    parser=AuthorMeta();parser.feed(html);authors=names(parser.authors)
                    row['attempts'].append({'channel':'publisher','source_url':publisher,'retrieved_at':now(),'outcome':'authors_found' if authors else 'no_explicit_author_metadata','seconds':seconds})
                    if authors:
                        row.update(authors=authors,status='available',source_url=publisher,retrieved_at=row['attempts'][-1]['retrieved_at'],basis='publisher citation_author/DC.creator; official DOI/title/ISSN matched')
                except HTTPError as e:
                    row['attempts'].append({'channel':'publisher','source_url':publisher,'retrieved_at':now(),'outcome':'http_error','http_status':e.code})
                    if e.code==429:
                        rows[r['doi']]=row
                        break
                except Exception as e:
                    row['attempts'].append({'channel':'publisher','source_url':publisher,'retrieved_at':now(),'outcome':'rejected_or_failed','error_kind':type(e).__name__,'reason':str(e)[:180]})
        row['metadata_sha256']=digest({k:v for k,v in row.items() if k not in {'attempts','metadata_sha256'}})
        rows[r['doi']]=row
        print(json.dumps({'doi':r['doi'],'author_count':len(row['authors']),'status':row['status']},ensure_ascii=False),flush=True)
    for d in selected:
        if d['doi'] not in rows:
            r=w.records[d['doi']];rows[d['doi']]={'doi':d['doi'],'record_sha256':digest(r),'title':r['title'],'issns':r['issns'],'authors':[],'status':'not_started_rate_limit','attempts':[]}
    for row in rows.values():
        row['metadata_sha256']=digest({k:v for k,v in row.items() if k not in {'attempts','metadata_sha256'}})
    result={'version':'author-metadata-1','candidate_sha256':w.input_sha,'created_at':now(),'selection':'Current included DOI set only; scientific decisions and raw inventory unchanged','records':rows}
    save_metadata(w,path,result,previous)
    print(json.dumps({'collected':sum(bool(v['authors']) for v in rows.values()),'pending':sum(not v['authors'] for v in rows.values())},ensure_ascii=False))

if __name__=='__main__':
    main()
