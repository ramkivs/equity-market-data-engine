"""Bound, one-time ticker lookup proofs over an existing verified catalog.

The proof file contains only the compact catalog ticker census, never canonical
rows. Group manifests detect accidental omission or miskeying of selected rows.
"""
import hashlib
import json
import os
import sqlite3
import tempfile
from urllib.parse import quote

from .continuity_catalog import CatalogError, _metadata, ticker_catalog, _feed
from .query import QueryError
from .incremental_registry import _json
from .catalog_publication import merge_ticker_catalogs

FILE = 'ticker_lookup_proofs.sqlite3'
FORMAT = 'ticker-lookup-proofs/1.0'


def _sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def _digest_rows(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update((_json(list(row)) + '\n').encode('utf8'))
    return digest.hexdigest()


def _manifest(db):
    rows = db.execute('SELECT kind,selector,series,row_count,digest FROM groups ORDER BY kind,selector,series').fetchall()
    return _digest_rows(rows), len(rows), {(kind, selector, series): (count, digest) for kind, selector, series, count, digest in rows}


def build(baseline, state, catalog_db, catalog_meta, expected=None):
    """Create once from the already-verified ticker census; never replace it."""
    path = os.path.join(state, FILE)
    if os.path.lexists(path):
        db, meta, _ = open_proofs(state, catalog_meta, expected)
        db.close()
        return meta
    if _metadata(catalog_db) != catalog_meta:
        raise CatalogError('ticker proof catalog changed before bootstrap')
    catalog = ticker_catalog(catalog_db, catalog_meta)
    fd, temp = tempfile.mkstemp(prefix='.ticker-proofs-', suffix='.part', dir=state)
    os.close(fd)
    try:
        db = sqlite3.connect(temp)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE rows (ticker TEXT NOT NULL, series TEXT NOT NULL, identity TEXT, raw TEXT, date_from TEXT, date_to TEXT)')
            db.executemany('INSERT INTO rows VALUES (?,?,?,?,?,?)', catalog['observations'])
            db.execute('CREATE INDEX rows_ticker ON rows(ticker,series)')
            db.execute('CREATE INDEX rows_identity ON rows(identity,series)')
            db.execute('CREATE TABLE groups (kind TEXT NOT NULL, selector TEXT NOT NULL, series TEXT NOT NULL, row_count INTEGER NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(kind,selector,series))')
            for kind in ('ticker', 'identity'):
                groups = {}
                for row in catalog['observations']:
                    selector = row[0] if kind == 'ticker' else row[2]
                    if selector is not None:
                        groups.setdefault((selector, row[1]), []).append(row)
                for (selector, series), values in groups.items():
                    values.sort(key=lambda row: tuple('' if v is None else v for v in row))
                    db.execute('INSERT INTO groups VALUES (?,?,?,?,?)', (kind, selector, series, len(values), _digest_rows(values)))
            group_sha, count, _ = _manifest(db)
            meta = {'format': FORMAT, 'catalog_sha256': _sha(_json(catalog_meta)),
                    'baseline_ticker_sha256': catalog_meta['ticker_sha256'],
                    'group_sha256': group_sha, 'group_count': count}
            if expected is not None and meta != expected:
                raise CatalogError('reconstructed ticker proof binding differs from active generation')
            db.executemany('INSERT INTO meta VALUES (?,?)', [(key, _json(value)) for key, value in meta.items()])
            db.commit()
        finally:
            db.close()
        with open(temp, 'rb') as stream:
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            db, existing, _ = open_proofs(state, catalog_meta, expected)
            db.close()
            return existing
        if os.name == 'posix':
            fd = os.open(state, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return meta
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def open_proofs(state, catalog_meta, expected=None, pinned_groups=None):
    path = os.path.join(state, FILE)
    if os.path.islink(path) or not os.path.isfile(path):
        raise CatalogError('ticker lookup proofs missing or unsafe; explicit recovery required')
    db = None
    try:
        db = sqlite3.connect('file:' + quote(os.path.abspath(path), safe='/') + '?mode=ro', uri=True)
        db.execute('BEGIN')
        meta = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}
        if (set(meta) != {'format', 'catalog_sha256', 'baseline_ticker_sha256', 'group_sha256', 'group_count'} or
                meta['format'] != FORMAT or meta['catalog_sha256'] != _sha(_json(catalog_meta)) or
                meta['baseline_ticker_sha256'] != catalog_meta['ticker_sha256'] or (expected is not None and meta != expected)):
            raise CatalogError('ticker lookup proof binding mismatch')
        if pinned_groups is None:
            digest, count, groups = _manifest(db)
            if digest != meta['group_sha256'] or count != meta['group_count']:
                raise CatalogError('ticker lookup proof group manifest mismatch')
        else:
            groups = pinned_groups
        return db, meta, groups
    except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        if db is not None:
            db.close()
        if isinstance(exc, CatalogError):
            raise
        raise CatalogError('ticker lookup proofs invalid: %s' % exc) from exc


def selected(db, groups, kind, value, series):
    if kind not in ('ticker', 'identity') or not isinstance(value, str) or not isinstance(series, str):
        raise CatalogError('invalid ticker proof selector')
    column = 'ticker' if kind == 'ticker' else 'identity'
    rows = db.execute('SELECT ticker,series,identity,raw,date_from,date_to FROM rows WHERE ' + column + '=? AND series=? ORDER BY ticker,series,identity,raw,date_from,date_to', (value, series)).fetchall()
    actual = (len(rows), _digest_rows(rows)) if rows else None
    if actual != groups.get((kind, value, series)):
        raise CatalogError('ticker lookup group observations mismatch')
    return rows


class TargetedCatalog:
    """Generation-pinned incremental census plus verified baseline lookups."""
    def __init__(self, state, catalog_meta, proof_meta, delta, db=None, groups=None):
        self.state, self.catalog_meta, self.proof_meta, self.delta = state, catalog_meta, proof_meta, delta
        self.db, self.groups = db, groups

    def _lookup(self, kind, value, series):
        db = self.db
        try:
            if db is None:
                db, _, groups = open_proofs(self.state, self.catalog_meta, self.proof_meta, self.groups)
            else:
                groups = self.groups
            base = selected(db, groups, kind, value, series)
            index = 0 if kind == 'ticker' else 2
            extra = (self.delta.ticker_observations(value, series) if kind == 'ticker' else self.delta.identity_observations(value, series)) if hasattr(self.delta, 'ticker_observations') else [row for row in self.delta['observations'] if row[index] == value and row[1] == series]
            return merge_ticker_catalogs({'observations': base}, {'observations': extra})['observations']
        except (sqlite3.Error, ValueError, OSError) as exc:
            raise QueryError('composite-unavailable', 'targeted ticker lookup failed: %s' % exc) from exc
        finally:
            if self.db is None and db is not None:
                db.close()

    def ticker_series(self, ticker):
        groups = self.groups
        db = None
        try:
            if groups is None:
                db, _, groups = open_proofs(self.state, self.catalog_meta, self.proof_meta)
            delta_series = self.delta.ticker_series(ticker) if hasattr(self.delta, 'ticker_series') else {row[1] for row in self.delta['observations'] if row[0] == ticker}
            return {series for kind, selector, series in groups if kind == 'ticker' and selector == ticker} | delta_series
        except (sqlite3.Error, ValueError, OSError) as exc:
            raise QueryError('composite-unavailable', 'ticker series lookup failed: %s' % exc) from exc
        finally:
            if db is not None:
                db.close()

    def ticker_observations(self, ticker, series):
        return self._lookup('ticker', ticker, series)

    def identity_observations(self, identity, series):
        return self._lookup('identity', identity, series)

    def __getitem__(self, key):
        # Compatibility for explicit full-census inspection, not normal queries.
        if key != 'observations':
            raise KeyError(key)
        db = self.db
        try:
            if db is None:
                db, _, _ = open_proofs(self.state, self.catalog_meta, self.proof_meta, self.groups)
            rows = db.execute('SELECT ticker,series,identity,raw,date_from,date_to FROM rows ORDER BY ticker,series,identity,raw').fetchall()
            digest = hashlib.sha256()
            for row in rows:
                _feed(digest, _json(list(row)))
            if len(rows) != self.catalog_meta['ticker_count'] or digest.hexdigest() != self.catalog_meta['ticker_sha256']:
                raise ValueError('full ticker proof census mismatch')
            return merge_ticker_catalogs({'observations': rows}, {'observations': self.delta['observations']})['observations']
        except (sqlite3.Error, ValueError, OSError) as exc:
            raise QueryError('composite-unavailable', 'ticker census read failed: %s' % exc) from exc
        finally:
            if self.db is None and db is not None:
                db.close()


def verify(state, catalog_meta):
    """Explicit full proof-file verification against the baseline ticker digest."""
    db, meta, groups = open_proofs(state, catalog_meta)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise CatalogError('ticker proof SQLite integrity check failed')
        rows = db.execute('SELECT ticker,series,identity,raw,date_from,date_to FROM rows ORDER BY ticker,series,identity,raw').fetchall()
        digest = hashlib.sha256()
        actual_groups = {}
        for row in rows:
            _feed(digest, _json(list(row)))
            for kind, selector in (('ticker', row[0]), ('identity', row[2])):
                if selector is not None:
                    actual_groups.setdefault((kind, selector, row[1]), []).append(row)
        if len(rows) != catalog_meta['ticker_count'] or digest.hexdigest() != catalog_meta['ticker_sha256']:
            raise CatalogError('ticker proof full census mismatch')
        computed = {key: (len(value), _digest_rows(value)) for key, value in actual_groups.items()}
        if computed != groups:
            raise CatalogError('ticker proof full group mismatch')
        return meta
    except sqlite3.Error as exc:
        raise CatalogError('ticker proof full verification failed: %s' % exc) from exc
    finally:
        db.close()


def recover(baseline, state, registry, saved, history, source_roots):
    """Explicitly reconstruct a missing proof file only if its binding matches.

    Never replaces an existing file. Active generation and prior registry state
    are left untouched; historical canonical rows and archives are not opened.
    """
    from .continuity_catalog import open_catalog
    from .incremental_registry import _db_path, _open
    from .incremental_publication import _sha as generation_sha
    registry_path = _db_path(baseline, registry, state, saved, history, source_roots)
    registry_db, _ = _open(baseline, registry_path)
    catalog_db = None
    try:
        registry_db.execute('BEGIN')
        row = registry_db.execute('SELECT a.generation,g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation WHERE a.singleton=1').fetchone()
        if row is None or generation_sha(row[1]) != row[0]:
            raise CatalogError('active generation missing or invalid')
        payload = json.loads(row[1])
        if payload.get('format') not in ('catalog-composite/7.0', 'catalog-composite/8.0', 'catalog-composite/9.0', 'catalog-composite/10.0', 'catalog-composite/11.0', 'catalog-composite/12.0', 'catalog-composite/13.0') or payload.get('baseline_manifest_sha256') != baseline.manifest_digest or not isinstance(payload.get('ticker_proofs_binding'), dict):
            raise CatalogError('active generation has no valid ticker proof binding')
        catalog_db, catalog_meta = open_catalog(baseline, state)
        catalog_db.execute('BEGIN')
        if _metadata(catalog_db) != catalog_meta or payload.get('catalog_binding') != catalog_meta or payload.get('baseline_index_sha256') != catalog_meta['baseline_index_sha256']:
            raise CatalogError('active generation catalog binding mismatch')
        meta = build(baseline, state, catalog_db, catalog_meta, payload['ticker_proofs_binding'])
        verify(state, catalog_meta)
        return {'status': 'VERIFIED-OR-RECOVERED', 'generation': row[0], 'binding': meta}
    finally:
        if catalog_db is not None:
            catalog_db.close()
        registry_db.close()
