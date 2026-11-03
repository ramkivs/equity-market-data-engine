"""Pending index bootstrap, tamper detection and explicit recovery."""
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.composite_binding import validate_registry
from serving.incremental_publication import active_snapshot, publish
from serving.incremental_registry import RegistryError
from serving.query import QueryError
from serving.pending_queue import ensure, verify, installed


class PendingQueueTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def test_bootstrap_preserves_staging_and_scans_only_pending_after_publication(self):
        self.init()
        with sqlite3.connect(self.dbpath()) as db:
            before = db.execute('SELECT * FROM staged_candidates').fetchall()
        publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertTrue(installed(db)); verify(db)
            self.assertEqual(db.execute('SELECT * FROM staged_candidates').fetchall(), before)
            self.assertEqual(db.execute('SELECT count(*) FROM publication_pending').fetchone()[0], 0)
            plan = ' '.join(str(r) for r in db.execute('EXPLAIN QUERY PLAN SELECT 1 FROM accepted WHERE date=?', ('2025-01-01',)))
            self.assertIn('publication_accepted_date', plan)
            plan = ' '.join(str(r) for r in db.execute('EXPLAIN QUERY PLAN SELECT 1 FROM staged_candidates WHERE date=?', ('2025-01-01',)))
            self.assertIn('publication_staged_date', plan)
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            verify(db)
            self.assertEqual(db.execute('SELECT count(*) FROM publication_pending').fetchone()[0], 1)
        import serving.catalog_publication as cp
        statements = []
        original = cp._open
        def traced(*args):
            db, meta = original(*args)
            db.set_trace_callback(statements.append)
            return db, meta
        with mock.patch.object(cp, '_open', side_effect=traced):
            publish(*self.args)
        queries = [s.lower() for s in statements if 'staged_candidates' in s.lower() and s.lower().lstrip().startswith('select')]
        self.assertTrue(queries)
        self.assertTrue(all('publication_pending' in q for q in queries), queries)
        with sqlite3.connect(self.dbpath()) as db:
            verify(db)
            self.assertEqual(db.execute('SELECT count(*) FROM publication_pending').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)

    def test_existing_proof_manifest_verified_once_per_publication(self):
        self.init(); publish(*self.args); self.next_delta()
        import serving.ticker_proofs as proofs
        import serving.continuity_catalog as catalog
        with mock.patch.object(proofs, '_manifest', wraps=proofs._manifest) as ticker_manifest, \
             mock.patch.object(catalog, '_validated_groups', wraps=catalog._validated_groups) as identity_manifest:
            self.assertEqual(publish(*self.args)['new_inputs'], 1)
        self.assertEqual(ticker_manifest.call_count, 1)
        self.assertEqual(identity_manifest.call_count, 0)

    def test_interrupted_bootstrap_rolls_back_and_retries(self):
        self.init()
        with sqlite3.connect(self.dbpath()) as db:
            with mock.patch('serving.pending_queue._digest', side_effect=RuntimeError('interrupted bootstrap')):
                with self.assertRaisesRegex(RuntimeError, 'interrupted bootstrap'):
                    ensure(db)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='publication_pending'").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM meta WHERE key='publication_pending_format'").fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 1)
            ensure(db)
            verify(db)
        self.assertEqual(publish(*self.args)['new_inputs'], 1)

    def test_deleted_queue_entry_fails_closed_and_explicit_recovery_preserves_records(self):
        self.init(); first = publish(*self.args); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            records = db.execute('SELECT * FROM staged_candidates ORDER BY file_name').fetchall()
            db.execute('DELETE FROM publication_pending')
        with self.assertRaisesRegex(RegistryError, 'pending index digest mismatch'):
            publish(*self.args)
        with self.assertRaisesRegex(QueryError, 'pending index digest mismatch'):
            validate_registry(self.baseline, self.args[2], self.args[1])
        result = validate_registry(self.baseline, self.args[2], self.args[1], recover_pending=True)
        self.assertEqual(result['pending_index'], 'RECOVERED')
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT * FROM staged_candidates ORDER BY file_name').fetchall(), records)
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], first['generation'])
            verify(db)
        self.assertEqual(publish(*self.args)['new_inputs'], 1)

    def test_staged_tamper_unseals_and_recovery_refuses_corrupt_data(self):
        self.init(); publish(*self.args); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            original = db.execute("SELECT rows FROM staged_candidates WHERE file_name='later.zip'").fetchone()[0]
            db.execute("UPDATE staged_candidates SET rows='damaged' WHERE file_name='later.zip'")
        with self.assertRaisesRegex(RegistryError, 'unsealed'):
            publish(*self.args)
        with self.assertRaisesRegex(QueryError, 'digest mismatch'):
            validate_registry(self.baseline, self.args[2], self.args[1], recover_pending=True)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute("UPDATE staged_candidates SET rows=? WHERE file_name='later.zip'", (original,))
        validate_registry(self.baseline, self.args[2], self.args[1], recover_pending=True)
        self.assertEqual(publish(*self.args)['new_inputs'], 1)

    def test_missing_metadata_or_trigger_fails_closed_and_can_be_rebuilt(self):
        self.init(); first = publish(*self.args); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            db.execute("DELETE FROM meta WHERE key='publication_pending_format'")
            db.execute('DROP TRIGGER publication_pending_stage_insert')
        with self.assertRaisesRegex(RegistryError, 'metadata missing'):
            publish(*self.args)
        with self.assertRaisesRegex(RegistryError, 'metadata missing'):
            self.next_delta()
        self.assertEqual(validate_registry(self.baseline, self.args[2], self.args[1], recover_pending=True)['generation'], first['generation'])
        self.assertEqual(publish(*self.args)['new_inputs'], 1)

    def test_malformed_derived_metadata_can_be_explicitly_recovered(self):
        self.init(); first = publish(*self.args); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            db.execute("UPDATE meta SET value='not-json' WHERE key='publication_pending_sha256'")
        with self.assertRaisesRegex(RegistryError, 'pending index metadata invalid'):
            publish(*self.args)
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].manifest_digest, first['generation'])
        validate_registry(self.baseline, self.args[2], self.args[1], recover_pending=True)
        self.assertEqual(publish(*self.args)['new_inputs'], 1)

    def test_unknown_schema_is_never_overwritten(self):
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DROP TRIGGER publication_pending_stage_insert')
            db.execute('CREATE TRIGGER publication_pending_stage_insert AFTER INSERT ON staged_candidates BEGIN SELECT 1; END')
        with self.assertRaisesRegex(QueryError, 'unidentified pending index trigger'):
            validate_registry(self.baseline, self.args[2], self.args[1], recover_pending=True)
        with sqlite3.connect(self.dbpath()) as db:
            sql = db.execute("SELECT sql FROM sqlite_master WHERE name='publication_pending_stage_insert'").fetchone()[0]
        self.assertIn('SELECT 1', sql)

    def test_staging_seal_failure_rolls_back_new_staged_record(self):
        self.init(); publish(*self.args)
        with mock.patch('serving.pending_queue.seal', side_effect=RegistryError('injected seal failure')):
            with self.assertRaisesRegex(RegistryError, 'injected seal failure'):
                self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            verify(db)
            self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM publication_pending').fetchone()[0], 0)
        self.next_delta()
        self.assertEqual(publish(*self.args)['new_inputs'], 1)
