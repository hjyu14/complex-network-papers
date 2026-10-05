"""DOI-sharded private material storage; historical references stay immutable."""
import hashlib
from pathlib import Path
import re


def checked(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('Cache path escaped private directory')
    return path


def doi_directory(root, doi):
    key = hashlib.sha256(doi.encode('utf-8')).hexdigest()
    return checked(root, Path(root)/'objects'/key[:2]/key)


def relocated(root, relative):
    """Deterministic mapping, without editing historical log paths or hashes."""
    parts = Path(relative).parts
    if not parts or '..' in parts or Path(relative).is_absolute():
        raise ValueError('Invalid relative cache path')
    if parts[0] in {'objects', 'legacy-inputs'}:
        return checked(root, Path(root)/relative)
    if len(parts) == 2 and re.fullmatch('[0-9a-f]{64}', parts[0]):
        return checked(root, Path(root)/'objects'/parts[0][:2]/relative)
    return checked(root, Path(root)/'legacy-inputs'/relative)


def resolve_reference(root, path):
    original = checked(root, path)
    mapped = relocated(root, original.relative_to(Path(root).resolve()))
    if original != mapped and original.exists() and mapped.exists():
        if original.read_bytes() != mapped.read_bytes():
            raise ValueError('Conflicting legacy and sharded cache versions')
    return original if original.exists() else mapped


def material_paths(root, doi):
    key = hashlib.sha256(doi.encode('utf-8')).hexdigest()
    paths = list(doi_directory(root, doi).glob('*.json'))
    paths += list(checked(root, Path(root)/key).glob('*.json'))
    return [checked(root, p) for p in paths]
