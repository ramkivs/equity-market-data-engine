"""Explicit registry adoption and missing-binding safeguards on disposable state."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest import mock

from tests.sqlite_support import sqlite_connection
from tests import test_b5_catalog_publication as catalog_tests
from serving.composite_binding import ensure_registry_binding, read_binding
from serving.incremental_publication import publish
from serving.query import QueryError
from serving.saved import execute_query_definition


class RegistryBindingTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def snapshot_registry(self):
        with sqlite_connection(Path(self.args[1], 'source_registry.sqlite3')) as db:
            return {table: db.execute('SELECT * FROM ' + table + ' ORDER BY 1,2').fetchall()
                    for table in ('accepted', 'staged_candidates', 'conflicts', 'composite_generations', 'composite_active')}

    def test_missing_binding_is_detected_and_explicit_repair_preserves_data(self):
        self.init(); generation = publish(*self.args)['generation']; self.next_delta()
        before = self.snapshot_registry()
        binding = Path(self.args[2], 'composite_registry.json')
        binding.unlink()
        with self.assertRaisesRegex(QueryError, 'binding missing'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'binding missing'):
            publish(*self.args)
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('rebinding read historical canonical rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            facts = ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.assertEqual(facts['generation'], generation)
        self.assertEqual(facts['accepted_incremental'], 1)
        self.assertEqual(facts['staged'], 2)
        self.assertEqual(self.snapshot_registry(), before)
        self.assertEqual(read_binding(self.baseline, self.args[2]), self.args[1])
        self.assertEqual(publish(*self.args)['new_inputs'], 1)

    def test_guard_rejects_wrong_registry_and_corruption(self):
        self.init(); publish(*self.args)
        alt = Path(self.tmp.name, 'other-registry'); alt.mkdir()
        shutil.copy2(Path(self.args[1], 'source_registry.sqlite3'), alt / 'source_registry.sqlite3')
        binding = Path(self.args[2], 'composite_registry.json'); binding.unlink()
        with self.assertRaisesRegex(QueryError, 'different registry'):
            ensure_registry_binding(self.baseline, self.args[2], str(alt))
        self.assertFalse(binding.exists())
        guard = Path(self.args[2], 'composite_registry_guard.json')
        original = guard.read_text(); guard.write_text('{invalid')
        with self.assertRaisesRegex(QueryError, 'invalid composite registry binding'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.assertFalse(binding.exists())
        guard.write_text(original)
        ensure_registry_binding(self.baseline, self.args[2], self.args[1])

    def test_explicit_cli_adopts_legacy_registry_and_refuses_damaged_staging(self):
        self.init(); publish(*self.args); self.next_delta()
        # Simulate a pre-binding installation, not removal of a guarded binding.
        Path(self.args[2], 'composite_registry.json').unlink()
        Path(self.args[2], 'composite_registry_guard.json').unlink()
        before = self.snapshot_registry()
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        cmd = [sys.executable, '-m', 'serving.incremental_registry', '--package', str(self.pkg),
               '--registry', self.args[1], '--state', self.args[2], '--saved-state', self.args[3],
               '--history-state', self.args[4], '--legacy-root', self.args[5]['LEGACY'],
               '--udiff-root', self.args[5]['UDIFF'], 'bind']
        path = Path(self.args[1], 'source_registry.sqlite3')
        with sqlite_connection(path) as db:
            text = db.execute("SELECT rows FROM staged_candidates WHERE file_name='later.zip'").fetchone()[0]
            db.execute("UPDATE staged_candidates SET rows='broken' WHERE file_name='later.zip'")
        failed = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=20)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('pending index is missing or unsealed', json.loads(failed.stdout)['detail'])
        repair = cmd[:-1] + ['pending-index-recover']
        damaged_repair = subprocess.run(repair, env=env, text=True, capture_output=True, timeout=20)
        self.assertNotEqual(damaged_repair.returncode, 0)
        self.assertIn('digest mismatch', json.loads(damaged_repair.stdout)['detail'])
        self.assertFalse(Path(self.args[2], 'composite_registry.json').exists())
        with sqlite_connection(path) as db:
            db.execute("UPDATE staged_candidates SET rows=? WHERE file_name='later.zip'", (text,))
        repaired = subprocess.run(repair, env=env, text=True, capture_output=True, timeout=20)
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        result = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['staged'], 2)
        self.assertEqual(self.snapshot_registry(), before)

    def test_interrupted_creation_fails_closed_and_can_be_repaired(self):
        self.init(); publish(*self.args)
        binding = Path(self.args[2], 'composite_registry.json')
        guard = Path(self.args[2], 'composite_registry_guard.json')
        binding.unlink(); guard.unlink()  # a pre-guard legacy state
        real_open = os.open
        def interrupted(path, flags, *args, **kwargs):
            if str(path) == str(binding) and flags & os.O_CREAT:
                raise OSError('simulated interruption')
            return real_open(path, flags, *args, **kwargs)
        with mock.patch('serving.composite_binding.os.open', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'simulated interruption'):
                ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.assertTrue(guard.exists()); self.assertFalse(binding.exists())
        with self.assertRaisesRegex(QueryError, 'binding missing'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.assertTrue(binding.exists())

    def test_missing_and_invalid_registry_are_reported_never_created(self):
        self.init()
        missing = str(Path(self.tmp.name, 'missing'))
        with self.assertRaisesRegex(QueryError, 'registry missing'):
            ensure_registry_binding(self.baseline, self.args[2], missing)
        self.assertFalse(Path(missing).exists())
        with sqlite_connection(Path(self.args[1], 'source_registry.sqlite3')) as db:
            db.execute('DELETE FROM accepted WHERE rowid=(SELECT min(rowid) FROM accepted)')
        with self.assertRaisesRegex(QueryError, 'baseline accepted records missing'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])
