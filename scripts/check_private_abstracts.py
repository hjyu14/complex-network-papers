"""Read-only pre-commit check. Does not install hooks or modify the Git index."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'abstract', 'abstract_text', 'transient_abstract', 'abstract_inverted_index'}


def has_abstract(value):
    if isinstance(value, dict):
        return any((k.lower() in FORBIDDEN and bool(v)) or has_abstract(v)
                   for k, v in value.items())
    if isinstance(value, list):
        return any(has_abstract(v) for v in value)
    return False


def violations(repository=ROOT):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repository), *args])
    paths = git('ls-files', '-z').decode('utf-8').split('\0')
    errors = []
    for path in filter(None, paths):
        lower = path.lower()
        if lower.startswith('.private/'):
            errors.append('Private cache is in Git index: ' + path)
        elif lower.startswith(('site/', 'reports/')) and lower.endswith('.json'):
            payload = json.loads(git('show', ':' + path).decode('utf-8'))
            if has_abstract(payload):
                errors.append('Abstract field in indexed public/report JSON: ' + path)
    return errors


if __name__ == '__main__':
    errors = violations()
    print('\n'.join(errors) if errors else 'PASS: no private paths or abstract fields in indexed site/report JSON.')
    raise SystemExit(bool(errors))
