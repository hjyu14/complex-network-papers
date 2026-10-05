"""Freeze per-run inputs so later config edits cannot reinterpret old decisions."""
import hashlib
import json
from datetime import date
from pathlib import Path

VERSION = 'screening-workflow-1'

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def load_inputs(out):
    folder = Path(out)/'inputs'
    meta = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if meta['version'] != 'run-inputs-1' or meta['screening_version'] != VERSION:
        raise ValueError('Unsupported run inputs version')
    for name in ['sources.json', 'screening-protocol.md']:
        if hashlib.sha256((folder/name).read_bytes()).hexdigest() != meta['files'][name]:
            raise ValueError('Frozen run input changed: '+name)
    config = json.loads((folder/'sources.json').read_text(encoding='utf-8'))
    protocol = (folder/'screening-protocol.md').read_text(encoding='utf-8')
    rule = digest({'protocol': protocol, 'config': config, 'version': VERSION})
    if rule != meta['rule_sha256']:
        raise ValueError('Frozen rule hash mismatch')
    names = [j['short'] for j in config['journals']]
    if (len(names) != len(set(names)) or names != meta['journals']
            or [meta['window_start'], meta['window_end']] != [config['initial_trial']['start'], config['initial_trial']['end']]):
        raise ValueError('Frozen journal/window mismatch')
    return config, protocol, meta

def freeze_inputs(out, root, journals=None, window=None):
    out, root = Path(out), Path(root)
    config = json.loads((root/'config/sources.json').read_text(encoding='utf-8'))
    if window is not None:
        start, end = (date.fromisoformat(value) for value in window)
        if start > end or start.year != end.year:
            raise ValueError('Requires an ordered single-year window')
        config['initial_trial'] = {**config['initial_trial'], 'start': start.isoformat(), 'end': end.isoformat()}
    names = [j['short'] for j in config['journals']]
    if len(names) != len(set(names)) or (journals is not None and (not journals or len(journals) != len(set(journals)) or not set(journals) <= set(names))):
        raise ValueError('Unknown, empty or duplicate journals')
    if journals is not None:
        config['journals'] = [j for j in config['journals'] if j['short'] in journals]
    protocol = (root/config['screening_protocol']).read_text(encoding='utf-8')
    folder = out/'inputs'
    folder.mkdir(exist_ok=False)
    (folder/'sources.json').write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    (folder/'screening-protocol.md').write_text(protocol, encoding='utf-8', newline='\n')
    meta = {'version': 'run-inputs-1', 'journals': [j['short'] for j in config['journals']],
            'window_start': config['initial_trial']['start'], 'window_end': config['initial_trial']['end'],
            'files': {name: hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['sources.json', 'screening-protocol.md']},
            'screening_version': VERSION, 'rule_sha256': digest({'protocol': protocol, 'config': config, 'version': VERSION})}
    (folder/'manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    return load_inputs(out)
