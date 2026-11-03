"""Generation-pinned incremental ticker groups in immutable content trees."""
from contextlib import contextmanager
import os
import sqlite3
from urllib.parse import quote

from .incremental_registry import _json
from .persistent_index_map import lookup, insert, entries, validate_reference_header
from .catalog_publication import validate_ticker_delta, merge_ticker_catalogs

NAMES = ('tickers', 'identities', 'series')


def empty():
    return {name: {'root': None, 'count': 0} for name in NAMES}


def validate_headers(trees):
    if not isinstance(trees, dict) or set(trees) != set(NAMES):
        raise ValueError('invalid ticker delta tree headers')
    for header in trees.values():
        validate_reference_header(header)


def _pair(selector, series):
    if not isinstance(selector, str) or not selector or not isinstance(series, str):
        raise ValueError('invalid ticker delta group key')
    return _json([selector, series])


def _valid_group(value, kind, selector, series):
    if not isinstance(value, dict) or set(value) != {'observations'} or not isinstance(value['observations'], list) or not value['observations']:
        raise ValueError('invalid ticker delta group')
    validate_ticker_delta(value)
    rows = value['observations']
    if any(row[0 if kind == 'tickers' else 2] != selector or row[1] != series for row in rows):
        raise ValueError('ticker delta group key mismatch')
    if rows != [list(row) for row in merge_ticker_catalogs({'observations': []}, value)['observations']]:
        raise ValueError('ticker delta group ordering mismatch')
    return rows


def _valid_series(value):
    if not isinstance(value, dict) or set(value) != {'series'} or not isinstance(value['series'], list) or not value['series'] or any(not isinstance(x, str) for x in value['series']) or value['series'] != sorted(set(value['series'])):
        raise ValueError('invalid ticker delta series directory')
    return value['series']


class TickerDeltaTrees:
    def __init__(self, trees, db=None, path=None):
        validate_headers(trees)
        self.trees, self.db, self.path = trees, db, path

    @contextmanager
    def _connection(self):
        if self.db is not None:
            yield self.db
        else:
            if not self.path or os.path.islink(self.path) or not os.path.isfile(self.path):
                raise ValueError('ticker delta registry missing or unsafe')
            db = sqlite3.connect('file:' + quote(os.path.abspath(self.path), safe='/') + '?mode=ro', uri=True)
            try:
                yield db
            finally:
                db.close()

    def _group(self, db, kind, selector, series):
        value = lookup(db, self.trees[kind]['root'], _pair(selector, series))
        return [] if value is None else _valid_group(value, kind, selector, series)

    def ticker_observations(self, ticker, series):
        with self._connection() as db:
            rows = self._group(db, 'tickers', ticker, series)
            directory = lookup(db, self.trees['series']['root'], ticker)
            values = [] if directory is None else _valid_series(directory)
            if bool(rows) != (series in values):
                raise ValueError('ticker delta series directory mismatch')
            identity_groups = {}
            for row in rows:
                identity = row[2]
                if identity is not None:
                    if identity not in identity_groups:
                        identity_groups[identity] = {tuple(item) for item in self._group(db, 'identities', identity, series)}
                    if tuple(row) not in identity_groups[identity]:
                        raise ValueError('ticker delta identity census mismatch')
            return rows

    def identity_observations(self, identity, series):
        with self._connection() as db:
            rows = self._group(db, 'identities', identity, series)
            tickers = {}
            for row in rows:
                ticker = row[0]
                if ticker not in tickers:
                    group = self._group(db, 'tickers', ticker, series)
                    directory = lookup(db, self.trees['series']['root'], ticker)
                    if (directory is None or series not in _valid_series(directory)) != (not group):
                        raise ValueError('ticker delta series directory mismatch')
                    tickers[ticker] = {tuple(item) for item in group}
                if tuple(row) not in tickers[ticker]:
                    raise ValueError('ticker delta ticker census mismatch')
            return rows

    def ticker_series(self, ticker):
        if ticker == '':
            return set()
        with self._connection() as db:
            value = lookup(db, self.trees['series']['root'], ticker)
            return set() if value is None else set(_valid_series(value))

    def update(self, delta):
        if self.db is None:
            raise ValueError('ticker delta tree updates require transaction')
        validate_ticker_delta(delta)
        ticker_groups, identity_groups, series_groups = {}, {}, {}
        for row in delta['observations']:
            ticker, series, identity = row[:3]
            ticker_groups.setdefault((ticker, series), []).append(row)
            series_groups.setdefault(ticker, set()).add(series)
            if identity is not None:
                identity_groups.setdefault((identity, series), []).append(row)
        # Validate the existing touched groups and their reciprocal projections
        # before changing either root.  This prevents an update from silently
        # repairing an already inconsistent affected ticker/identity group.
        cached = {'tickers': {}, 'identities': {}}
        def prior(kind, selector, series):
            key = (selector, series)
            if key not in cached[kind]:
                rows = self.ticker_observations(selector, series) if kind == 'tickers' else self.identity_observations(selector, series)
                cached[kind][key] = (rows, {tuple(row) for row in rows})
            return cached[kind][key]
        for (ticker, series) in ticker_groups:
            for row in prior('tickers', ticker, series)[0]:
                if row[2] is not None and tuple(row) not in prior('identities', row[2], series)[1]:
                    raise ValueError('ticker delta identity census mismatch')
        for (identity, series) in identity_groups:
            for row in prior('identities', identity, series)[0]:
                if tuple(row) not in prior('tickers', row[0], series)[1]:
                    raise ValueError('ticker delta ticker census mismatch')
        for kind, groups in (('tickers', ticker_groups), ('identities', identity_groups)):
            for (selector, series), rows in sorted(groups.items()):
                key = _pair(selector, series)
                old = prior(kind, selector, series)[0]
                combined = merge_ticker_catalogs({'observations': old}, {'observations': rows})
                value = {'observations': [list(row) for row in combined['observations']]}
                _valid_group(value, kind, selector, series)
                h = self.trees[kind]
                h['root'] = insert(self.db, h['root'], key, value, replace=bool(old))
                h['count'] += not bool(old)
        for ticker, additions in sorted(series_groups.items()):
            h = self.trees['series']
            old = lookup(self.db, h['root'], ticker)
            existing = set() if old is None else set(_valid_series(old))
            value = {'series': sorted(existing | additions)}
            if old is not None and existing == set(value['series']):
                continue
            h['root'] = insert(self.db, h['root'], ticker, value, replace=old is not None)
            h['count'] += old is None

    def __getitem__(self, key):
        """Explicitly verify complete tree censuses and cross-group parity."""
        if key != 'observations':
            raise KeyError(key)
        with self._connection() as db:
            all_maps = {kind: entries(db, self.trees[kind]['root']) for kind in NAMES}
            if any(len(all_maps[kind]) != self.trees[kind]['count'] for kind in NAMES):
                raise ValueError('ticker delta tree count mismatch')
            import json
            rows, identities, directories = [], {}, {}
            for key, value in all_maps['tickers'].items():
                try:
                    selector, series = json.loads(key)
                except (ValueError, TypeError) as exc:
                    raise ValueError('invalid ticker delta key') from exc
                if _pair(selector, series) != key:
                    raise ValueError('invalid ticker delta key')
                group = _valid_group(value, 'tickers', selector, series)
                rows.extend(group)
                directories.setdefault(selector, set()).add(series)
                for row in group:
                    if row[2] is not None:
                        identities.setdefault(_pair(row[2], series), []).append(row)
            validate_ticker_delta({'observations': rows})
            for key, value in all_maps['identities'].items():
                try:
                    selector, series = json.loads(key)
                except (ValueError, TypeError) as exc:
                    raise ValueError('invalid ticker identity key') from exc
                if _pair(selector, series) != key:
                    raise ValueError('invalid ticker identity key')
                group = _valid_group(value, 'identities', selector, series)
                if key not in identities or group != [list(row) for row in merge_ticker_catalogs({'observations': []}, {'observations': identities.pop(key)})['observations']]:
                    raise ValueError('ticker delta identity census mismatch')
            if identities or {key: _valid_series(value) for key, value in all_maps['series'].items()} != {key: sorted(value) for key, value in directories.items()}:
                raise ValueError('ticker delta group census mismatch')
            return merge_ticker_catalogs({'observations': []}, {'observations': rows})['observations']
