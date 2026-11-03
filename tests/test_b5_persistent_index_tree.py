"""Persistent index trie and selected-generation publication integration."""
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.composite_blobs import schema
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.persistent_index_map import insert, lookup, entries, _key_hash
from serving.query import QueryError
from serving.saved import execute_query_definition


class PersistentTrieUnitTests(unittest.TestCase):
    def test_updates_only_changed_path_and_old_root_remains_valid(self):
        db = sqlite3.connect(':memory:')
        try:
            schema(db); root = None
            for n in range(80):
                root = insert(db, root, 'source-%d' % n, {'number': n})
            previous = root
            old = entries(db, previous)
            import serving.persistent_index_map as trie
            with mock.patch.object(trie, '_read', wraps=trie._read) as reads:
                root = insert(db, root, 'additional', {'number': 80})
            self.assertLessEqual(reads.call_count, 64)
            self.assertEqual(lookup(db, previous, 'additional'), None)
            self.assertEqual(lookup(db, root, 'additional'), {'number': 80})
            self.assertEqual(entries(db, previous), old)
            self.assertEqual(len(entries(db, root)), 81)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                insert(db, root, 'additional', {'number': 81})
        finally:
            db.close()

    def test_content_corruption_and_hidden_paths_are_detected(self):
        db = sqlite3.connect(':memory:')
        try:
            schema(db); root = insert(db, None, 'test', {'number': 1})
            node = json.loads(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (root,)).fetchone()[0])
            child = node['children'][_key_hash('test')[0]]
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('corrupt', child))
            with self.assertRaisesRegex(ValueError, 'tree node corrupt'):
                lookup(db, root, 'test')
            with self.assertRaisesRegex(ValueError, 'tree node corrupt'):
                entries(db, root)
        finally:
            db.close()


class PersistentIndexPublicationTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def test_actual_publication_pins_root_and_writes_only_new_path(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        old_index = old[1]
        root = old[0].payload['index_tree']['root']
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
            self.assertNotIn('index_delta', payload)
            self.assertEqual(payload['index_tree']['root'], root)
            self.assertEqual(payload['index_tree']['file_count'], 1)
        self.source.unlink(); self.next_delta()
        import serving.persistent_index_map as trie
        with mock.patch.object(trie, '_read', wraps=trie._read) as reads, \
             mock.patch('serving.catalog_publication.materialize_index_tree', side_effect=AssertionError('prior tree fully scanned')):
            second = publish(*self.args)
        self.assertLessEqual(reads.call_count, 64)
        current = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertNotEqual(current[0].payload['index_tree']['root'], root)
        self.assertEqual(current[0].payload['index_tree']['file_count'], 2)
        self.assertEqual(second['row_count'], current[1]['counts']['row_count'])
        self.assertEqual(old[1], old_index)
        self.assertGreater(current[1]['counts']['row_count'], old[1]['counts']['row_count'])

    def test_corrupt_tree_node_fails_closed_for_reader_and_affected_publish(self):
        self.init(); result = publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        root = selected[0].payload['index_tree']['root']
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', root))
        with self.assertRaisesRegex(QueryError, 'index tree node corrupt'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        self.next_delta()
        with self.assertRaisesRegex(RegistryError, 'index tree node corrupt'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])
            self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)

    def test_v7_migration_rollback_retry_with_pending_and_no_old_sources(self):
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        payload = dict(selected[0].payload)
        for key in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides'):
            payload[key] = dict(payload[key].references)
        payload.pop('index_tree'); payload.pop('index'); payload.pop('symbol_catalog')
        payload['format'] = 'catalog-composite/7.0'
        text = _json(payload); old_id = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (old_id, text))
            db.execute('UPDATE composite_active SET generation=?', (old_id,))
            db.execute("CREATE TRIGGER block_tree_switch BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.source.unlink(); self.next_delta()
        path = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read historical rows')
            return path(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)
                db.execute('DROP TRIGGER block_tree_switch')
            result = publish(*self.args)
        self.assertEqual(result['migrated_index_tree_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertGreater(active_snapshot(self.baseline, self.args[1], self.args[2])[1]['counts']['row_count'], pinned[1]['counts']['row_count'])

    def test_v7_migration_without_pending_is_equivalent(self):
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        payload = dict(selected[0].payload)
        for key in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides'):
            payload[key] = dict(payload[key].references)
        payload.pop('index_tree'); payload.pop('index'); payload.pop('symbol_catalog')
        payload['format'] = 'catalog-composite/7.0'
        text = _json(payload); old_id = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (old_id, text))
            db.execute('UPDATE composite_active SET generation=?', (old_id,))
        before = active_snapshot(self.baseline, self.args[1], self.args[2])[1]
        self.source.unlink()
        result = publish(*self.args)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(result['migrated_index_tree_generation'], old_id)
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[1], before)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
