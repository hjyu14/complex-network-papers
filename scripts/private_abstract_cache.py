"""DOI-verified, immutable local abstract snapshots; never a public payload."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('doi', 'title', 'source_url', 'retrieved_at', 'abstract_basis',
          'issns', 'article_type', 'published_online', 'published_print',
          'online_date', 'publication_date')
BASES = {'crossref.abstract', 'publisher.Abstract', 'publisher.citation_abstract',
         'pubmed.Abstract', 'europepmc.abstractText', 'openalex.abstract_inverted_index'}


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class AbstractCache:
    def __init__(self, repository=ROOT):
        repository = Path(repository).resolve()
        self.root = repository / '.private/abstract-cache/v9'
        # A symlink/junction must not redirect private data into public outputs.
        if not self.root.resolve().is_relative_to(repository / '.private'):
            raise ValueError('Private cache path escapes .private')

    def _directory(self, doi):
        doi = doi.strip().lower()
        if not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
            raise ValueError('Invalid DOI')
        return doi, self.root / digest(doi)

    def put(self, metadata, abstract):
        if metadata.get('doi_match') is not True:
            raise ValueError('DOI identity must be confirmed')
        if not isinstance(abstract, str) or not abstract.strip():
            raise ValueError('Empty abstract')
        if metadata.get('abstract_basis') not in BASES:
            raise ValueError('Not an explicit abstract field')
        doi, directory = self._directory(metadata['doi'])
        record = {key: metadata[key] for key in FIELDS if key in metadata}
        for key in ('title', 'source_url', 'retrieved_at'):
            if not record.get(key):
                raise ValueError('Missing provenance: ' + key)
        url = urlsplit(record['source_url'])
        if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password:
            raise ValueError('Invalid or credential-bearing source URL')
        if re.search(r'(api[-_]?key|token|password|secret)=', url.query, re.I):
            raise ValueError('Credential-bearing source URL')
        record.update(doi=doi, abstract=abstract, abstract_sha256=digest(abstract),
                      doi_match=True, schema='private-abstract-v1')
        serialized = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)+'\n'
        path = directory / (digest(serialized)+'.json')
        directory.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('x', encoding='utf-8') as stream:
                stream.write(serialized)
        except FileExistsError:
            if path.read_text(encoding='utf-8') != serialized:
                raise ValueError('Existing cache snapshot mismatch')
        return record

    def get(self, doi):
        doi, directory = self._directory(doi)
        records = []
        for path in directory.glob('*.json'):
            raw = path.read_text(encoding='utf-8')
            record = json.loads(raw)
            if (path.stem != digest(raw) or record.get('doi') != doi or
                    record.get('doi_match') is not True or
                    record.get('abstract_basis') not in BASES or
                    not record.get('abstract') or
                    record.get('abstract_sha256') != digest(record['abstract'])):
                raise ValueError('Invalid private cache snapshot: ' + path.name)
            records.append(record)
        return max(records, key=lambda r: r['retrieved_at']) if records else None
