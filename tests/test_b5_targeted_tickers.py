"""Targeted ticker proof publication and reader integration."""
import json
import os
import subprocess
import sys
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests.sqlite_support import sqlite_connection
from tests import test_b5_catalog_publication as catalog_tests
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.continuity_catalog import CatalogError, verify_catalog
from serving.query import QueryError
from serving.saved import execute_query_definition
from serving.ticker_proofs import FILE


class TargetedTickerTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def proofpath(self):
        return Path(self.args[2], FILE)

    def test_actual_publication_and_queries_use_selected_groups_only_after_bootstrap(self):
        self.init(); first = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.source.unlink(); self.next_delta()
        import serving.ticker_proofs as proofs
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('publication read baseline rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked), \
             mock.patch('serving.continuity_catalog.ticker_catalog', side_effect=AssertionError('full ticker census reread')), \
             mock.patch('serving.catalog_publication.ticker_catalog', side_effect=AssertionError('full ticker census reread')), \
             mock.patch.object(proofs, 'ticker_catalog', side_effect=AssertionError('full ticker census reread')), \
             mock.patch.object(proofs, 'selected', wraps=proofs.selected) as lookups:
            second = publish(*self.args)
            status = execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
            self.assertGreater(status['summary']['row_count'], 0)
            self.assertGreater(lookups.call_count, 0)
            self.assertTrue(all(call.args[2] in ('ticker', 'identity') for call in lookups.call_args_list))
        self.assertNotEqual(first['generation'], second['generation'])
        with mock.patch('serving.continuity_catalog.ticker_catalog', side_effect=AssertionError('full ticker census reread')), \
             mock.patch.object(proofs.TargetedCatalog, '__getitem__', side_effect=AssertionError('full ticker census materialized')):
            query = execute_query_definition('Q3-instrument', {'symbol':'NEWRELIANCE','series':'EQ'}, self.baseline, self.args[2])
            identity_query = execute_query_definition('Q5-association', {'symbol':'NEWRELIANCE','series':'EQ'}, self.baseline, self.args[2])
            filtered = execute_query_definition('Q4-filter', {'filters': {'symbol':'NEWRELIANCE'}}, self.baseline, self.args[2])
        self.assertTrue(any(row['business_date'] == '2025-03-06' for row in query['rows']))
        self.assertGreater(identity_query['record_count'], 0)
        self.assertGreater(filtered['result_count'], 0)
        self.assertNotEqual(pinned[0].manifest_digest, second['generation'])
        verify_catalog(self.baseline, self.args[2])

    def test_corrupt_or_miskeyed_selected_group_fails_closed(self):
        self.init(); first = publish(*self.args)
        with sqlite_connection(self.proofpath()) as db:
            db.execute("UPDATE rows SET ticker='MISSING' WHERE ticker='RELIANCE'")
        with self.assertRaisesRegex(QueryError, 'ticker lookup group observations mismatch'):
            execute_query_definition('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'}, self.baseline, self.args[2])
        with self.assertRaises(CatalogError):
            verify_catalog(self.baseline, self.args[2])
        self.next_delta()
        with self.assertRaisesRegex(RegistryError, 'ticker lookup group observations mismatch'):
            publish(*self.args)
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].manifest_digest, first['generation'])

    def test_manifest_corruption_and_missing_file_do_not_silently_rebuild(self):
        self.init(); first = publish(*self.args)
        path = self.proofpath()
        with sqlite_connection(path) as db:
            db.execute('UPDATE groups SET row_count=row_count+1 WHERE rowid=(SELECT min(rowid) FROM groups)')
        # The pinned tree remains authoritative for ordinary selected reads.
        self.assertGreater(execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])['summary']['row_count'], 0)
        from serving.composite_binding import ensure_registry_binding
        with self.assertRaisesRegex(QueryError, 'group manifest mismatch'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        with self.assertRaises(CatalogError):
            verify_catalog(self.baseline, self.args[2])
        path.unlink()
        with self.assertRaisesRegex(QueryError, 'proofs missing'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(RegistryError, 'proofs missing'):
            publish(*self.args)
        self.assertFalse(path.exists())
        with sqlite_connection(Path(self.args[1], 'source_registry.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], first['generation'])

    def test_explicit_recovery_restores_only_matching_missing_proofs(self):
        from serving.ticker_proofs import recover
        self.init(); generation = publish(*self.args)['generation']
        self.proofpath().unlink()
        self.source.unlink()
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('recovery read baseline canonical rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            result = recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.assertEqual(result['generation'], generation)
        self.assertTrue(self.proofpath().is_file())
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].manifest_digest, generation)
        # An existing corrupt proof file must never be overwritten by recovery.
        with sqlite_connection(self.proofpath()) as db:
            db.execute('UPDATE groups SET row_count=row_count+1 WHERE rowid=(SELECT min(rowid) FROM groups)')
        before = self.proofpath().read_bytes()
        with self.assertRaises(CatalogError):
            recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.assertEqual(before, self.proofpath().read_bytes())

    def test_recovery_cli_requires_explicit_registry_and_restores_missing_file(self):
        self.init(); generation = publish(*self.args)['generation']
        self.proofpath().unlink()
        cmd = [sys.executable, '-m', 'serving.incremental_registry', '--package', str(self.pkg),
               '--registry', self.args[1], '--state', self.args[2], '--saved-state', self.args[3],
               '--history-state', self.args[4], '--legacy-root', self.args[5]['LEGACY'],
               '--udiff-root', self.args[5]['UDIFF'], 'ticker-proof-recover']
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['data']['generation'], generation)
        self.assertTrue(self.proofpath().is_file())

    def test_format6_upgrade_without_pending_is_atomic(self):
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        payload = dict(selected.payload)
        for key in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides'):
            payload[key] = dict(payload[key].references)
        payload.pop('ticker_proof_tree')
        payload.pop('identity_proof_tree')
        payload.pop('candidate_tree')
        payload.pop('ticker_trees')
        payload['symbol_delta'] = {'observations': payload['symbol_delta']['observations']}
        payload.pop('derived_trees')
        payload.pop('reference_trees')
        payload.pop('index_tree')
        payload.pop('ticker_proofs_binding'); payload.pop('index'); payload.pop('symbol_catalog')
        payload['format'] = 'catalog-composite/6.0'
        text = _json(payload); old = _sha(text)
        path = Path(self.args[1], 'source_registry.sqlite3')
        with sqlite_connection(path) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (old, text))
            db.execute('UPDATE composite_active SET generation=?', (old,))
            db.execute("CREATE TRIGGER block_ticker_proofs BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        self.source.unlink()
        with self.assertRaises(RegistryError):
            publish(*self.args)
        with sqlite_connection(path) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old)
            db.execute('DROP TRIGGER block_ticker_proofs')
        result = publish(*self.args)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(result['migrated_ticker_proofs_generation'], old)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
