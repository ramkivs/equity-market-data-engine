"""Transactional, integrity-sealed index of staged-but-unaccepted inputs.

The retained staged and accepted records remain authoritative. A one-time
migration builds this derived queue; triggers mark every relevant mutation
unsealed until the owning application transaction seals it. Ordinary reads scan
only the queue, never all previously accepted staged rows.
"""
import hashlib
import json

from .incremental_registry import RegistryError, _json

TABLE = 'publication_pending'
MARKER = 'publication_pending_format'
FORMAT = 'pending-index/1.0'
CREATE_TABLE = "CREATE TABLE publication_pending (file_name TEXT NOT NULL, date TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','conflict')), PRIMARY KEY(file_name,date))"
NONCE = 'publication_pending_nonce'
SEALED = 'publication_pending_sealed_nonce'
DIGEST = 'publication_pending_sha256'
INDEXES = {
    'publication_accepted_date': 'CREATE INDEX publication_accepted_date ON accepted(date)',
    'publication_staged_date': 'CREATE INDEX publication_staged_date ON staged_candidates(date)',
}

# Every staged mutation, including a payload-only update, invalidates the seal.
# Accepted mutations invalidate it when their governed identity/content changes.
def _refresh(where):
    return ("DELETE FROM publication_pending WHERE " + where + "; "
            "INSERT INTO publication_pending(file_name,date,digest,state) "
            "SELECT s.file_name,s.date,s.digest,CASE WHEN a.file_name IS NULL THEN 'pending' ELSE 'conflict' END "
            "FROM staged_candidates s LEFT JOIN accepted a ON a.file_name=s.file_name AND a.date=s.date "
            "WHERE (" + where.replace('file_name=', 's.file_name=').replace(' date=', ' s.date=') + ") "
            "AND (a.file_name IS NULL OR a.digest<>s.digest); ")


def _where(prefix):
    return 'file_name=' + prefix + '.file_name AND date=' + prefix + '.date'


def _trigger(name, timing, body):
    return 'CREATE TRIGGER ' + name + ' ' + timing + ' BEGIN ' + body + "UPDATE meta SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT) WHERE key='" + NONCE + "'; END"


TRIGGERS = {
    'publication_pending_stage_insert': _trigger('publication_pending_stage_insert', 'AFTER INSERT ON staged_candidates', _refresh(_where('NEW'))),
    'publication_pending_stage_delete': _trigger('publication_pending_stage_delete', 'AFTER DELETE ON staged_candidates', _refresh(_where('OLD'))),
    'publication_pending_stage_update': _trigger('publication_pending_stage_update', 'AFTER UPDATE ON staged_candidates', _refresh(_where('OLD')) + _refresh(_where('NEW'))),
    'publication_pending_accept_insert': _trigger('publication_pending_accept_insert', 'AFTER INSERT ON accepted', _refresh(_where('NEW'))),
    'publication_pending_accept_delete': _trigger('publication_pending_accept_delete', 'AFTER DELETE ON accepted', _refresh(_where('OLD'))),
    'publication_pending_accept_update': _trigger('publication_pending_accept_update', 'AFTER UPDATE OF file_name,date,digest ON accepted', _refresh(_where('OLD')) + _refresh(_where('NEW'))),
}


def _values(db):
    return {key: json.loads(value) for key, value in db.execute('SELECT key,value FROM meta WHERE key IN (?,?,?,?)', (MARKER, NONCE, SEALED, DIGEST))}


def _digest(db):
    digest = hashlib.sha256()
    for row in db.execute('SELECT file_name,date,digest,state FROM publication_pending ORDER BY file_name,date'):
        digest.update((_json(list(row)) + '\n').encode('utf8'))
    return digest.hexdigest()


def installed(db):
    if db.execute('SELECT 1 FROM meta WHERE key=?', (MARKER,)).fetchone() is not None:
        return True
    if db.execute('SELECT 1 FROM meta WHERE key IN (?,?,?)', (NONCE, SEALED, DIGEST)).fetchone() or any(
            db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (name,)).fetchone() for name in (TABLE,) + tuple(TRIGGERS) + tuple(INDEXES)):
        raise RegistryError('publication pending index metadata missing; explicit recovery required')
    return False


def _schema_check(db):
    table = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
    if not table or table[0] != CREATE_TABLE:
        raise RegistryError('publication pending index missing or invalid')
    for name, expected in TRIGGERS.items():
        row = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
        if row is None or row[0] != expected:
            raise RegistryError('publication pending index trigger missing or invalid')
    for name, expected in INDEXES.items():
        row = db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)).fetchone()
        if row is None or row[0] != expected:
            raise RegistryError('publication pending date index missing or invalid')


def verify(db):
    try:
        values = _values(db)
    except (ValueError, TypeError) as exc:
        raise RegistryError('publication pending index metadata invalid') from exc
    if set(values) != {MARKER, NONCE, SEALED, DIGEST} or values[MARKER] != FORMAT or type(values[NONCE]) is not int or values[NONCE] < 0 or values[SEALED] != values[NONCE] or not isinstance(values[DIGEST], str):
        raise RegistryError('publication pending index is missing or unsealed')
    _schema_check(db)
    if _digest(db) != values[DIGEST]:
        raise RegistryError('publication pending index digest mismatch')


def seal(db):
    """Seal only changes made by an already verified owning transaction."""
    if not db.in_transaction:
        raise RegistryError('publication pending seal requires transaction')
    values = _values(db)
    if set(values) != {MARKER, NONCE, SEALED, DIGEST} or values[MARKER] != FORMAT or type(values[NONCE]) is not int:
        raise RegistryError('publication pending index metadata invalid')
    _schema_check(db)
    db.execute('UPDATE meta SET value=? WHERE key=?', (_json(values[NONCE]), SEALED))
    db.execute('UPDATE meta SET value=? WHERE key=?', (_json(_digest(db)), DIGEST))


def ensure(db):
    """Install once from existing retained metadata, or verify without repair."""
    if db.in_transaction:
        raise RegistryError('pending index bootstrap requires an independent transaction')
    db.execute('BEGIN IMMEDIATE')
    try:
        if installed(db):
            verify(db)
        else:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_candidates'").fetchone():
                raise RegistryError('no staged candidates')
            names = (TABLE,) + tuple(TRIGGERS) + tuple(INDEXES)
            if any(db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (name,)).fetchone() for name in names):
                raise RegistryError('unidentified pending index state; no replacement performed')
            db.execute(CREATE_TABLE)
            for sql in tuple(TRIGGERS.values()) + tuple(INDEXES.values()):
                db.execute(sql)
            db.execute("INSERT INTO publication_pending SELECT s.file_name,s.date,s.digest,CASE WHEN a.file_name IS NULL THEN 'pending' ELSE 'conflict' END FROM staged_candidates s LEFT JOIN accepted a ON a.file_name=s.file_name AND a.date=s.date WHERE a.file_name IS NULL OR a.digest<>s.digest")
            db.executemany('INSERT INTO meta VALUES (?,?)', [(MARKER, _json(FORMAT)), (NONCE, _json(0)), (SEALED, _json(0)), (DIGEST, _json(_digest(db)))])
            verify(db)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def recover(db):
    """Explicitly rebuild known derived index after full registry validation.

    Caller holds the write lock and has independently verified baseline, staged,
    accepted, D21 and active-generation data; no user record is replaced.
    Unknown table or trigger definitions are never overwritten.
    """
    if not db.in_transaction:
        raise RegistryError('pending index recovery requires transaction')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_candidates'").fetchone():
        raise RegistryError('no staged candidates')
    table = db.execute("SELECT type,sql FROM sqlite_master WHERE name=?", (TABLE,)).fetchone()
    if table is None:
        db.execute(CREATE_TABLE)
    elif table != ('table', CREATE_TABLE):
        raise RegistryError('unidentified pending index table; no replacement performed')
    for name, expected in TRIGGERS.items():
        row = db.execute('SELECT type,sql FROM sqlite_master WHERE name=?', (name,)).fetchone()
        if row is None:
            db.execute(expected)
        elif row != ('trigger', expected):
            raise RegistryError('unidentified pending index trigger; no replacement performed')
    for name, expected in INDEXES.items():
        row = db.execute('SELECT type,sql FROM sqlite_master WHERE name=?', (name,)).fetchone()
        if row is None:
            db.execute(expected)
        elif row != ('index', expected):
            raise RegistryError('unidentified pending date index; no replacement performed')
    db.execute('DELETE FROM publication_pending')
    db.execute("INSERT INTO publication_pending SELECT s.file_name,s.date,s.digest,CASE WHEN a.file_name IS NULL THEN 'pending' ELSE 'conflict' END FROM staged_candidates s LEFT JOIN accepted a ON a.file_name=s.file_name AND a.date=s.date WHERE a.file_name IS NULL OR a.digest<>s.digest")
    for key, value in ((MARKER, FORMAT), (NONCE, 0), (SEALED, 0), (DIGEST, _digest(db))):
        db.execute('INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, _json(value)))
    verify(db)
