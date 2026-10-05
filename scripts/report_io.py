"""Read ordinary or losslessly compressed evidence, with explicit archive references."""
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def read_bytes(path):
    path = Path(path)
    packed = path.with_name(path.name + '.gz')
    if path.exists() and packed.exists():
        raise ValueError('Ambiguous plain and compressed evidence: ' + str(path))
    if path.exists():
        return path.read_bytes()
    if packed.exists():
        return gzip.decompress(packed.read_bytes())
    raise FileNotFoundError(path)


def file_sha(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def checked_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Evidence path leaves its permitted directory')
    return path


def read_reference(ref, root):
    if 'archive' in ref:
        archive = checked_path(root, ref['archive'])
        member = PurePosixPath(ref['member'])
        if member.is_absolute() or '..' in member.parts or '\\' in ref['member']:
            raise ValueError('Unsafe archive member')
        with zipfile.ZipFile(archive) as bundle:
            if len(bundle.namelist()) != len(set(bundle.namelist())):
                raise ValueError('Duplicate archive members')
            data = bundle.read(ref['member'])
    else:
        data = read_bytes(checked_path(root, ref['path']))
    if hashlib.sha256(data).hexdigest() != ref['sha256']:
        raise ValueError('Evidence reference hash mismatch')
    return data


def run_directory(path, root, *, writable=False):
    """CLI boundary: formal runs/reviews only; never mutate sealed publications."""
    root, path = Path(root).resolve(), Path(path).resolve()
    allowed = [root/'reports/runs', root/'reports/reviews']
    if not any(path.parent == base for base in allowed):
        raise ValueError('Use reports/runs/<run-id> or reports/reviews/<review-id>')
    if writable and ((path/'publication.json').exists() or any(path.glob('*-log.jsonl.gz'))):
        raise ValueError('Sealed run is read-only; start an explicit review instead')
    if writable:
        # A published amendment is frozen even if its small logs are uncompressed.
        for publication in (root/'reports/runs').glob('*/publication.json'):
            selected=json.loads(publication.read_text(encoding='utf8'))
            if any((root/stage['source']['run']).resolve()==path for stage in selected.get('revisions',[])):
                raise ValueError('Published review is read-only; start another explicit review')
    return path


def work_directory(run, root):
    run = run_directory(run, root)
    return Path(root).resolve()/'.private/work'/run.name
