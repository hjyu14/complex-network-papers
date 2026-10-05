"""Import selected browser bibliography into the existing Nature prefix verifier.

No network, HTML, abstracts or article text. This does not declare coverage complete;
resume collect_candidates.py to check order, guards and source reconciliation.
"""
import argparse
from datetime import date, datetime
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from collect_candidates import EventLog, digest
from import_aip_directory import check_keys
from run_inputs import load_inputs


def validate(bundle, journal, start):
    check_keys(bundle,['version','journal','pages'])
    if bundle['version'] != 'nature-browser-bibliography-1' or bundle['journal'] != journal['short']:
        raise ValueError('Wrong bibliography/journal')
    if journal['collection']['family'] != 'nature' or not 0 < len(bundle['pages']) <= journal['collection']['max_pages']:
        raise ValueError('Wrong family or page budget')
    result=[]
    for number,p in enumerate(bundle['pages'],1):
        check_keys(p,['url','retrieved_at','page_title','issns','all_types','total','last_page','records'])
        u=urlsplit(p['url']); q=parse_qs(u.query)
        if (u.scheme != 'https' or u.hostname != 'www.nature.com' or u.path != urlsplit(journal['collection']['url']).path
                or q.get('year') != [start[:4]] or int(q.get('page',['1'])[0]) != number
                or set(q)-{'year','page','sort','searchType'} or q.get('sort',['PubDate']) != ['PubDate']):
            raise ValueError('Wrong or filtered directory URL/page')
        if (p['all_types'] is not True or journal['name'] not in p['page_title'] or start[:4] not in p['page_title']
                or not set(p['issns']) & set(journal['issns'])):
            raise ValueError('Journal/year/all-types identity not confirmed')
        stamp=datetime.fromisoformat(p['retrieved_at'].replace('Z','+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Timestamp needs timezone')
        if (type(p['total']) is not int or p['total'] <= 0 or p['last_page'] != (p['total']+19)//20
                or len(p['records']) != min(20,p['total']-(number-1)*20)):
            raise ValueError('Incomplete card page or pagination/count mismatch')
        for r in p['records']:
            check_keys(r,['title','article_type','date','article_url'])
            target=urlsplit(r['article_url'])
            if (not r['title'] or not r['article_type'] or target.scheme!='https' or target.hostname!='www.nature.com'
                    or not target.path.startswith('/articles/')):
                raise ValueError('Missing/wrong card identity')
            date.fromisoformat(r['date'])
        result.append({'url':p['url'],'retrieved_at':p['retrieved_at'],
                       'parsed':{'records':p['records'],'total':p['total'],'last_page':p['last_page']}})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--input',required=True,type=Path)
    args=p.parse_args()
    from report_io import run_directory
    args.out=run_directory(args.out,Path(__file__).resolve().parents[1],writable=True)
    config,_,_=load_inputs(args.out)
    bundle=json.loads(args.input.read_text(encoding='utf-8'))
    journal=next(j for j in config['journals'] if j['short']==bundle['journal'])
    pages=validate(bundle,journal,config['initial_trial']['start'])
    log=EventLog(args.out/'collection-log.jsonl')
    revision=log.latest('directory_revision',journal['short'])
    prefix=f"official:{journal['short']}:directory:{revision['revision'] if revision else 0}:"
    if any(log.latest('official_page',prefix+str(i)) for i in range(1,len(pages)+1)):
        raise ValueError('Existing page evidence; use a separately recorded revision, never overwrite')
    log.add('browser_nature_observation',{'key':journal['short'],'input_sha256':digest(bundle),
            'code_sha256':__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest(),
            'pages':len(pages),'completion_claim':False})
    for number,page in enumerate(pages,1):
        log.add('official_page',{'key':prefix+str(number),**page,'observation_basis':'browser_visible_bibliography'})
    print(json.dumps({'pages':len(pages),'cards':sum(len(p['parsed']['records']) for p in pages),'completion_claim':False}))


if __name__=='__main__': main()
