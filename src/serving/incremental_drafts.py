"""Durable, isolated draft snapshots for future composite publication.

Drafts are NOT published or served.  They preserve a consistent staged snapshot
and its delta-only derivations without reading baseline rows or source archives.
"""
import hashlib
import json
import sqlite3

from nse_engine.contract import RUN_METADATA_PLACEHOLDER

from .incremental_registry import RegistryError, _db_path, _json, _open, bindings
from .index import load_index
from .symbols import _identity, observed_trading_symbol
from .w2_continuity import build_continuity

FORMAT = 'incremental-draft/1.0'
MAX_DRAFT_ROWS = 20000
MAX_DRAFT_BYTES = 128 * 1024 * 1024


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS draft_generations (id TEXT PRIMARY KEY, manifest TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS draft_members (generation TEXT NOT NULL, digest TEXT NOT NULL, record TEXT NOT NULL, rows TEXT NOT NULL, evidence TEXT NOT NULL, PRIMARY KEY(generation,digest))')


def _validate(record, row_text, evidence_text, baseline):
    if record.get('state') != 'VALIDATED-STAGED-NOT-PUBLISHED' or record.get('baseline_manifest_sha256') != baseline.manifest_digest or record.get('bindings') != bindings(baseline):
        raise RegistryError('staged candidate identity or bindings mismatch')
    if _sha(row_text) != record.get('rows_sha256') or _sha(evidence_text) != record.get('evidence_sha256'):
        raise RegistryError('staged rows/evidence digest mismatch')
    try:
        evidence = json.loads(evidence_text)
        rows = [json.loads(line) for line in row_text.splitlines() if line.strip()]
    except (ValueError, TypeError) as exc:
        raise RegistryError('invalid staged canonical JSON') from exc
    determinism_view = []
    for row in rows:
        copy = dict(row)
        copy['provenance'] = dict(row.get('provenance') or {}, run_id=RUN_METADATA_PLACEHOLDER)
        determinism_view.append(_json(copy) + '\n')
    if len(rows) != record.get('rows') or not rows or evidence.get('rows_jsonl_sha256') != _sha(''.join(determinism_view)) or evidence.get('row_count') != len(rows):
        raise RegistryError('staged counts or evidence disagree')
    if evidence.get('archive_sha256') != record.get('digest') or evidence.get('member_name') != record.get('member_name'):
        raise RegistryError('staged evidence provenance mismatch')
    lines = set()
    for row in rows:
        p = row.get('provenance') or {}
        line = row.get('source_line_number')
        if (type(line) is not int or line in lines or row.get('business_date') != record.get('date') or
            row.get('format_family') != record.get('family') or p.get('archive_sha256') != record.get('digest') or
            p.get('run_id') != record.get('run_id') or p.get('member_name') != record.get('member_name') or
            p.get('tool_sha256') != record['bindings']['engine_sha256']):
            raise RegistryError('staged canonical lineage mismatch')
        lines.add(line)
    return rows


def create_draft(baseline, registry_root, state, saved, history, source_roots):
    """Capture a deterministic staged snapshot, with delta-only B2/B3 evidence.

    This never accepts inputs, switches readers or generates a composite W2.
    Existing baseline serving-index state is read/verified, never rebuilt.
    """
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    baseline_index, index_digest = load_index(state, baseline)
    db, _ = _open(baseline, path)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_candidates'").fetchone():
            raise RegistryError('no staged candidates')
        # Measure before loading staged blobs into Python; the cap must not
        # itself require materializing an unbounded corpus in memory.
        count, total_bytes = db.execute(
            'SELECT count(*), COALESCE(sum(length(CAST(record AS BLOB)) + length(CAST(rows AS BLOB)) + length(CAST(evidence AS BLOB))), 0) FROM staged_candidates'
        ).fetchone()
        if not count:
            raise RegistryError('no staged candidates')
        if total_bytes > MAX_DRAFT_BYTES:
            raise RegistryError('draft snapshot exceeds safe byte limit')
        entries = db.execute('SELECT record,rows,evidence FROM staged_candidates ORDER BY file_name,date,digest').fetchall()
        all_rows, observations, fragments, records = [], [], [], []
        for record_text, row_text, evidence_text in entries:
            try:
                record = json.loads(record_text)
                rows = _validate(record, row_text, evidence_text, baseline)
            except (ValueError, KeyError, TypeError) as exc:
                if isinstance(exc, RegistryError):
                    raise
                raise RegistryError('invalid staged record: %s' % exc) from exc
            if len(all_rows) + len(rows) > MAX_DRAFT_ROWS:
                raise RegistryError('draft snapshot exceeds safe row limit')
            source = 'incremental/' + record['digest'] + '.rows.jsonl'
            flags, pairs = {}, set()
            for row in rows:
                values = row.get('source_values') or {}
                pairs.add((values.get('listing_symbol') or '', values.get('series') or ''))
                for flag in row.get('flags', []):
                    name = flag.get('name') if isinstance(flag, dict) else None
                    if not isinstance(name, str) or not name:
                        raise RegistryError('invalid staged flag')
                    flags[name] = flags.get(name, 0) + 1
                ticker = observed_trading_symbol(row)
                observations.append({'source_file': source, 'source_line_number': row['source_line_number'],
                                     'trading_symbol': ticker, 'security_id': _identity(row),
                                     'series': values.get('series'), 'business_date': row.get('business_date')})
                all_rows.append((source, row))
            fragments.append({'source_file': source, 'family': record['family'], 'year': record['date'][:4],
                              'row_count': len(rows), 'business_date_min': record['date'], 'business_date_max': record['date'],
                              'instruments': [list(x) for x in sorted(pairs)], 'flag_census': flags})
            records.append(record)
        # B3 here covers the delta ONLY. It must never be used as a composite
        # result: ambiguity and transitions can depend on baseline observations.
        b3 = build_continuity(all_rows, baseline.manifest_digest)
        manifest = {'format': FORMAT, 'state': 'DRAFT-NOT-SERVEABLE',
                    'baseline_manifest_sha256': baseline.manifest_digest, 'baseline_index_sha256': index_digest,
                    'baseline_counts': baseline_index['counts'], 'candidates': records,
                    'delta_index_fragments': fragments, 'delta_b2_observations': observations,
                    'delta_only_b3': b3}
        text = _json(manifest)
        digest = _sha(text)
        # Detect index replacement while capturing; no historical rows are read.
        _, after = load_index(state, baseline)
        if after != index_digest:
            raise RegistryError('baseline index changed during snapshot')
        _schema(db)
        old = db.execute('SELECT manifest FROM draft_generations WHERE id=?', (digest,)).fetchone()
        if old:
            if old[0] != text:
                raise RegistryError('existing draft digest collision')
            stored = db.execute('SELECT record,rows,evidence FROM draft_members WHERE generation=? ORDER BY digest', (digest,)).fetchall()
            if sorted(entries) != sorted(stored):
                raise RegistryError('existing draft members disagree with its snapshot')
        else:
            db.execute('INSERT INTO draft_generations VALUES (?,?)', (digest, text))
            for record_text, row_text, evidence_text in entries:
                record = json.loads(record_text)
                db.execute('INSERT INTO draft_members VALUES (?,?,?,?,?)', (digest, record['digest'], record_text, row_text, evidence_text))
        db.commit()
        return {'draft_id': digest, 'state': 'DRAFT-NOT-SERVEABLE', 'candidates': len(records), 'rows': len(all_rows)}
    except sqlite3.IntegrityError as exc:
        raise RegistryError('draft snapshot failed: %s' % exc) from exc
    finally:
        db.close()


def list_drafts(baseline, registry_root, state, saved, history, source_roots):
    """List only drafts whose manifest and detached members still verify."""
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    db, _ = _open(baseline, path)
    try:
        db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='draft_generations'").fetchone():
            return []
        output = []
        for digest, text in db.execute('SELECT id,manifest FROM draft_generations ORDER BY id'):
            if _sha(text) != digest:
                raise RegistryError('draft manifest digest mismatch')
            try:
                doc = json.loads(text)
                if doc['state'] != 'DRAFT-NOT-SERVEABLE' or doc['baseline_manifest_sha256'] != baseline.manifest_digest:
                    raise RegistryError('draft identity mismatch')
                members = db.execute('SELECT record,rows,evidence FROM draft_members WHERE generation=? ORDER BY digest', (digest,)).fetchall()
                expected = sorted(_json(record) for record in doc['candidates'])
                if sorted(record for record, _, _ in members) != expected:
                    raise RegistryError('draft member set mismatch')
                for record, rows, evidence in members:
                    _validate(json.loads(record), rows, evidence, baseline)
            except (ValueError, KeyError, TypeError) as exc:
                if isinstance(exc, RegistryError):
                    raise
                raise RegistryError('invalid draft: %s' % exc) from exc
            output.append({'draft_id': digest, 'state': 'DRAFT-NOT-SERVEABLE'})
        return output
    finally:
        db.close()
