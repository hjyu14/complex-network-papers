"""Validate original editorial reading recommendations against immutable review evidence."""
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from publication_view import publication_workflow
from screen_candidates import digest


def validate_suggestions(config, papers, sources, *, as_of):
    shapes = {'daily-suggestions-1': {'version', 'entries'},
              'daily-suggestions-2': {'version', 'entries', 'revisions'}}
    if config.get('version') not in shapes or set(config) != shapes[config['version']]:
        raise ValueError('Invalid daily suggestion configuration')
    entries = config['entries']
    revisions = config.get('revisions', [])
    if not isinstance(entries, list) or not isinstance(revisions, list):
        raise ValueError('Suggestions must be a list')
    required = {'doi', 'recommended_on', 'selection', 'source_run', 'publication_sha256',
                'assessment_sha256', 'input_sha256', 'evidence_sha256', 'review_evidence_kind',
                'reviewed_at', 'question', 'reasons', 'audience', 'reading_caveat'}
    seen_dois, seen_dates = set(), set()
    fulltext_fields = {'screening_evidence_kind', 'fulltext_review', 'reading_comment'}
    active = {}
    for entry in entries:
        if entry['doi'] in seen_dois or entry['recommended_on'] in seen_dates:
            raise ValueError('Recommend each DOI once and at most one paper per date')
        seen_dois.add(entry['doi']); seen_dates.add(entry['recommended_on'])
        active[entry['doi']] = entry
    for entry in revisions:
        prior = active.get(entry['doi'])
        if (not prior or entry.get('supersedes_sha256') != digest(prior)
                or any(entry[k] != prior[k] for k in ('recommended_on', 'selection'))):
            raise ValueError('Recommendation revision must bind its exact predecessor and original date')
        revision_time = datetime.fromisoformat(entry['reviewed_at'])
        prior_time = datetime.fromisoformat(prior['reviewed_at'])
        if revision_time.tzinfo is None or prior_time.tzinfo is None:
            raise ValueError('Reading timestamp must include a time zone')
        if revision_time < prior_time:
            raise ValueError('Recommendation revision cannot predate its predecessor')
        active[entry['doi']] = entry
    latest_date = max((e['recommended_on'] for e in active.values()), default=None)

    def bilingual(value, limit):
        if (not isinstance(value, dict) or set(value) != {'en', 'zh'}
                or any(not isinstance(t, str) or not t.strip() for t in value.values())
                or len(value['en'].split()) > limit or len(value['zh']) > limit * 5):
            raise ValueError('Invalid or oversized bilingual recommendation note')

    for entry in entries + revisions:
        fulltext = entry['review_evidence_kind'] == 'fulltext'
        fields = required | (fulltext_fields if fulltext else set())
        if any(entry is revision for revision in revisions):
            fields |= {'supersedes_sha256'}
        if set(entry) != fields:
            raise ValueError('Unexpected suggestion fields; only editorial notes may be exported')
        day = date.fromisoformat(entry['recommended_on']).isoformat()
        if day != entry['recommended_on'] or day > as_of:
            raise ValueError('Future or invalid recommendation date')
        doi = entry['doi']
        if entry['selection'] not in {'new_in_update', 'from_archive'}:
            raise ValueError('Invalid recommendation selection')
        source = sources.get((entry['source_run'], entry['assessment_sha256']))
        if (not source or source['publication_sha256'] != entry['publication_sha256']
                or source['decision']['doi'] != doi
                or source['decision']['category'] not in {'core', 'transferable_application'}
                or source['decision']['input_sha256'] != entry['input_sha256']
                or source['decision']['material_sha256'] != entry['evidence_sha256']):
            raise ValueError('Recommendation lacks matching published assessment/evidence')
        # Screening retains its original abstract binding; full-text reading is separate.
        screening_kind = entry['screening_evidence_kind'] if fulltext else entry['review_evidence_kind']
        if screening_kind not in {'abstract', 'abstract_excerpt'} or not entry['evidence_sha256']:
            raise ValueError('Recommendation requires a bound explicit abstract')
        reviewed = datetime.fromisoformat(entry['reviewed_at'])
        if reviewed.tzinfo is None or reviewed.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() > day:
            raise ValueError('Reading timestamp must precede publication of the recommendation')
        current = entry is active[doi] and day == latest_date
        if current and doi not in papers:
            raise ValueError('The current suggestion must be in the reviewed public paper list')
        if current and (any(papers[doi].get(key) != entry[key] for key in
                            ('assessment_sha256', 'input_sha256'))
                        or papers[doi].get('review_evidence_kind') != screening_kind):
            raise ValueError('Current recommendation requires rereading after assessment changes')
        if current and papers[doi].get('review_evidence_sha256') != entry['evidence_sha256']:
            raise ValueError('Current recommendation evidence has changed')
        if fulltext:
            evidence = entry['fulltext_review']
            evidence_fields = {'doi', 'title', 'sha256', 'version', 'source_url', 'source_kind',
                               'pages', 'read_scope', 'reviewed_at'}
            if (not isinstance(evidence, dict) or set(evidence) != evidence_fields
                    or evidence['doi'] != doi or evidence['reviewed_at'] != entry['reviewed_at']
                    or not isinstance(evidence['sha256'], str)
                    or not re.fullmatch(r'[0-9a-f]{64}', evidence['sha256'])
                    or evidence['source_kind'] not in {'user_provided_pdf', 'publisher_fulltext'}
                    or type(evidence['pages']) is not int or not 1 <= evidence['pages'] <= 10000
                    or any(not isinstance(evidence[k], str) or not evidence[k].strip()
                           or len(evidence[k]) > 600 for k in ('title', 'version', 'read_scope'))):
                raise ValueError('Full-text recommendation requires its own DOI/version/reading binding')
            url = urlsplit(evidence['source_url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('Full-text source must be a public HTTPS URL')
            if current and evidence['title'] != papers[doi].get('title'):
                raise ValueError('Full-text title does not match the published paper')
            comment = entry['reading_comment']
            if (not isinstance(comment, dict) or set(comment) != {'en', 'zh'}
                    or any(not isinstance(p, list) or not 1 <= len(p) <= 3
                           or any(not isinstance(t, str) or not t.strip() for t in p)
                           for p in comment.values())):
                raise ValueError('Supply one to three original bilingual commentary paragraphs')
            bilingual({lang: ' '.join(p) for lang, p in comment.items()}, 120)
        bilingual(entry['question'], 45)
        bilingual(entry['audience'], 45)
        bilingual(entry['reading_caveat'], 90)
        if not isinstance(entry['reasons'], list) or not 2 <= len(entry['reasons']) <= 4:
            raise ValueError('Supply two to four actual reading reasons')
        for reason in entry['reasons']:
            if not isinstance(reason, dict) or set(reason) != {'heading', 'text'}:
                raise ValueError('Invalid reading reason')
            bilingual(reason['heading'], 15); bilingual(reason['text'], 80)
    return sorted(active.values(), key=lambda e: e['recommended_on'], reverse=True)


def attach_suggestions(artifacts, config_path, root, *, as_of):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    sources, loaded = {}, {}
    for entry in config['entries'] + config.get('revisions', []):
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
    if config.get('revisions'):
        snapshot['daily_suggestions_history'] = config['entries'] + config['revisions']
    snapshot['daily_suggestions_sha256'] = digest(config)
    artifacts['screening-report.json']['daily_suggestions_sha256'] = digest(config)
    return artifacts
