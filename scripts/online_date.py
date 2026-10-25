"""Validate DOI-bound official first-online observations for Elsevier inclusions."""
from datetime import date, datetime
from urllib.parse import urlsplit

from collect_candidates import digest, normalized_title


def validate_online_observation(record, journal, observation):
    """Validate official first-online bibliography, including explicit citation meta.

    Citation metadata can establish inventory membership. Inclusions separately
    require the visible Available online history through validate_online_check.
    """
    target = urlsplit(observation.get('url', ''))
    stamp = datetime.fromisoformat(observation['retrieved_at'].replace('Z', '+00:00'))
    date.fromisoformat(observation['available_online'])
    if (observation.get('doi') != record['doi']
            or normalized_title(observation.get('title')) != normalized_title(record['title'])
            or observation.get('journal') != journal['name']
            or observation.get('issn') not in journal['issns']
            or observation.get('date_label') not in {'Available online', 'citation_online_date'}
            or observation.get('publication_version') not in {
                None, 'Journal Pre-proof', 'Article in Press', 'Version of Record',
                'Corrected Proof', 'Uncorrected Proof'}
            or target.scheme != 'https' or target.hostname != 'www.sciencedirect.com'
            or not target.path.startswith('/science/article/pii/'+journal['collection']['pii_prefix'])
            or target.query or target.fragment or stamp.tzinfo is None):
        raise ValueError('Official first-online bibliography identity/date/version mismatch')
    return observation


def validate_online_check(record, journal, check):
    if journal.get('collection', {}).get('date_policy') != 'publisher.available_online':
        return None
    if (check.get('status') != 'verified'
            or check.get('basis') != 'publisher.available_online'
            or check.get('publication_status') != 'published'):
        raise ValueError('Elsevier inclusion needs a verified official first Available online date')
    value = date.fromisoformat(check['value']).isoformat()
    observations = record.get('publisher_online_observations', [])
    for observation in observations:
        if digest(observation) != check.get('observation_sha256'):
            continue
        validate_online_observation(record, journal, observation)
        if (observation.get('available_online') != value
                or observation.get('date_label') != 'Available online'):
            raise ValueError('Official Available online observation identity/date/version mismatch')
        return observation
    raise ValueError('First-online hard check is not bound to an official candidate observation')
