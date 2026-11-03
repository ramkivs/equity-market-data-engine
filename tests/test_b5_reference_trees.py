"""Format-9 immutable delta and evidence reference-tree publication."""
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


class ReferenceTreePublicationTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v8(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        payload = dict(selected[0].payload)
        for name in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides'):
            payload[name] = dict(payload[name].references)
        payload.pop('identity_proof_tree')
        payload.pop('candidate_tree')
        payload.pop('ticker_trees')
        payload['symbol_delta'] = {'observations': payload['symbol_delta']['observations']}
        payload.pop('derived_trees')
        payload.pop('reference_trees'); payload.pop('index_delta'); payload.pop('index'); payload.pop('symbol_catalog')
        payload['format'] = 'catalog-composite/8.0'
        text = _json(payload); generation = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        return generation

    def test_roots_are_pinned_and_old_references_not_serialized(self):
        self.init(); first = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        source, rows = next(iter(pinned[0].payload['delta'].items()))
        with sqlite3.connect(self.dbpath()) as db:
            stored = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
        self.assertNotIn('delta', stored); self.assertNotIn('evidence', stored)
        self.assertEqual(stored['reference_trees']['delta']['count'], 1)
        self.source.unlink(); self.next_delta()
        import serving.persistent_index_map as trie
        with mock.patch.object(trie, 'entries', side_effect=AssertionError('old tree fully traversed')):
            second = publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(pinned[0].payload['delta'][source], rows)
        self.assertEqual(len(selected[0].payload['delta']), 2)
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertNotEqual(stored['reference_trees']['delta']['root'], selected[0].payload['reference_trees']['delta']['root'])

    def test_corrupt_reference_root_fails_closed_and_preserves_active_pointer(self):
        for name in ('delta', 'evidence'):
            with self.subTest(name=name):
                # Each subtest needs a separate fixture.
                if name == 'evidence':
                    self.tearDown(); self.setUp()
                self.init(); result = publish(*self.args)
                selected = active_snapshot(self.baseline, self.args[1], self.args[2])
                root = selected[0].payload['reference_trees'][name]['root']
                with sqlite3.connect(self.dbpath()) as db:
                    db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', root))
                with self.assertRaisesRegex(QueryError, 'blob references invalid'):
                    execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
                self.next_delta()
                with self.assertRaisesRegex(RegistryError, 'tree node corrupt'):
                    publish(*self.args)
                with sqlite3.connect(self.dbpath()) as db:
                    self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])
                    self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)

    def test_missing_blob_table_reports_unavailable_not_sqlite_error(self):
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('ALTER TABLE composite_blobs RENAME TO damaged_composite_blobs')
        with self.assertRaisesRegex(QueryError, 'candidate tree invalid'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])

    def test_v8_migration_rollback_retry_preserves_pinned_reader(self):
        self.init(); publish(*self.args); old_id = self.to_v8()
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        source, rows = next(iter(pinned[0].payload['delta'].items()))
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER block_references BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read historical canonical rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], count)
                db.execute('DROP TRIGGER block_references')
            result = publish(*self.args)
        self.assertEqual(result['migrated_references_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(pinned[0].payload['delta'][source], rows)
        self.assertEqual(len(active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['delta']), 2)

    def test_v8_without_pending_migrates_once(self):
        self.init(); publish(*self.args); old_id = self.to_v8()
        before = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.source.unlink()
        result = publish(*self.args)
        after = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(result['migrated_references_generation'], old_id)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(before[1], after[1])
        self.assertEqual(dict(before[0].payload['delta']), dict(after[0].payload['delta']))
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
