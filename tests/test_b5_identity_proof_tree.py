"""Compact, generation-pinned baseline identity-group search proofs."""
import json
import math
import os
import subprocess
import sys
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.composite_binding import ensure_registry_binding
from serving.composite_blobs import schema
from serving.continuity_catalog import open_catalog
from serving.identity_proof_tree import IdentityProofTree, build
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.query import QueryError
from serving.saved import execute_query_definition


class IdentityTreeUnitTests(unittest.TestCase):
    def test_balanced_proof_is_one_node_per_group_and_logarithmic_lookup(self):
        import serving.continuity_catalog as catalog
        import serving.identity_proof_tree as proof
        db = sqlite3.connect(':memory:'); cat = sqlite3.connect(':memory:')
        try:
            schema(db); db.commit(); db.execute('BEGIN'); cat.execute('BEGIN')
            groups = {('w2', 'IDENTITY-%04d' % n): (n + 1, 'a' * 64) for n in range(511)}
            meta = {'group_count': len(groups), 'group_sha256': 'b' * 64}
            with mock.patch.object(catalog, '_metadata', return_value=meta), \
                 mock.patch.object(catalog, '_validated_groups', return_value=groups):
                header = build(db, cat, meta)
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], len(groups))
                tree = IdentityProofTree(header, meta, db=db)
                with mock.patch.object(proof, '_node', wraps=proof._node) as reads:
                    self.assertEqual(tree.get(('w2', 'IDENTITY-0500')), groups[('w2', 'IDENTITY-0500')])
                    self.assertIsNone(tree.get(('b2', 'NOPE')))
                self.assertLessEqual(reads.call_count, 2 * (math.ceil(math.log2(len(groups) + 1)) + 1))
                self.assertEqual(tree.verify(cat, meta)['count'], len(groups))
        finally:
            db.close(); cat.close()


class IdentityTreePublicationTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v12(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        p = dict(selected[0].payload)
        for name in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides',
                     'candidates', 'symbol_delta', 'symbol_catalog', 'index_delta', 'index', 'identity_proof_tree'):
            p.pop(name)
        p['format'] = 'catalog-composite/12.0'
        text = _json(p); generation = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        return generation

    def test_normal_publish_and_unaffected_q5_do_not_scan_identity_manifest(self):
        self.init(); first = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.source.unlink(); self.next_delta()
        import serving.continuity_catalog as catalog
        with mock.patch.object(catalog, '_validated_groups', side_effect=AssertionError('baseline identity manifest scan')):
            result = publish(*self.args)
            query = execute_query_definition('Q5-association', {'security_id':'INE009A01021'}, self.baseline, self.args[2])
        self.assertEqual(result['new_inputs'], 1)
        self.assertGreater(query['record_count'], 0)
        self.assertTrue(query['records'][0]['serving']['continuity'])
        self.assertEqual(pinned[0].manifest_digest, first['generation'])
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(selected[0].payload['identity_proof_tree'], pinned[0].payload['identity_proof_tree'])
        facts = ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.assertEqual(facts['generation'], result['generation'])

    def test_corrupt_root_blocks_selected_identity_and_affected_publication(self):
        self.init(); first = publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        root = selected[0].payload['identity_proof_tree']['root']
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', root))
        with self.assertRaisesRegex(QueryError, 'identity proof tree node corrupt'):
            execute_query_definition('Q5-association', {'security_id':'INE009A01021'}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'identity proof tree node corrupt'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.next_delta()
        with self.assertRaisesRegex(RegistryError, 'identity proof tree node corrupt'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], first['generation'])

    def test_unrelated_node_is_deferred_but_explicit_binding_checks_all(self):
        import serving.identity_proof_tree as proof
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        root = selected[0].payload['identity_proof_tree']['root']
        target = ('b2', 'INE009A01021')
        with sqlite3.connect(self.dbpath()) as db:
            path = set(); digest = root
            while digest is not None:
                path.add(digest)
                node, key = proof._node(db, digest)
                if key == target:
                    break
                digest = node['left'] if target < key else node['right']
            self.assertIsNotNone(digest)
            stack = [root]; other = None
            while stack:
                item = stack.pop(); node, _ = proof._node(db, item)
                if item not in path:
                    other = item; break
                stack.extend(child for child in (node['left'], node['right']) if child)
            self.assertIsNotNone(other)
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', other))
        query = execute_query_definition('Q5-association', {'security_id':target[1]}, self.baseline, self.args[2])
        self.assertGreater(query['record_count'], 0)
        with self.assertRaisesRegex(QueryError, 'identity proof tree node corrupt'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])

    def test_malformed_proof_binding_fails_selection_and_publication(self):
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            text = db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0]
            payload = json.loads(text); payload['identity_proof_tree']['count'] += 1
            text = _json(payload); digest = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (digest, text))
            db.execute('UPDATE composite_active SET generation=?', (digest,))
        with self.assertRaisesRegex(QueryError, 'identity proof tree binding'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(RegistryError, 'identity proof tree binding'):
            publish(*self.args)

    def test_missing_selected_catalog_row_is_detected_by_pinned_tree(self):
        from serving.continuity_catalog import FILENAME
        self.init(); publish(*self.args)
        path = Path(self.args[2], FILENAME)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE observations SET b2_identity='HIDDEN' WHERE ordinal=(SELECT min(ordinal) FROM observations WHERE b2_identity='INE009A01021')")
        with self.assertRaisesRegex(QueryError, 'group observations mismatch'):
            execute_query_definition('Q5-association', {'security_id':'INE009A01021'}, self.baseline, self.args[2])
        from serving.continuity_catalog import verify_catalog, CatalogError
        with self.assertRaises(CatalogError):
            verify_catalog(self.baseline, self.args[2])

    def test_explicit_recovery_restores_missing_nodes_but_never_replaces_corruption(self):
        from serving.identity_proof_tree import recover
        self.init(); result = publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        root = selected[0].payload['identity_proof_tree']['root']
        with sqlite3.connect(self.dbpath()) as db:
            original = db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone()[0]
            db.execute('DELETE FROM composite_blobs WHERE digest=?', (root,))
        self.source.unlink()
        path = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('identity proof recovery read historical rows')
            return path(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            outcome = recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.assertEqual(outcome['generation'], result['generation'])
        self.assertGreater(execute_query_definition('Q5-association', {'security_id':'INE009A01021'}, self.baseline, self.args[2])['record_count'], 0)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone()[0], original)
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('corrupt', root))
        with self.assertRaisesRegex(ValueError, 'collision or corruption'):
            recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone()[0], 'corrupt')
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])

    def test_recovery_cli_uses_explicit_existing_registry(self):
        self.init(); result = publish(*self.args)
        root = active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['identity_proof_tree']['root']
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DELETE FROM composite_blobs WHERE digest=?', (root,))
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-m', 'serving.incremental_registry', '--package', str(self.pkg),
                   '--registry', self.args[1], '--state', self.args[2], '--saved-state', self.args[3],
                   '--history-state', self.args[4], '--legacy-root', self.args[5]['LEGACY'],
                   '--udiff-root', self.args[5]['UDIFF'], 'identity-proof-recover']
        proc = subprocess.run(command, env=env, text=True, capture_output=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['data']['generation'], result['generation'])

    def test_recovery_refuses_changed_catalog_manifest_and_rolls_back(self):
        from serving.continuity_catalog import FILENAME
        from serving.identity_proof_tree import recover
        self.init(); result = publish(*self.args)
        root = active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['identity_proof_tree']['root']
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DELETE FROM composite_blobs WHERE digest=?', (root,))
        with sqlite3.connect(Path(self.args[2], FILENAME)) as db:
            db.execute('UPDATE identity_groups SET row_count=row_count+1 WHERE rowid=(SELECT min(rowid) FROM identity_groups)')
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        with sqlite3.connect(self.dbpath()) as db:
            self.assertIsNone(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone())
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])

    def test_v12_migration_rollback_retry_without_historical_or_old_sources(self):
        self.init(); publish(*self.args); old = self.to_v12()
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        prior = execute_query_definition('Q5-association', {'security_id':'INE009A01021'}, self.baseline, self.args[2], composite=pinned)
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER stop_identity_tree BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read historical canonical rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old)
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], count)
                db.execute('DROP TRIGGER stop_identity_tree')
            result = publish(*self.args)
        self.assertEqual(result['migrated_identity_proofs_generation'], old)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(execute_query_definition('Q5-association', {'security_id':'INE009A01021'}, self.baseline, self.args[2], composite=pinned), prior)

    def test_v12_migration_without_pending_and_manifest_corruption(self):
        from serving.continuity_catalog import FILENAME
        self.init(); publish(*self.args); old = self.to_v12(); self.source.unlink()
        path = Path(self.args[2], FILENAME)
        with sqlite3.connect(path) as db:
            original = db.execute('SELECT row_count FROM identity_groups WHERE rowid=(SELECT min(rowid) FROM identity_groups)').fetchone()[0]
            db.execute('UPDATE identity_groups SET row_count=row_count+1 WHERE rowid=(SELECT min(rowid) FROM identity_groups)')
        with self.assertRaisesRegex(RegistryError, 'manifest mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old)
        with sqlite3.connect(path) as db:
            db.execute('UPDATE identity_groups SET row_count=? WHERE rowid=(SELECT min(rowid) FROM identity_groups)', (original,))
        result = publish(*self.args)
        self.assertEqual(result['migrated_identity_proofs_generation'], old)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
