"""Check formal layout, verify archives, trace a DOI, and export disposable review views."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import zipfile
from report_io import read_reference, checked_path, run_directory, work_directory
from run_inputs import digest

ROOT = Path(__file__).resolve().parents[1]
FILES = {'README.md','candidates.json','coverage.json','collection-log.jsonl','screening-log.jsonl',
         'collection-log.jsonl.gz','screening-log.jsonl.gz','author-metadata.json','publication.json',
         'publication-evidence.json','parent-manifest.json',
         'inputs/manifest.json','inputs/sources.json','inputs/screening-protocol.md'}


def layout(root):
    unexpected=[]
    for path in (root/'reports').iterdir():
        if path.name not in {'README.md','runs','reviews','archive'}:
            unexpected.append(path.relative_to(root).as_posix())
    for kind in ['runs','reviews']:
        for run in (root/'reports'/kind).iterdir():
            if not run.is_dir():
                unexpected.append(run.relative_to(root).as_posix());continue
            for path in run.rglob('*'):
                if path.is_file():
                    name=path.relative_to(run).as_posix()
                    if name not in FILES and not name.startswith('evidence/'):
                        unexpected.append(path.relative_to(root).as_posix())
    if unexpected:
        raise ValueError('Unclassified formal output; register its independent purpose or export privately: '+', '.join(unexpected))
    return {'unclassified_files':0}


def verify_archive(manifest_path, root):
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf8'))
    rows=manifest['files']
    if len(rows)!=manifest['original_files'] or len({r['original_path'] for r in rows})!=len(rows):
        raise ValueError('Migration inventory has missing or duplicate entries')
    archive=Path(manifest_path).parent/'artifacts.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['archive_sha256']:
        raise ValueError('Archive container changed')
    with zipfile.ZipFile(archive) as bundle:
        expected={r['member'] for r in rows if 'member' in r}
        if set(bundle.namelist())!=expected or len(bundle.namelist())!=len(expected):
            raise ValueError('Archive members differ from migration inventory')
    for row in rows:
        if 'archive' in row:
            data=read_reference(row,root)
        else:
            path=checked_path(root,row['path'])
            data=path.read_bytes()
            if row['compression']=='gzip':data=gzip.decompress(data)
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Migrated evidence differs: '+row['original_path'])
    return {'verified_original_files':len(rows),'archived_files':len(expected),
            'archive_bytes':archive.stat().st_size,'original_bytes':manifest['original_bytes']}


def export_view(run, root):
    from publication_view import publication_workflow
    run=run_directory(run,root)
    w=publication_workflow(run)
    target=work_directory(run,root)/'exports';target.mkdir(parents=True,exist_ok=True)
    # This is explicitly disposable derived output, not another source of judgments.
    rows=[{'doi':d['doi'],'title':w.records[d['doi']]['title'],'category':d['category'],
           'reason':d.get('reason'),'assessment_sha256':digest(d)} for d in w.assessments()]
    result={'derived_from':run.relative_to(root).as_posix(),'status':w.status(),'records':rows}
    (target/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    lines=['# 派生审核视图','', '本文件可重新生成；正式依据是审核日志。','']
    lines.extend(f"- {r['doi']} — {r['category']} — {r['title']}" for r in rows)
    (target/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    return {'derived_output':target.relative_to(root).as_posix(),'records':len(rows)}


def trace(doi, root):
    from publication_view import publication_workflow
    from publish_snapshot import selected_runs
    rows=[]
    for run in selected_runs(root/'config/release.json'):
        w=publication_workflow(run)
        events=w.evidence_events if hasattr(w,'evidence_events') else w.log.events
        for event in events:
            if event['data'].get('doi')==doi and event['kind'] in {'assessment','assessment_corrected','user_editorial_verdict'}:
                rows.append({'kind':event['kind'],'event_sha256':event['sha256'],'data':event['data']})
    unique={row['event_sha256']:row for row in rows}
    return {'doi':doi,'events':list(unique.values()),'complete_abstracts_included':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('check-layout')
    p=sub.add_parser('verify-archive');p.add_argument('--manifest',required=True,type=Path)
    p=sub.add_parser('export');p.add_argument('--run',required=True,type=Path)
    p=sub.add_parser('trace');p.add_argument('--doi',required=True)
    args=parser.parse_args()
    if args.command=='check-layout':result=layout(ROOT)
    elif args.command=='verify-archive':result=verify_archive(args.manifest,ROOT)
    elif args.command=='export':result=export_view(args.run,ROOT)
    else:result=trace(args.doi,ROOT)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
