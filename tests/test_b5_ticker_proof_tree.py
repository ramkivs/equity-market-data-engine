"""Pinned baseline ticker proofs, including authenticated series ranges."""
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest import mock

from tests.sqlite_support import sqlite_connection
from tests import test_b5_catalog_publication as catalog_tests
from serving.composite_blobs import schema
from serving.composite_binding import ensure_registry_binding
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.query import QueryError
from serving.saved import execute_query_definition
from serving.ticker_proof_tree import TickerProofTree, build, recover


class TickerProofTreeUnitTests(unittest.TestCase):
    def test_balanced_selected_and_complete_series_range(self):
        import serving.ticker_proofs as proofs
        import serving.ticker_proof_tree as tree_module
        db = sqlite3.connect(':memory:'); proof_db = sqlite3.connect(':memory:')
        try:
            schema(db); db.commit(); db.execute('BEGIN'); proof_db.execute('BEGIN')
            groups = {('ticker', 'TICK-%04d' % n, series): (1, 'a' * 64)
                      for n in range(256) for series in ('A', 'EQ', 'Z')}
            groups.update({('identity', 'IDENT-%04d' % n, 'EQ'): (2, 'c' * 64) for n in range(256)})
            meta = {'group_sha256': 'b' * 64, 'group_count': len(groups)}
            with mock.patch.object(proofs, '_manifest', return_value=(meta['group_sha256'], len(groups), groups)):
                header = build(db, proof_db, meta)
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], len(groups))
                tree = TickerProofTree(header, meta, db=db)
                with mock.patch.object(tree_module, '_node', wraps=tree_module._node) as reads:
                    self.assertEqual(tree.ticker_series('TICK-0123'), {'A', 'EQ', 'Z'})
                    self.assertEqual(tree.ticker_series('TICK-NOT-PRESENT'), set())
                    self.assertEqual(tree.ticker_series(''), set())
                    self.assertIsNone(tree.get(('ticker', '', 'EQ')))
                    self.assertEqual(tree.get(('identity', 'IDENT-0001', 'EQ')), (2, 'c' * 64))
                    self.assertIsNone(tree.get(('ticker', 'TICK-0123', 'MISSING')))
                self.assertLess(reads.call_count, 7 * (math.ceil(math.log2(len(groups) + 1)) + 3))
                self.assertEqual(tree.verify(proof_db, meta)['count'], len(groups))
                visited = set()
                original_node = tree_module._node
                def track(conn, digest, *bounds):
                    visited.add(digest)
                    return original_node(conn, digest, *bounds)
                with mock.patch.object(tree_module, '_node', side_effect=track):
                    tree.ticker_series('TICK-0123')
                    tree.get(('ticker', 'TICK-0123', 'EQ'))
                other = next(digest for digest, in db.execute('SELECT digest FROM composite_blobs') if digest not in visited)
                db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('corrupt', other))
                self.assertEqual(tree.ticker_series('TICK-0123'), {'A', 'EQ', 'Z'})
                self.assertEqual(tree.get(('ticker', 'TICK-0123', 'EQ')), (1, 'a' * 64))
                with self.assertRaisesRegex(ValueError, 'ticker proof tree node corrupt'):
                    tree.verify(proof_db, meta)
        finally:
            db.close(); proof_db.close()


class TickerProofTreePublicationTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v13(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        payload = dict(selected.payload)
        for name in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides',
                     'candidates', 'symbol_delta', 'symbol_catalog', 'index_delta', 'index', 'ticker_proof_tree'):
            payload.pop(name)
        payload['format'] = 'catalog-composite/13.0'
        text = _json(payload); generation = _sha(text)
        with sqlite_connection(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        return generation

    def test_publication_and_series_queries_no_longer_scan_either_manifest(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.source.unlink(); self.next_delta()
        with mock.patch('serving.ticker_proofs._manifest', side_effect=AssertionError('ticker manifest scanned')), \
             mock.patch('serving.continuity_catalog._validated_groups', side_effect=AssertionError('identity manifest scanned')):
            second = publish(*self.args)
            q4 = execute_query_definition('Q4-filter', {'filters': {'symbol':'RELIANCE'}}, self.baseline, self.args[2])
            q5 = execute_query_definition('Q5-association', {'symbol':'INFY','series':'EQ'}, self.baseline, self.args[2])
            missing = execute_query_definition('Q4-filter', {'filters': {'symbol':'NOTPRESENT'}}, self.baseline, self.args[2])
        self.assertEqual(second['new_inputs'], 1)
        self.assertGreater(q4['result_count'], 0)
        self.assertGreater(q5['record_count'], 0)
        self.assertEqual(missing['result_count'], 0)
        self.assertEqual(old[0].manifest_digest, first['generation'])
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(selected[0].payload['ticker_proof_tree'], old[0].payload['ticker_proof_tree'])
        self.assertEqual(ensure_registry_binding(self.baseline, self.args[2], self.args[1])['generation'], second['generation'])

    def test_selected_tree_corruption_fails_closed_and_pointer_unchanged(self):
        self.init(); result = publish(*self.args)
        root = active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['ticker_proof_tree']['root']
        with sqlite_connection(self.dbpath()) as db:
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('corrupt', root))
        with self.assertRaisesRegex(QueryError, 'ticker proof tree node corrupt'):
            execute_query_definition('Q4-filter', {'filters': {'symbol':'RELIANCE'}}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'ticker proof tree node corrupt'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.next_delta()
        with self.assertRaisesRegex(RegistryError, 'ticker proof tree node corrupt'):
            publish(*self.args)
        with sqlite_connection(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])

    def test_v13_migration_is_atomic_and_preserves_pinned_reader(self):
        self.init(); publish(*self.args); old_generation = self.to_v13()
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        before = execute_query_definition('Q4-filter', {'filters': {'symbol':'RELIANCE'}}, self.baseline, self.args[2], composite=old)
        self.source.unlink(); self.next_delta()
        with sqlite_connection(self.dbpath()) as db:
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER stop_ticker_proof BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read historical canonical rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite_connection(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_generation)
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], count)
                db.execute('DROP TRIGGER stop_ticker_proof')
            result = publish(*self.args)
        self.assertEqual(result['migrated_ticker_proof_tree_generation'], old_generation)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(execute_query_definition('Q4-filter', {'filters': {'symbol':'RELIANCE'}}, self.baseline, self.args[2], composite=old), before)

    def test_v13_migrates_without_pending_and_rejects_corrupt_manifest(self):
        from serving.ticker_proofs import FILE
        self.init(); publish(*self.args); old = self.to_v13(); self.source.unlink()
        proofpath = Path(self.args[2], FILE)
        with sqlite_connection(proofpath) as db:
            value = db.execute('SELECT row_count FROM groups WHERE rowid=(SELECT min(rowid) FROM groups)').fetchone()[0]
            db.execute('UPDATE groups SET row_count=row_count+1 WHERE rowid=(SELECT min(rowid) FROM groups)')
        with self.assertRaisesRegex(ValueError, 'group manifest mismatch'):
            publish(*self.args)
        with sqlite_connection(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old)
        with sqlite_connection(proofpath) as db:
            db.execute('UPDATE groups SET row_count=? WHERE rowid=(SELECT min(rowid) FROM groups)', (value,))
        result = publish(*self.args)
        self.assertEqual(result['migrated_ticker_proof_tree_generation'], old)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_explicit_recovery_restores_only_missing_matching_nodes(self):
        self.init(); result = publish(*self.args)
        root = active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['ticker_proof_tree']['root']
        with sqlite_connection(self.dbpath()) as db:
            original = db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone()[0]
            db.execute('DELETE FROM composite_blobs WHERE digest=?', (root,))
        self.source.unlink()
        path = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('proof recovery read historical rows')
            return path(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            outcome = recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.assertEqual(outcome['generation'], result['generation'])
        with sqlite_connection(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone()[0], original)
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('corrupt', root))
        with self.assertRaisesRegex(ValueError, 'collision or corruption'):
            recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        with sqlite_connection(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone()[0], 'corrupt')
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])

    def test_recovery_refuses_changed_group_manifest_and_rolls_back(self):
        from serving.ticker_proofs import FILE
        self.init(); result = publish(*self.args)
        root = active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['ticker_proof_tree']['root']
        with sqlite_connection(self.dbpath()) as db:
            db.execute('DELETE FROM composite_blobs WHERE digest=?', (root,))
        with sqlite_connection(Path(self.args[2], FILE)) as db:
            db.execute('UPDATE groups SET row_count=row_count+1 WHERE rowid=(SELECT min(rowid) FROM groups)')
        with self.assertRaisesRegex(ValueError, 'group manifest mismatch'):
            recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        with sqlite_connection(self.dbpath()) as db:
            self.assertIsNone(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone())
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])

    def test_malformed_binding_rejected_at_selection_and_publication(self):
        self.init(); publish(*self.args)
        with sqlite_connection(self.dbpath()) as db:
            text = db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0]
            payload = json.loads(text); payload['ticker_proof_tree']['count'] += 1
            text = _json(payload); generation = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        with self.assertRaisesRegex(QueryError, 'ticker proof tree binding'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(ValueError, 'ticker proof tree binding'):
            publish(*self.args)

    def test_recovery_cli_for_missing_tree_node(self):
        self.init(); result = publish(*self.args)
        root = active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['ticker_proof_tree']['root']
        with sqlite_connection(self.dbpath()) as db:
            db.execute('DELETE FROM composite_blobs WHERE digest=?', (root,))
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-m', 'serving.incremental_registry', '--package', str(self.pkg),
                   '--registry', self.args[1], '--state', self.args[2], '--saved-state', self.args[3],
                   '--history-state', self.args[4], '--legacy-root', self.args[5]['LEGACY'],
                   '--udiff-root', self.args[5]['UDIFF'], 'ticker-proof-tree-recover']
        proc = subprocess.run(command, env=env, text=True, capture_output=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['data']['generation'], result['generation'])
