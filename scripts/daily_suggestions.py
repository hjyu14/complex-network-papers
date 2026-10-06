"""Validate original editorial reading recommendations against immutable review evidence."""
from datetime import date
import hashlib
import json
from pathlib import Path
from publication_view import publication_workflow
from screen_candidates import digest


def validate_suggestions(config, papers, sources, *, as_of):
    if set(config) != {'version', 'entries'} or config['version'] != 'daily-suggestions-1':
        raise ValueError('Invalid daily suggestion configuration')
    entries = config['entries']
    if not isinstance(entries, list):
        raise ValueError('Suggestions must be a list')
    required = {'doi', 'recommended_on', 'selection', 'source_run', 'publication_sha256',
                'assessment_sha256', 'input_sha256', 'evidence_sha256', 'review_evidence_kind',
                'reviewed_at', 'question', 'reasons', 'audience', 'reading_caveat'}
    seen_dois, seen_dates = set(), set()
    latest_date = max((e['recommended_on'] for e in entries), default=None)

    def bilingual(value, limit):
        if (not isinstance(value, dict) or set(value) != {'en', 'zh'}
                or any(not isinstance(t, str) or not t.strip() for t in value.values())
                or len(value['en'].split()) > limit or len(value['zh']) > limit * 5):
            raise ValueError('Invalid or oversized bilingual recommendation note')

    for entry in entries:
        if set(entry) != required:
            raise ValueError('Unexpected suggestion fields; only editorial notes may be exported')
        day = date.fromisoformat(entry['recommended_on']).isoformat()
        if day != entry['recommended_on'] or day > as_of:
            raise ValueError('Future or invalid recommendation date')
        doi = entry['doi']
        if doi in seen_dois or day in seen_dates:
            raise ValueError('Recommend each DOI once and at most one paper per date')
        seen_dois.add(doi); seen_dates.add(day)
        if entry['selection'] not in {'new_in_update', 'from_archive'}:
            raise ValueError('Invalid recommendation selection')
        source = sources.get((entry['source_run'], entry['assessment_sha256']))
        if (not source or source['publication_sha256'] != entry['publication_sha256']
                or source['decision']['doi'] != doi
                or source['decision']['category'] not in {'core', 'transferable_application'}
                or source['decision']['input_sha256'] != entry['input_sha256']
                or source['decision']['material_sha256'] != entry['evidence_sha256']):
            raise ValueError('Recommendation lacks matching published assessment/evidence')
        # The first implementation uses explicit abstracts. Other materials require an
        # explicit evidence binding before they can support a detailed recommendation.
        if entry['review_evidence_kind'] not in {'abstract', 'abstract_excerpt'} or not entry['evidence_sha256']:
            raise ValueError('Recommendation requires a bound explicit abstract')
        from datetime import datetime
        reviewed = datetime.fromisoformat(entry['reviewed_at'])
        from zoneinfo import ZoneInfo
        if reviewed.tzinfo is None or reviewed.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() > day:
            raise ValueError('Reading timestamp must precede publication of the recommendation')
        if day == latest_date and doi not in papers:
            raise ValueError('The current suggestion must be in the reviewed public paper list')
        if day == latest_date and any(papers[doi].get(key) != entry[key] for key in
                                     ('assessment_sha256', 'input_sha256', 'review_evidence_kind')):
            raise ValueError('Current recommendation requires rereading after assessment changes')
        if day == latest_date and papers[doi].get('review_evidence_sha256') != entry['evidence_sha256']:
            raise ValueError('Current recommendation evidence has changed')
        bilingual(entry['question'], 45)
        bilingual(entry['audience'], 45)
        bilingual(entry['reading_caveat'], 90)
        if not isinstance(entry['reasons'], list) or not 2 <= len(entry['reasons']) <= 4:
            raise ValueError('Supply two to four actual reading reasons')
        for reason in entry['reasons']:
            if not isinstance(reason, dict) or set(reason) != {'heading', 'text'}:
                raise ValueError('Invalid reading reason')
            bilingual(reason['heading'], 15); bilingual(reason['text'], 80)
    return sorted(entries, key=lambda e: e['recommended_on'], reverse=True)


def attach_suggestions(artifacts, config_path, root, *, as_of):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    sources, loaded = {}, {}
    for entry in config['entries']:
        relative = entry['source_run']
        path = (root / relative).resolve()
        if not path.is_relative_to((root / 'reports/runs').resolve()) or path == (root / 'reports/runs').resolve():
            raise ValueError('Suggestion source must be an original publication run')
        if relative not in loaded:
            manifest_hash = hashlib.sha256((path / 'publication.json').read_bytes()).hexdigest()
            if manifest_hash != entry['publication_sha256']:
                raise ValueError('Pinned recommendation publication changed')
            w = publication_workflow(path)
            decisions = w.assessments()
            loaded[relative] = manifest_hash
            for decision in decisions:
                sources[(relative, digest(decision))] = {'decision': decision, 'publication_sha256': manifest_hash}
    snapshot = artifacts['papers.json']
    entries = validate_suggestions(config, {p['doi']: p for p in snapshot['papers']}, sources, as_of=as_of)
    snapshot['daily_suggestions'] = entries
    snapshot['daily_suggestions_sha256'] = digest(config)
    artifacts['screening-report.json']['daily_suggestions_sha256'] = digest(config)
    return artifacts
