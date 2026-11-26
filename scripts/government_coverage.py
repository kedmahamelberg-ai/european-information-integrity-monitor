"""Archive reconciliation and publisher identities; no model or network calls."""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
from government_source_identities import resolved_source_url

POLICY = 'official-archive-reconciliation-v1'
HISTORY_DAY = dt.date(2026, 10, 1)


def history_start(code, timezones):
    day = dt.date(2026, 10, 4) if code == 'US' else HISTORY_DAY
    return dt.datetime.combine(day, dt.time.min, timezones.get(code, ZoneInfo('Europe/Amsterdam'))).astimezone(dt.timezone.utc)


def discovery_window(state, code, end, timezones, requested_start=None):
    """Reconcile the whole archive daily; revisit recent dates between checks."""
    baseline = history_start(code, timezones)
    if requested_start is not None:
        if isinstance(requested_start,dt.date) and not isinstance(requested_start,dt.datetime):
            requested_start=dt.datetime.combine(requested_start,dt.time.min,
                timezones.get(code,ZoneInfo('Europe/Amsterdam'))).astimezone(dt.timezone.utc)
        return max(baseline, requested_start), requested_start <= baseline
    proof = (state.get('source_reconciliations') or {}).get(code, {})
    day = end.astimezone(ZoneInfo('Europe/Amsterdam')).date().isoformat()
    if proof.get('policy') != POLICY or proof.get('day') != day:
        return baseline, True
    cursor = (state.get('source_cursors') or {}).get(code)
    try:
        prior = dt.datetime.fromisoformat(cursor.replace('Z', '+00:00'))
        if prior.tzinfo is None:
            raise ValueError('Source cursor has no timezone')
    except (AttributeError, TypeError, ValueError):
        return baseline, True
    # Publishers can add or correct a record carrying an older publication day.
    return max(baseline, prior - dt.timedelta(days=14)), False


def normalized_url(url):
    parts = urlsplit(url)
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid'})
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                       urlencode(query), ''))


def publisher_identity(code, url):
    """Use a documented CMS ID where slugs or section paths can change."""
    url = resolved_source_url(url)
    parts = urlsplit(url)
    if code == 'KZ' and parts.hostname == 'primeminister.kz':
        match = re.search(r'-(\d{4,8})/?$', parts.path)
        if match:
            return code + ':article:' + match.group(1)
    if code == 'SM' and parts.hostname in {'www.gov.sm', 'gov.sm'}:
        values = {k.casefold(): v for k, v in parse_qsl(parts.query)}
        ident = values.get('iditem', '')
        if re.fullmatch(r'[a-fA-F0-9-]{36}', ident):
            return code + ':article:' + ident.lower()
    if code == 'LI' and parts.hostname == 'www.regierung.li':
        match = re.search(r'/medienportal-medium/16182/(\d+)/', parts.path)
        if match:
            return code + ':article:' + match.group(1)
    if code == 'CH' and parts.hostname == 'www.admin.ch':
        match = re.fullmatch(r'/(?:de|fr|it|en)/newnsb/([A-Za-z0-9_-]+)', parts.path)
        if match:
            return code + ':article:' + match.group(1)
    if code == 'MT' and parts.hostname == 'departmentofinformation.gov.mt':
        match = re.fullmatch(r'/press-release/20\d{2}/(pr\d{6})(?:en)?(?:-\d+)?/?', parts.path, re.I)
        if match:
            return code + ':release:' + match.group(1).lower()
    return code + ':url:' + normalized_url(url)


def index_records(items):
    result = {}
    priority = lambda item: (bool(item.get('human_reviewed')), bool(item.get('source_reviewed')),
                             item.get('classification_status') in {'provisional', 'human_reviewed'})
    for item in items:
        for url in [item['url'], *(item.get('source_aliases') or [])]:
            key = publisher_identity(item['country_code'], url)
            if key not in result or priority(item) > priority(result[key]):
                result[key] = item
    return result


def match_record(entry, index):
    for url in [entry['url'], *(entry.get('source_aliases') or [])]:
        item = index.get(publisher_identity(entry['country_code'], url))
        if item is not None:
            return item
    return None


def register_aliases(item, entry):
    """Keep the existing ID, citation and reviewed fields; add identity evidence."""
    aliases = set(item.get('source_aliases') or [])
    aliases.update([entry['url'], *(entry.get('source_aliases') or [])])
    aliases.discard(item['url'])
    if aliases:
        item['source_aliases'] = sorted(aliases)


def known_window_records(code, items, start, end):
    result = set()
    for item in items:
        if item.get('country_code') != code:
            continue
        try:
            published = dt.datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
        except (KeyError, TypeError, ValueError):
            continue
        if published.tzinfo and start <= published <= end:
            result.add(item['id'])
    return result


def validate_archive_window(source, entries, items, start, end, full):
    """A stale/partial archive cannot erase known coverage with a false zero."""
    if full and not entries and known_window_records(source['iso2'], items, start, end):
        raise RuntimeError('Official archive returned zero despite saved records in this window: '+source['iso2'])


def reconcile_coverage_ids(report, items):
    """Keep saved archive proofs attached to records after a verified URL merge."""
    index = index_records(items)
    for row in report.get('sources', []):
        for record in row.get('archive_records', []):
            item = index.get(publisher_identity(row['country_code'], record['url']))
            if item is not None:
                record['id'] = item['id']


def coverage_row(source, entries, index, *, full, start, end):
    unique = {}
    for item in entries:
        unique.setdefault(publisher_identity(item['country_code'], item['url']), item)
    missing = [item for item in unique.values() if match_record(item, index) is None]
    return {'country_code': source['iso2'], 'country': source['name'],
            'source_url': source['url'], 'scope_note': source.get('scope_note', ''),
            'status': 'complete' if not missing else 'missing_records',
            'policy': POLICY, 'full_reconciliation': full,
            'window_start': start.isoformat(), 'window_end': end.isoformat(),
            'archive_unique_records': len(unique),
            'retained_matching_records': len(unique)-len(missing),
            'duplicate_archive_links': len(entries)-len(unique),
            'archive_records': [{'url': item['url'], 'id': (match_record(item,index) or {}).get('id')}
                                for item in unique.values()],
            'missing_ids': [item.get('id') for item in missing],
            'missing_urls': [item['url'] for item in missing]}
