"""Compact incremental index overlay on the verified baseline serving index.

Historical canonical rows are never read here. A reader reconstructs the
existing index contract from the baseline index and generation-pinned delta.
"""
import copy


def empty():
    return {'files': {}, 'flag_census': {}}


def file_metadata(record, rows):
    pairs = set()
    flags = {}
    for row in rows:
        values = row['source_values']
        pairs.add((values.get('listing_symbol') or '', values.get('series') or ''))
        for flag in row.get('flags', []):
            name = flag.get('name') if isinstance(flag, dict) else None
            if not isinstance(name, str) or not name:
                raise ValueError('invalid staged flag')
            flags[name] = flags.get(name, 0) + 1
    return ({'family': record['family'], 'year': record['date'][:4], 'member_stem': record['file_name'],
             'row_count': len(rows), 'instruments': [list(p) for p in sorted(pairs)],
             'business_date_min': record['date'], 'business_date_max': record['date']}, flags)


def validate(delta, candidates):
    if not isinstance(delta, dict) or set(delta) != {'files', 'flag_census'}:
        raise ValueError('invalid incremental index overlay')
    files, flags = delta['files'], delta['flag_census']
    if not isinstance(files, dict) or not isinstance(flags, dict) or not isinstance(candidates, list):
        raise ValueError('invalid incremental index overlay components')
    expected = {}
    for record in candidates:
        if not isinstance(record, dict):
            raise ValueError('invalid incremental index candidate')
        source = 'incremental/' + record['digest'] + '.rows.jsonl'
        if source in expected:
            raise ValueError('duplicate incremental index candidate')
        expected[source] = record
    if set(files) != set(expected):
        raise ValueError('incremental index file census mismatch')
    for source, meta in files.items():
        rec = expected[source]
        if not isinstance(meta, dict) or set(meta) != {'family', 'year', 'member_stem', 'row_count', 'instruments', 'business_date_min', 'business_date_max'}:
            raise ValueError('invalid incremental index file metadata')
        if type(meta['row_count']) is not int or meta['row_count'] <= 0:
            raise ValueError('invalid incremental index row count')
        if (meta['family'], meta['year'], meta['member_stem'], meta['row_count'], meta['business_date_min'], meta['business_date_max']) != (rec['family'], rec['date'][:4], rec['file_name'], rec['rows'], rec['date'], rec['date']):
            raise ValueError('incremental index file identity mismatch')
        pairs = meta['instruments']
        if not isinstance(pairs, list) or any(not isinstance(p, list) or len(p) != 2 or any(not isinstance(x, str) for x in p) for p in pairs) or pairs != sorted(pairs) or len(pairs) != len({tuple(p) for p in pairs}):
            raise ValueError('invalid incremental index instruments')
    if any(not isinstance(k, str) or not k or type(v) is not int or v <= 0 for k, v in flags.items()):
        raise ValueError('invalid incremental index flag census')


def compose(baseline, delta, candidates):
    validate(delta, candidates)
    result = copy.deepcopy(baseline)
    for source, meta in delta['files'].items():
        if source in result['files']:
            raise ValueError('incremental index collides with baseline')
        result['files'][source] = copy.deepcopy(meta)
        key = meta['family'] + '/' + meta['year']
        part = result['partitions'].setdefault(key, {'family': meta['family'], 'year': meta['year'], 'row_files': 0, 'row_count': 0})
        part['row_files'] += 1
        part['row_count'] += meta['row_count']
    for name, count in delta['flag_census'].items():
        result['flag_census'][name] = result['flag_census'].get(name, 0) + count
    result['counts']['row_files'] = len(result['files'])
    result['counts']['row_count'] = sum(f['row_count'] for f in result['files'].values())
    result['counts']['instrument_pairs'] = len({tuple(pair) for item in result['files'].values() for pair in item['instruments']})
    return result


def extract(baseline, composite, candidates):
    if not isinstance(composite, dict):
        raise ValueError('invalid inline composite index')
    base_files, composite_files = baseline['files'], composite['files']
    if any(composite_files.get(source) != meta for source, meta in base_files.items()):
        raise ValueError('inline composite index changed baseline files')
    flags = {}
    for name in set(baseline['flag_census']) | set(composite['flag_census']):
        value = composite['flag_census'].get(name, 0) - baseline['flag_census'].get(name, 0)
        if type(value) is not int or value < 0:
            raise ValueError('inline composite index changed baseline flag census')
        if value:
            flags[name] = value
    delta = {'files': {k: copy.deepcopy(v) for k, v in composite_files.items() if k not in base_files}, 'flag_census': flags}
    if compose(baseline, delta, candidates) != composite:
        raise ValueError('inline composite index disagrees with baseline and incremental overlay')
    return delta
