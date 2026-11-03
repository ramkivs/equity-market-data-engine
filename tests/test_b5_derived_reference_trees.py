"""Format-10 derived reference-tree migration and transactional updates."""
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.query import QueryError
from serving.saved import execute_query_definition
from serving.persistent_index_map import DERIVED_NAMES


class DerivedReferenceTreesTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v9(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        p = dict(selected[0].payload)
        for name in ('delta', 'evidence') + DERIVED_NAMES:
            p[name] = dict(p[name].references)
        p.pop('ticker_proof_tree')
        p.pop('identity_proof_tree')
        p.pop('candidate_tree')
        p.pop('ticker_trees')
        p['symbol_delta'] = {'observations': p['symbol_delta']['observations']}
        p.pop('derived_trees'); p.pop('index_delta'); p.pop('index'); p.pop('symbol_catalog')
        # Format 9 already uses reference trees for rows/evidence.
        p.pop('delta'); p.pop('evidence')
        p['format'] = 'catalog-composite/9.0'
        text = _json(p); digest = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (digest, text))
            db.execute('UPDATE composite_active SET generation=?', (digest,))
        return digest

    def test_updates_changed_identity_paths_and_retains_old_root(self):
        self.init(); first = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        affected, unaffected = 'INE002A01018', 'INE000000006'
        old_ref = pinned[0].payload['w2_delta'].references[affected]
        old_rows = pinned[0].payload['w2_delta'][affected]
        unaffected_ref = pinned[0].payload['w2_delta'].references[unaffected]
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
            for name in DERIVED_NAMES:
                self.assertNotIn(name, payload)
                self.assertGreater(payload['derived_trees'][name]['count'], 0)
        self.source.unlink(); self.next_delta()
        import serving.persistent_index_map as trie
        with mock.patch.object(trie, 'entries', side_effect=AssertionError('prior trie fully scanned')):
            publish(*self.args)
        current = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertNotEqual(current[0].payload['w2_delta'].references[affected], old_ref)
        self.assertEqual(current[0].payload['w2_delta'].references[unaffected], unaffected_ref)
        self.assertEqual(pinned[0].payload['w2_delta'][affected], old_rows)
        self.assertEqual(current[0].payload['derived_trees']['w2_delta']['count'], len(current[0].payload['w2_delta']))

    def test_each_corrupt_tree_fails_selection_and_affected_publication(self):
        for i, name in enumerate(DERIVED_NAMES):
            with self.subTest(name=name):
                if i:
                    self.tearDown(); self.setUp()
                self.init(); result = publish(*self.args)
                selected = active_snapshot(self.baseline, self.args[1], self.args[2])
                root = selected[0].payload['derived_trees'][name]['root']
                with sqlite3.connect(self.dbpath()) as db:
                    db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', root))
                with self.assertRaisesRegex(QueryError, 'blob references invalid'):
                    execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
                self.next_delta()
                with self.assertRaisesRegex(RegistryError, 'tree node corrupt'):
                    publish(*self.args)
                with sqlite3.connect(self.dbpath()) as db:
                    self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])

    def test_v9_migration_with_pending_rollback_and_pinned_reader(self):
        self.init(); publish(*self.args); old_id = self.to_v9()
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        identity = 'INE002A01018'
        old_rows = pinned[0].payload['w2_delta'][identity]
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER stop_migration BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        path = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read historical canonical rows')
            return path(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], count)
                db.execute('DROP TRIGGER stop_migration')
            result = publish(*self.args)
        self.assertEqual(result['migrated_derived_references_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(pinned[0].payload['w2_delta'][identity], old_rows)
        self.assertGreater(len(active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['w2_delta'][identity]), len(old_rows))

    def test_v9_migration_without_pending_preserves_queries(self):
        self.init(); publish(*self.args); old_id = self.to_v9()
        params = {'symbol':'NEWRELIANCE', 'series':'EQ'}
        before = execute_query_definition('Q5-association', params, self.baseline, self.args[2])
        self.source.unlink()
        result = publish(*self.args)
        after = execute_query_definition('Q5-association', params, self.baseline, self.args[2])
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(result['migrated_derived_references_generation'], old_id)
        self.assertEqual(_json(before).replace(old_id, result['generation']), _json(after))
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
