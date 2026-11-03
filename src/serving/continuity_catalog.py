"""One-time, baseline-bound continuity observation catalog.

This is a streaming projection of already-qualified canonical rows, not an
archive ingest and not a new authoritative corpus. It is not yet wired into
composite publication or Q3-Q5; see the B5 implementation evidence.
"""
import datetime
import hashlib
import json
import os
import sqlite3
import tempfile
from urllib.parse import quote

from nse_engine.compact import normalize_upper_trim
from .atomic import sync_file
from .index import load_index
from .incremental_registry import _db_path, _open
from .paths import validate_roots, validate_store_root
from .symbols import _identity, observed_trading_symbol

LEGACY_FORMAT = 'continuity-catalog/1.0'
FORMAT = 'continuity-catalog/2.0'
FILENAME = 'continuity_catalog.sqlite3'


class CatalogError(ValueError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _sha(value):
    return hashlib.sha256(value.encode('utf8')).hexdigest()


def _feed(digest, value):
    data = value.encode('utf8')
    digest.update(len(data).to_bytes(8, 'big'))
    digest.update(data)


def _projection(row):
    values = row.get('source_values')
    provenance = row.get('provenance')
    line, date = row.get('source_line_number'), row.get('business_date')
    if (not isinstance(values, dict) or not isinstance(provenance, dict) or
            type(line) is not int or line < 1 or not isinstance(date, str)):
        raise CatalogError('invalid canonical continuity observation')
    try:
        if datetime.date.fromisoformat(date).isoformat() != date:
            raise ValueError('noncanonical date')
    except ValueError as exc:
        raise CatalogError('invalid business date') from exc
    required = ('listing_symbol', 'series', 'security_isin')
    if any(not isinstance(values.get(k), str) for k in required):
        raise CatalogError('canonical row lacks W2 source fields')
    if not isinstance(row.get('isin_validity'), str):
        raise CatalogError('canonical row lacks ISIN validity')
    return {'source_line_number': line, 'business_date': date,
            'format_family': row.get('format_family'), 'isin_validity': row['isin_validity'],
            'isin_normalized': row.get('isin_normalized'), 'provenance': provenance,
            'source_values': {k: values.get(k) for k in
                              ('listing_symbol', 'series', 'security_isin', 'underlying_symbol', 'segment', 'instrument_type')}}


def _metadata(db):
    try:
        meta = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}
        required = {'format', 'baseline_manifest_sha256', 'baseline_index_sha256', 'row_count',
                    'observation_sha256', 'ticker_sha256', 'ticker_count', 'complete'}
        if meta.get('format') == FORMAT:
            required |= {'group_sha256', 'group_count'}
        if set(meta) != required or meta.get('format') not in (LEGACY_FORMAT, FORMAT) or meta['complete'] is not True:
            raise CatalogError('invalid or incomplete catalog metadata')
        if meta['format'] == FORMAT and (type(meta['group_count']) is not int or meta['group_count'] < 0):
            raise CatalogError('invalid catalog group count')
        if type(meta['row_count']) is not int or meta['row_count'] < 0 or type(meta['ticker_count']) is not int:
            raise CatalogError('invalid catalog counts')
        for name in ('baseline_manifest_sha256', 'baseline_index_sha256', 'observation_sha256', 'ticker_sha256') + (('group_sha256',) if meta['format'] == FORMAT else ()):
            if not isinstance(meta[name], str) or len(meta[name]) != 64 or any(c not in '0123456789abcdef' for c in meta[name]):
                raise CatalogError('invalid catalog digest')
        return meta
    except (sqlite3.Error, ValueError, TypeError) as exc:
        if isinstance(exc, CatalogError):
            raise
        raise CatalogError('invalid catalog metadata: %s' % exc) from exc


def open_catalog(baseline, state):
    """Open an existing catalog read-only; validate its baseline/index binding.

    This checks metadata and binding only. Version 2 identity lookups verify
    the compact group manifest and all selected observations before returning.
    Version 1 requires a full verification or upgrade before trusted selection.
    """
    validate_roots(package=baseline.root, state=state)
    validate_store_root(state, 'state')
    path = os.path.join(state, FILENAME)
    if os.path.islink(path) or not os.path.isfile(path):
        raise CatalogError('catalog missing or unsafe')
    try:
        db = sqlite3.connect('file:' + quote(os.path.abspath(path), safe='/') + '?mode=ro', uri=True)
        meta = _metadata(db)
        _, index_digest = load_index(state, baseline)
        if meta['baseline_manifest_sha256'] != baseline.manifest_digest or meta['baseline_index_sha256'] != index_digest:
            raise CatalogError('catalog baseline/index binding mismatch')
        return db, meta
    except BaseException:
        if 'db' in locals():
            db.close()
        raise


def _check_observation(item):
    ordinal, source, line, date, w2, b2, ticker, series, raw_symbol, text, row_hash = item
    if _sha(text) != row_hash:
        raise CatalogError('catalog observation digest mismatch')
    try:
        row = json.loads(text)
        projection = _projection(row)
        values = projection['source_values']
        expected = (projection['source_line_number'], projection['business_date'],
                    normalize_upper_trim(values['security_isin']) or None, _identity(projection),
                    observed_trading_symbol(projection)['observed_symbol'], values['series'], values['listing_symbol'])
        if _json(projection) != text or expected != (line, date, w2, b2, ticker, series, raw_symbol):
            raise CatalogError('catalog observation/index mismatch')
        return source, line, text, projection
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        if isinstance(exc, CatalogError):
            raise
        raise CatalogError('invalid catalog observation: %s' % exc) from exc


def _group_rows(db):
    """Compute group hashes by streaming the catalog's two identity indexes."""
    for kind, column in (('b2', 'b2_identity'), ('w2', 'w2_identity')):
        previous, digest, count = None, None, 0
        sql = ('SELECT ' + column + ',ordinal,source_file,source_line,projection_sha256 '
               'FROM observations WHERE ' + column + ' IS NOT NULL ORDER BY ' + column + ',ordinal')
        for identity, ordinal, source, line, row_hash in db.execute(sql):
            if identity != previous:
                if previous is not None:
                    yield kind, previous, count, digest.hexdigest()
                previous, digest, count = identity, hashlib.sha256(), 0
            _feed(digest, _json([ordinal, source, line, row_hash]))
            count += 1
        if previous is not None:
            yield kind, previous, count, digest.hexdigest()


def _group_digest(rows):
    digest = hashlib.sha256()
    count = 0
    for item in rows:
        _feed(digest, _json(list(item))); count += 1
    return digest.hexdigest(), count


def _create_groups(db):
    db.execute('CREATE TABLE identity_groups (kind TEXT NOT NULL, identity TEXT NOT NULL, '
               'row_count INTEGER NOT NULL, group_sha256 TEXT NOT NULL, PRIMARY KEY(kind,identity))')
    batch = []
    for group in _group_rows(db):
        batch.append(group)
        if len(batch) >= 1000:
            db.executemany('INSERT INTO identity_groups VALUES (?,?,?,?)', batch)
            batch.clear()
    if batch:
        db.executemany('INSERT INTO identity_groups VALUES (?,?,?,?)', batch)
    return _group_digest(db.execute('SELECT kind,identity,row_count,group_sha256 FROM identity_groups ORDER BY kind,identity'))


def _validated_groups(db, meta):
    if meta.get('format') != FORMAT:
        raise CatalogError('catalog identity proofs unavailable; upgrade catalog first')
    groups = {}
    digest = hashlib.sha256()
    try:
        for kind, identity, count, group_sha in db.execute('SELECT kind,identity,row_count,group_sha256 FROM identity_groups ORDER BY kind,identity'):
            item = [kind, identity, count, group_sha]
            _feed(digest, _json(item))
            if (kind not in ('w2', 'b2') or not isinstance(identity, str) or not identity or
                    type(count) is not int or count < 1 or not isinstance(group_sha, str) or len(group_sha) != 64 or
                    any(c not in '0123456789abcdef' for c in group_sha)):
                raise CatalogError('invalid catalog identity group')
            groups[(kind, identity)] = (count, group_sha)
    except sqlite3.Error as exc:
        raise CatalogError('catalog identity group read failed: %s' % exc) from exc
    if len(groups) != meta['group_count'] or digest.hexdigest() != meta['group_sha256']:
        raise CatalogError('catalog identity group manifest mismatch')
    return groups


class _PinnedIdentityManifest:
    def __init__(self, db, groups):
        self.db = db
        self.groups = groups


def _pin_identity_manifest(db, meta):
    if not db.in_transaction or _metadata(db) != meta:
        raise CatalogError('identity manifest requires the bound read transaction')
    return _PinnedIdentityManifest(db, _validated_groups(db, meta))


def _pin_indexed_identity_manifest(db, meta, tree):
    from .identity_proof_tree import IdentityProofTree, validate_header
    if not db.in_transaction or _metadata(db) != meta or not isinstance(tree, IdentityProofTree):
        raise CatalogError('indexed identity proof requires bound transactions')
    validate_header(tree.header, meta)
    return _PinnedIdentityManifest(db, tree)


def observations_for_identity(db, identity, kind='w2', pinned_groups=None):
    """Verify a compact group manifest and only the selected identity rows.

    Row hashes alone cannot detect a corrupt key that hides a row. The separate
    authenticated count and group digest detect omitted or miskeyed rows. A
    read transaction pins both the group manifest and observations. A caller
    already holding that transaction can pass a previously verified manifest to
    reuse it across affected identities without rescanning the census.
    """
    column = {'w2': 'w2_identity', 'b2': 'b2_identity'}.get(kind)
    if column is None or not isinstance(identity, str) or not identity:
        raise CatalogError('invalid catalog identity selector')
    started = not db.in_transaction
    try:
        if started:
            db.execute('BEGIN')
        if pinned_groups is not None:
            if started or not isinstance(pinned_groups, _PinnedIdentityManifest) or pinned_groups.db is not db:
                raise CatalogError('pinned identity manifest requires its existing read transaction')
            expected = pinned_groups.groups.get((kind, identity))
        else:
            meta = _metadata(db)
            expected = _validated_groups(db, meta).get((kind, identity))
        digest = hashlib.sha256()
        result = []
        for item in db.execute('SELECT * FROM observations WHERE ' + column + '=? ORDER BY ordinal', (identity,)):
            source, line, _text, projection = _check_observation(item)
            _feed(digest, _json([item[0], source, line, item[10]]))
            result.append((source, projection))
        actual = (len(result), digest.hexdigest()) if result else None
        if actual != expected:
            raise CatalogError('catalog identity group observations mismatch')
        return iter(result)
    except sqlite3.Error as exc:
        raise CatalogError('catalog observation read failed: %s' % exc) from exc
    finally:
        if started and db.in_transaction:
            db.rollback()


def ticker_catalog(db, meta):
    """Load the compact ticker census only after verifying its complete digest."""
    digest = hashlib.sha256()
    observations = []
    try:
        for item in db.execute('SELECT ticker,series,identity,raw_symbol,date_from,date_to FROM tickers ORDER BY ticker,series,identity,raw_symbol'):
            _feed(digest, _json(list(item))); observations.append(item)
    except sqlite3.Error as exc:
        raise CatalogError('catalog ticker read failed: %s' % exc) from exc
    if len(observations) != meta['ticker_count'] or digest.hexdigest() != meta['ticker_sha256']:
        raise CatalogError('catalog ticker census or digest mismatch')
    return {'observations': tuple(observations)}


def verify_catalog(baseline, state):
    """Full explicit integrity check (linear in catalog size, not archive IO)."""
    db, meta = open_catalog(baseline, state)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise CatalogError('catalog SQLite integrity check failed')
        digest = hashlib.sha256()
        count = 0
        for item in db.execute('SELECT * FROM observations ORDER BY ordinal'):
            source, line, text, _projection_data = _check_observation(item)
            _feed(digest, _json([source, line, text])); count += 1
        if count != meta['row_count'] or digest.hexdigest() != meta['observation_sha256']:
            raise CatalogError('catalog observation census or digest mismatch')
        ticker_catalog(db, meta)
        if meta['format'] == FORMAT:
            expected_groups = _validated_groups(db, meta)
            actual_groups = {(kind, identity): (count, digest) for kind, identity, count, digest in _group_rows(db)}
            if actual_groups != expected_groups:
                raise CatalogError('catalog identity group observations mismatch')
        from .ticker_proofs import FILE as PROOF_FILE, verify as verify_ticker_proofs
        if os.path.lexists(os.path.join(state, PROOF_FILE)):
            verify_ticker_proofs(state, meta)
        return meta
    except sqlite3.Error as exc:
        raise CatalogError('catalog integrity failure: %s' % exc) from exc
    finally:
        db.close()


def upgrade_catalog(baseline, state):
    """Atomically add identity proofs to a verified v1 catalog, once.

    No baseline canonical file or source archive is opened. Existing catalog
    bytes are never rebuilt from the baseline. A SQLite transaction protects
    the old format if the migration fails or the process is interrupted.
    """
    read_db, meta = open_catalog(baseline, state)
    read_db.close()
    path = os.path.join(state, FILENAME)
    try:
        db = sqlite3.connect('file:' + quote(os.path.abspath(path), safe='/') + '?mode=rw', uri=True)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            # A second connection verifies the last committed state while this
            # connection's reserved write lock prevents concurrent modifications.
            meta = verify_catalog(baseline, state)
            if meta['format'] == FORMAT:
                db.commit()
                return {'status': 'ALREADY-CURRENT', **meta}
            group_sha, group_count = _create_groups(db)
            db.execute('UPDATE meta SET value=? WHERE key=?', (_json(FORMAT), 'format'))
            db.executemany('INSERT INTO meta VALUES (?,?)', [('group_sha256', _json(group_sha)), ('group_count', _json(group_count))])
            db.commit()
            return {'status': 'UPGRADED', **dict(meta, format=FORMAT, group_sha256=group_sha, group_count=group_count)}
        finally:
            db.close()
    except sqlite3.Error as exc:
        raise CatalogError('catalog upgrade failed: %s' % exc) from exc


def bootstrap(baseline, state, registry, saved, history, source_roots):
    """Create once, exclusively; interruptions never replace existing state."""
    registry_path = _db_path(baseline, registry, state, saved, history, source_roots)
    db, _ = _open(baseline, registry_path)
    db.close()
    index, index_digest = load_index(state, baseline)
    path = os.path.join(state, FILENAME)
    if os.path.lexists(path):
        return {'status': 'ALREADY-BOOTSTRAPPED', **verify_catalog(baseline, state)}
    expected_files = set(baseline.row_files())
    if set(index.get('files', {})) != expected_files:
        raise CatalogError('baseline index file set differs from qualified manifest')
    fd, temporary = tempfile.mkstemp(prefix='.continuity-catalog-', suffix='.part', dir=state)
    os.close(fd)
    try:
        db = sqlite3.connect(temporary)
        try:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE observations (ordinal INTEGER PRIMARY KEY, source_file TEXT NOT NULL, source_line INTEGER NOT NULL, '
                       'business_date TEXT NOT NULL, w2_identity TEXT, b2_identity TEXT, ticker TEXT, series TEXT NOT NULL, '
                       'raw_symbol TEXT NOT NULL, projection TEXT NOT NULL, projection_sha256 TEXT NOT NULL, UNIQUE(source_file,source_line))')
            db.execute('CREATE TABLE tickers (ticker TEXT NOT NULL, series TEXT NOT NULL, identity TEXT, raw_symbol TEXT, date_from TEXT, date_to TEXT)')
            digest = hashlib.sha256()
            count = 0
            batch = []
            for source in baseline.row_files():
                file_count = 0
                with open(baseline.path(source), encoding='utf8') as stream:
                    for text in stream:
                        if not text.strip():
                            continue
                        try:
                            row = json.loads(text)
                            projected = _projection(row)
                        except (ValueError, TypeError, AttributeError) as exc:
                            raise CatalogError('invalid canonical observation in %s: %s' % (source, exc)) from exc
                        values = projected['source_values']
                        line = projected['source_line_number']
                        data = _json(projected)
                        count += 1; file_count += 1
                        _feed(digest, _json([source, line, data]))
                        ticker = observed_trading_symbol(projected)['observed_symbol']
                        w2_identity = normalize_upper_trim(values['security_isin']) or None
                        batch.append((count, source, line, projected['business_date'], w2_identity, _identity(projected),
                                      ticker, values['series'], values['listing_symbol'], data, _sha(data)))
                        if len(batch) >= 1000:
                            db.executemany('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)', batch); batch.clear()
                if file_count != index['files'][source].get('row_count'):
                    raise CatalogError('qualified file row count disagrees with serving index: %s' % source)
            if batch:
                db.executemany('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)', batch)
            if count != index.get('counts', {}).get('row_count'):
                raise CatalogError('catalog row count disagrees with serving index')
            db.execute('CREATE INDEX observations_w2 ON observations(w2_identity,ordinal)')
            db.execute('CREATE INDEX observations_b2 ON observations(b2_identity,series,ordinal)')
            db.execute('CREATE INDEX observations_ticker ON observations(ticker,series,ordinal)')
            db.execute('INSERT INTO tickers SELECT ticker,series,b2_identity,raw_symbol, '
                       'min(CASE WHEN b2_identity IS NOT NULL THEN business_date END), '
                       'max(CASE WHEN b2_identity IS NOT NULL THEN business_date END) '
                       'FROM observations WHERE ticker IS NOT NULL GROUP BY ticker,series,b2_identity,raw_symbol')
            ticker_digest = hashlib.sha256()
            ticker_count = 0
            for item in db.execute('SELECT ticker,series,identity,raw_symbol,date_from,date_to FROM tickers ORDER BY ticker,series,identity,raw_symbol'):
                _feed(ticker_digest, _json(list(item))); ticker_count += 1
            group_sha, group_count = _create_groups(db)
            meta = {'format': FORMAT, 'group_sha256': group_sha, 'group_count': group_count,
                    'baseline_manifest_sha256': baseline.manifest_digest,
                    'baseline_index_sha256': index_digest, 'row_count': count, 'observation_sha256': digest.hexdigest(),
                    'ticker_sha256': ticker_digest.hexdigest(), 'ticker_count': ticker_count, 'complete': True}
            db.executemany('INSERT INTO meta VALUES (?,?)', [(key, _json(value)) for key, value in meta.items()])
            db.commit()
        finally:
            db.close()
        sync_file(temporary)
        # Atomic no-replace publication. Unlike os.replace this never overwrites
        # an existing catalog, even if two bootstraps race.
        try:
            os.link(temporary, path)
        except FileExistsError:
            return {'status': 'ALREADY-BOOTSTRAPPED', **verify_catalog(baseline, state)}
        if os.name == 'posix':
            directory = os.open(state, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return {'status': 'BOOTSTRAPPED', **meta}
    except sqlite3.Error as exc:
        raise CatalogError('catalog bootstrap failed: %s' % exc) from exc
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
