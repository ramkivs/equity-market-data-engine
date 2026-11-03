"""Q6/Q8/Q9 for a pinned composite generation.

Historical evidence remains baseline-scoped. Incremental archives contribute
only facts established by the committed candidate and its retained evidence.
"""
import datetime
import json

from .archive import parse_input_manifest, query_archive_inventory
from .quality import query_data_quality
from .query import (CALENDAR_FILE, CALENDAR_QUERY_ID, CALENDAR_WEEKDAY_NAMES, QueryError,
                    _cross_check_calendar, _load_calendar_metrics, _validate_calendar_day,
                    _validate_iso_date, parse_calendar)


def _candidates(baseline):
    candidates = baseline.payload.get('candidates')
    if not isinstance(candidates, list):
        raise QueryError('composite-unavailable', 'generation candidate manifest is invalid')
    seen = set()
    for item in candidates:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k] for k in ('root','date','digest','file_name','member_name','family')):
            raise QueryError('composite-unavailable', 'invalid published candidate')
        if item['digest'] in seen or item['root'] not in ('LEGACY', 'UDIFF'):
            raise QueryError('composite-unavailable', 'duplicate or invalid published candidate')
        seen.add(item['digest'])
        yield item


def calendar(baseline, params):
    start, end = params.get('date_from'), params.get('date_to')
    if (start is None) != (end is None):
        raise QueryError('query-input', 'calendar range requires both date bounds')
    if start is not None:
        _validate_iso_date('date_from', start); _validate_iso_date('date_to', end)
    original = parse_calendar(baseline.original)
    if original is not None:
        _cross_check_calendar(original, _load_calendar_metrics(baseline.original))
        days = {doc['trade_date']: (line, dict(doc), None) for line, doc in original}
        calendar_scope = 'qualified-baseline-calendar-plus-incremental'
    else:
        # If W2 calendar is legitimately absent, reconstruct only the file-
        # presence facts from the qualified input manifest. No holiday labels
        # or UDiFF date-equality facts can be inferred from that manifest.
        manifest = parse_input_manifest(baseline.original)
        if len(manifest) != baseline.original.run_record.get('corpus', {}).get('archive_count') or not manifest:
            raise QueryError('calendar-scan', 'baseline input manifest count mismatch or empty')
        days = {}
        for item in manifest:
            day = _validate_iso_date('baseline archive date', item['date_from_filename'])
            date = datetime.date.fromisoformat(day)
            if date.weekday() >= 5:
                raise QueryError('calendar-scan', 'baseline input date is a weekend')
            if day not in days:
                doc = {'trade_date': day, 'weekday': CALENDAR_WEEKDAY_NAMES[date.weekday()],
                       'file_present': True, 'missing_weekday': False, 'formats_present': [], 'member_names': [],
                       'label_status': 'not-applicable', 'official_holiday_label': None,
                       'label_circular': None, 'label_registry_id': None,
                       'notes': ['Baseline W2 calendar absent; presence derived from original input manifest, holiday labels unavailable.'],
                       'trad_dt_eq_biz_dt': None}
                days[day] = (None, doc, None)
            doc = days[day][1]
            doc['formats_present'] = sorted(set(doc['formats_present']) | {item['root']})
            doc['member_names'] = sorted(set(doc['member_names']) | {item['file_name']})
        calendar_scope = 'baseline-calendar-absent; manifest-presence-plus-incremental'
    baseline_statuses = {date: {'file_present': doc['file_present'], 'label_status': doc['label_status']}
                         for date, (_, doc, _) in days.items()}
    for item in _candidates(baseline):
        _validate_iso_date('incremental date', item['date'])
        date = datetime.date.fromisoformat(item['date'])
        if date.weekday() >= 5:
            raise QueryError('calendar-scan', 'incremental input date is a weekend')
        prior = days.get(item['date'])
        if prior is None:
            doc = {'trade_date': item['date'], 'weekday': CALENDAR_WEEKDAY_NAMES[date.weekday()],
                   'file_present': False, 'missing_weekday': True, 'formats_present': [], 'member_names': [],
                   'label_status': 'not-retrieved', 'official_holiday_label': None,
                   'label_circular': None, 'label_registry_id': None, 'notes': [], 'trad_dt_eq_biz_dt': None}
            line, original_status = None, None
        else:
            line, doc, _ = prior
            doc = dict(doc)
            original_status = baseline_statuses.get(item['date'])
        previous_udiff = 'UDIFF' in doc['formats_present']
        previous_equal = doc['trad_dt_eq_biz_dt']
        doc['file_present'], doc['missing_weekday'] = True, False
        doc['formats_present'] = sorted(set(doc['formats_present']) | {item['root']})
        doc['member_names'] = sorted(set(doc['member_names']) | {item['file_name']})
        if prior is None:
            doc['label_status'] = 'not-applicable'
        else:
            doc['notes'] = list(doc['notes']) + ['Baseline calendar label and notes are retained as historical evidence; incremental input is now present.']
        if item['family'] == 'udiff34':
            source = 'incremental/' + item['digest'] + '.rows.jsonl'
            text = baseline.payload.get('delta', {}).get(source)
            if not isinstance(text, str):
                raise QueryError('calendar-scan', 'published incremental rows unavailable')
            try:
                rows = [json.loads(line) for line in text.splitlines() if line.strip()]
                values = [row.get('observations', {}).get('bizdt_traddt_comparison') for row in rows]
            except (ValueError, AttributeError, TypeError) as exc:
                raise QueryError('calendar-scan', 'invalid incremental calendar evidence') from exc
            doc['trad_dt_eq_biz_dt'] = True if rows and all(v == 'verbatim_text_equality' for v in values) and (not previous_udiff or previous_equal is True) else None
        _validate_calendar_day(doc, 'selected calendar')
        days[item['date']] = (line, doc, original_status)
    # Extend the original weekday span; unknown days are never labelled as holidays.
    if not days:
        raise QueryError('calendar-scan', 'baseline calendar and incremental input dates are empty')
    first, last = datetime.date.fromisoformat(min(days)), datetime.date.fromisoformat(max(days))
    if (last - first).days > 36600:
        raise QueryError('calendar-scan', 'composite calendar span exceeds safe local limit')
    cursor = first
    while cursor <= last:
        text = cursor.isoformat()
        if cursor.weekday() < 5 and text not in days:
            doc = {'trade_date': text, 'weekday': CALENDAR_WEEKDAY_NAMES[cursor.weekday()],
                   'file_present': False, 'missing_weekday': True, 'formats_present': [], 'member_names': [],
                   'label_status': 'not-retrieved', 'official_holiday_label': None,
                   'label_circular': None, 'label_registry_id': None,
                   'notes': ['Outside the qualified baseline calendar; cause and holiday labels not retrieved.'],
                   'trad_dt_eq_biz_dt': None}
            _validate_calendar_day(doc, 'extended calendar')
            days[text] = (None, doc, None)
        cursor += datetime.timedelta(days=1)
    records = []
    for date, (line, doc, original_status) in sorted(days.items()):
        if start is not None and not start <= date <= end:
            continue
        served = dict(doc)
        served['serving'] = {'query': CALENDAR_QUERY_ID, 'date_from': start, 'date_to': end,
                             'source_file': CALENDAR_FILE if line is not None else 'composite/' + baseline.manifest_digest,
                             'source_line_number': line, 'baseline_calendar_status': original_status}
        records.append(served)
    return {'query': CALENDAR_QUERY_ID, 'date_from': start, 'date_to': end,
            'calendar_present': True, 'record_count': len(records), 'records': records,
            'composite_generation': baseline.manifest_digest, 'scope': calendar_scope}


def quality(baseline, index):
    result = query_data_quality(baseline.original, index)
    candidates = list(_candidates(baseline))
    quarantined = 0
    for item in candidates:
        value = item.get('quarantined')
        if type(value) is not int or value < 0:
            raise QueryError('data-quality', 'invalid incremental quarantine count')
        quarantined += value
    result['quarantine']['count'] += quarantined
    result['quarantine']['scope'] = 'baseline-plus-published-incremental'
    result['unresolved']['scope'] = 'original-baseline-only'
    result['unresolved']['incremental_availability'] = 'not-published'
    result['reconciliation']['scope'] = 'original-baseline-only'
    result['reconciliation']['incremental_availability'] = 'not-published'
    try:
        findings = [json.loads(text) for text in baseline.registry_conflicts]
        if any(not isinstance(item, dict) or item.get('status') != 'CHANGED-CONFLICT-UNRESOLVED' for item in findings):
            raise ValueError('invalid D21 conflict')
    except (ValueError, TypeError) as exc:
        raise QueryError('data-quality', 'invalid registry conflict evidence') from exc
    result['changed'] = {'present': True, 'status': 'registry-present', 'record_count': len(findings),
                         'findings': findings, 'note': 'D21 unresolved conflicts at request snapshot; changed inputs remain held.'}
    result['composite_generation'] = baseline.manifest_digest
    return result


def inventory(baseline, d01):
    result = query_archive_inventory(baseline.original, d01=d01)
    summary = result['summary']
    summary['baseline_archive_set_digest'] = summary['archive_set_digest']
    summary['archive_set_digest'] = None  # the original digest does not cover deltas
    summary['registry'] = {'present': True, 'status': 'selected-generation'}
    accepted = set(baseline.registry_accepted)
    for record in result['archives']:
        identity = (record['file_name'], record['date_from_filename'], record['archive_sha256_observed_raw_bytes'])
        if identity not in accepted:
            raise QueryError('inventory-scan', 'baseline manifest input missing from registry')
        record['registry'] = {'present': True, 'status': 'accepted-baseline'}
        record['source_scope'] = 'original-input-manifest'
    for item in _candidates(baseline):
        digest = item['digest']
        if (item['file_name'], item['date'], digest) not in accepted:
            raise QueryError('inventory-scan', 'published incremental input missing from registry')
        try:
            evidence = json.loads(baseline.payload['evidence'][digest])
            parsed = evidence['parse_report']
            if evidence['archive_sha256'] != digest or evidence['member_name'] != item['member_name']:
                raise ValueError('incremental evidence identity mismatch')
            record = {'sequence': None, 'root': item['root'], 'relative_path': item['relative_path'],
                      'file_name': item['file_name'], 'member_name': item['member_name'],
                      'date_from_filename': item['date'], 'detected_format': item['root'],
                      'engine_family': item['family'], 'partition': item['family'] + '/' + item['date'][:4],
                      'archive_sha256_d01': None, 'archive_sha256_basis': evidence['archive_sha256_basis'],
                      'archive_sha256_observed_raw_bytes': digest,
                      'member_sha256_raw_bytes': parsed['member_sha256_raw_bytes'],
                      'member_sha256_lf_text': parsed['member_sha256_lf_text'],
                      'member_size_bytes': parsed['member_size_bytes'],
                      'header_physical_width': parsed['header_physical_width'],
                      'header_tolerance_applied': parsed['header_tolerance_applied'],
                      'data_lines': parsed['data_lines'], 'rows': item['rows'], 'quarantined': item['quarantined'],
                      'd01': None, 'registry': {'present': True, 'status': 'published'},
                      'source_scope': 'incremental-registry-not-original-input-manifest'}
        except (KeyError, TypeError, ValueError) as exc:
            raise QueryError('inventory-scan', 'invalid published incremental evidence') from exc
        result['archives'].append(record)
    summary['archive_count'] = len(result['archives'])
    summary['d01_scope'] = 'original-baseline-only'
    summary['composite_generation'] = baseline.manifest_digest
    return result
