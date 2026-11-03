"""B5 targeted identity proofs and safe v1 catalog migration."""
import os
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_bootstrap as boot
from serving.continuity_catalog import (CatalogError, FILENAME, FORMAT, LEGACY_FORMAT, open_catalog,
                                        observations_for_identity, upgrade_catalog, verify_catalog)


class CatalogProofTests(unittest.TestCase):
    setUp = boot.CatalogBootstrapTests.setUp
    tearDown = boot.CatalogBootstrapTests.tearDown
    build = boot.CatalogBootstrapTests.build

    def _legacy(self):
        self.build()
        path = Path(self.args[2], FILENAME)
        with sqlite3.connect(path) as db:
            db.execute('DROP TABLE identity_groups')
            db.execute("DELETE FROM meta WHERE key IN ('group_sha256','group_count')")
            db.execute('UPDATE meta SET value=? WHERE key=?', ('"' + LEGACY_FORMAT + '"', 'format'))
        return path

    def test_targeted_lookup_reads_only_selected_rows(self):
        self.build()
        db, meta = open_catalog(self.baseline, self.args[2])
        queries = []
        db.set_trace_callback(queries.append)
        try:
            self.assertEqual(meta['format'], FORMAT)
            with mock.patch.object(type(self.baseline), 'path', side_effect=AssertionError('historical row read')):
                result = list(observations_for_identity(db, 'INE002A01018', 'w2'))
                self.assertGreater(len(result), 0)
                self.assertEqual(list(observations_for_identity(db, 'NOT-PRESENT', 'w2')), [])
                self.assertEqual(list(observations_for_identity(db, 'INE123', 'b2')), [])
                self.assertGreater(len(list(observations_for_identity(db, 'INE123', 'w2'))), 0)
            reads = [q.lower() for q in queries if 'from observations' in q.lower()]
            self.assertTrue(reads)
            self.assertTrue(all('where w2_identity=' in q or 'where b2_identity=' in q for q in reads), reads)
        finally:
            db.close()

    def test_pinned_manifest_reused_only_in_its_open_read_transaction(self):
        import serving.continuity_catalog as catalog
        self.build()
        db, meta = open_catalog(self.baseline, self.args[2])
        other, _ = open_catalog(self.baseline, self.args[2])
        try:
            with self.assertRaisesRegex(CatalogError, 'requires the bound read transaction'):
                catalog._pin_identity_manifest(db, meta)
            db.execute('BEGIN'); other.execute('BEGIN')
            with mock.patch.object(catalog, '_validated_groups', wraps=catalog._validated_groups) as validate:
                pinned = catalog._pin_identity_manifest(db, meta)
                self.assertGreater(len(list(observations_for_identity(db, 'INE002A01018', 'w2', pinned_groups=pinned))), 0)
                self.assertGreater(len(list(observations_for_identity(db, 'INE002A01018', 'b2', pinned_groups=pinned))), 0)
                self.assertEqual(list(observations_for_identity(db, 'MISSING', 'w2', pinned_groups=pinned)), [])
                self.assertEqual(validate.call_count, 1)
            with self.assertRaisesRegex(CatalogError, 'existing read transaction'):
                list(observations_for_identity(other, 'INE002A01018', 'w2', pinned_groups=pinned))
            db.rollback()
            with self.assertRaisesRegex(CatalogError, 'existing read transaction'):
                list(observations_for_identity(db, 'INE002A01018', 'w2', pinned_groups=pinned))
        finally:
            db.close(); other.close()

    def test_miskeyed_row_cannot_disappear_silently(self):
        self.build()
        path = Path(self.args[2], FILENAME)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE observations SET w2_identity='HIDDEN' WHERE ordinal=(SELECT min(ordinal) FROM observations WHERE w2_identity='INE002A01018')")
        db, _ = open_catalog(self.baseline, self.args[2])
        try:
            with self.assertRaisesRegex(CatalogError, 'group observations mismatch'):
                list(observations_for_identity(db, 'INE002A01018'))
            with self.assertRaisesRegex(CatalogError, '(group observations mismatch|observation/index mismatch)'):
                list(observations_for_identity(db, 'HIDDEN'))
        finally:
            db.close()
        with self.assertRaises(CatalogError):
            verify_catalog(self.baseline, self.args[2])

    def test_manifest_and_selected_projection_corruption_fail_closed(self):
        self.build()
        path = Path(self.args[2], FILENAME)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE identity_groups SET row_count=row_count+1 WHERE kind='w2' AND identity='INE002A01018'")
        db, _ = open_catalog(self.baseline, self.args[2])
        try:
            with self.assertRaisesRegex(CatalogError, 'manifest mismatch'):
                list(observations_for_identity(db, 'INE002A01018'))
        finally:
            db.close()

    def test_v1_migration_is_transactional_and_does_not_read_baseline(self):
        self._legacy()
        db, _ = open_catalog(self.baseline, self.args[2])
        try:
            with self.assertRaisesRegex(CatalogError, 'upgrade catalog first'):
                list(observations_for_identity(db, 'INE002A01018'))
        finally:
            db.close()
        with mock.patch.object(type(self.baseline), 'path', side_effect=AssertionError('baseline was reread')):
            report = upgrade_catalog(self.baseline, self.args[2])
            self.assertEqual(report['status'], 'UPGRADED')
            self.assertEqual(verify_catalog(self.baseline, self.args[2])['format'], FORMAT)
            self.assertEqual(upgrade_catalog(self.baseline, self.args[2])['status'], 'ALREADY-CURRENT')
        db, _ = open_catalog(self.baseline, self.args[2])
        try:
            self.assertGreater(len(list(observations_for_identity(db, 'INE002A01018'))), 0)
        finally:
            db.close()

    def test_interrupted_migration_rolls_back_and_retries(self):
        path = self._legacy()
        import serving.continuity_catalog as mod
        original = mod._create_groups
        def fail(db):
            original(db)
            raise RuntimeError('simulated interruption')
        with mock.patch.object(mod, '_create_groups', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'simulated interruption'):
                upgrade_catalog(self.baseline, self.args[2])
        with sqlite3.connect(path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='identity_groups'").fetchone())
        self.assertEqual(verify_catalog(self.baseline, self.args[2])['format'], LEGACY_FORMAT)
        self.assertEqual(upgrade_catalog(self.baseline, self.args[2])['status'], 'UPGRADED')

    def test_legacy_corruption_is_not_upgraded_or_replaced(self):
        path = self._legacy()
        with sqlite3.connect(path) as db:
            db.execute("UPDATE observations SET raw_symbol='corrupted' WHERE ordinal=1")
        with self.assertRaises(CatalogError):
            upgrade_catalog(self.baseline, self.args[2])
        with sqlite3.connect(path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='identity_groups'").fetchone())

    def test_abrupt_process_exit_during_upgrade_rolls_back(self):
        import subprocess, sys
        path = self._legacy()
        code = r"""
import os,sys
from serving.baseline import open_baseline
import serving.continuity_catalog as c
base=open_baseline(sys.argv[1], verify_files=False)
original=c._create_groups
def die(db):
    original(db)
    os._exit(47)
c._create_groups=die
c.upgrade_catalog(base,sys.argv[2])
"""
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-c', code, str(self.pkg), self.args[2]], env=env,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 47, proc.stderr)
        with sqlite3.connect(path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='identity_groups'").fetchone())
        self.assertEqual(verify_catalog(self.baseline, self.args[2])['format'], LEGACY_FORMAT)
        self.assertEqual(upgrade_catalog(self.baseline, self.args[2])['status'], 'UPGRADED')

    def test_catalog_upgrade_cli(self):
        import subprocess, sys
        self._legacy()
        args = ['--package', str(self.pkg), '--registry', self.args[1], '--state', self.args[2],
                '--saved-state', self.args[3], '--history-state', self.args[4],
                '--legacy-root', self.args[5]['LEGACY'], '--udiff-root', self.args[5]['UDIFF']]
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-m', 'serving.incremental_registry', *args, 'catalog-upgrade'],
                              env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('"UPGRADED"', proc.stdout)

    def test_group_lookup_uses_one_pinned_sqlite_snapshot(self):
        self.build()
        path = Path(self.args[2], FILENAME)
        with sqlite3.connect(path) as writer:
            self.assertEqual(writer.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        reader, _ = open_catalog(self.baseline, self.args[2])
        try:
            reader.execute('BEGIN')
            reader.execute('SELECT count(*) FROM identity_groups').fetchone()  # establish snapshot
            with sqlite3.connect(path) as writer:
                writer.execute("UPDATE identity_groups SET row_count=row_count+1 WHERE kind='w2' AND identity='INE002A01018'")
            self.assertGreater(len(list(observations_for_identity(reader, 'INE002A01018'))), 0)
            reader.rollback()
            with self.assertRaisesRegex(CatalogError, 'manifest mismatch'):
                list(observations_for_identity(reader, 'INE002A01018'))
        finally:
            reader.close()
