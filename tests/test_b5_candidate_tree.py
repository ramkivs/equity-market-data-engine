"""Format-12 ordered candidate tree, migration and rollback tests."""
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.candidate_tree import CandidateTree, empty, materialize
from serving.composite_blobs import schema
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.query import QueryError
from serving.saved import execute_query_definition


class CandidateTreeUnitTests(unittest.TestCase):
    def test_order_and_prior_roots_are_preserved(self):
        db = sqlite3.connect(':memory:')
        try:
            schema(db); header = empty(); tree = CandidateTree(db, header)
            records = [{'name': 'item-%02d' % n} for n in range(20)]
            for item in records[:10]:
                tree.append(item)
            prior = dict(header)
            for item in records[10:]:
                tree.append(item)
            self.assertEqual(materialize(db, prior), records[:10])
            self.assertEqual(materialize(db, header), records)
            self.assertEqual(len(tree), 20)
            with self.assertRaisesRegex(ValueError, 'count mismatch'):
                materialize(db, dict(header, count=19))
        finally:
            db.close()


class CandidateTreePublicationTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v11(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        payload = dict(selected[0].payload)
        for name in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides', 'candidate_tree', 'symbol_catalog', 'symbol_delta', 'index_delta', 'index'):
            payload.pop(name)
        payload['format'] = 'catalog-composite/11.0'
        text = _json(payload); digest = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (digest, text))
            db.execute('UPDATE composite_active SET generation=?', (digest,))
        return digest

    def test_publication_appends_without_materializing_prior_candidates(self):
        self.init(); first = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        records = list(pinned[0].payload['candidates'])
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
        self.assertNotIn('candidates', payload)
        self.assertEqual(payload['candidate_tree']['count'], 1)
        self.source.unlink(); self.next_delta()
        import serving.persistent_index_map as trie
        with mock.patch.object(trie, 'entries', side_effect=AssertionError('prior tree scanned')), \
             mock.patch('serving.candidate_tree.materialize', side_effect=AssertionError('prior candidates materialized')):
            second = publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(pinned[0].payload['candidates'], records)
        self.assertEqual(selected[0].payload['candidates'][:1], records)
        self.assertEqual(len(selected[0].payload['candidates']), 2)
        self.assertNotEqual(first['generation'], second['generation'])
        q9 = execute_query_definition('Q9-archive-inventory', {}, self.baseline, self.args[2])
        self.assertEqual(sum(a['source_scope'].startswith('incremental') for a in q9['archives']), 2)

    def test_corrupt_candidate_tree_blocks_selection_and_publication(self):
        self.init(); result = publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        root = selected[0].payload['candidate_tree']['root']
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', root))
        with self.assertRaisesRegex(QueryError, 'candidate tree invalid'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        self.next_delta()
        with self.assertRaisesRegex(RegistryError, 'tree node corrupt'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], result['generation'])
            self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)

    def test_v11_migration_pending_rollback_retry_and_pinned_reader(self):
        self.init(); publish(*self.args); old_id = self.to_v11()
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        records = list(pinned[0].payload['candidates'])
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER stop_candidate_tree BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
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
                db.execute('DROP TRIGGER stop_candidate_tree')
            result = publish(*self.args)
        self.assertEqual(result['migrated_candidates_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(pinned[0].payload['candidates'], records)
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['candidates'][:1], records)

    def test_v11_without_pending_preserves_queries(self):
        self.init(); publish(*self.args); old_id = self.to_v11()
        params = {'symbol': 'RELIANCE', 'series': 'EQ'}
        before = execute_query_definition('Q3-instrument', params, self.baseline, self.args[2])
        self.source.unlink(); result = publish(*self.args)
        after = execute_query_definition('Q3-instrument', params, self.baseline, self.args[2])
        self.assertEqual(result['migrated_candidates_generation'], old_id)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(_json(before).replace(old_id, result['generation']), _json(after))
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_v11_migration_refuses_mismatched_accepted_data(self):
        self.init(); publish(*self.args); old_id = self.to_v11()
        with sqlite3.connect(self.dbpath()) as db:
            text = db.execute("SELECT record FROM accepted WHERE file_name='new.zip'").fetchone()[0]
            record = json.loads(text); record['rows_sha256'] = '0' * 64
            db.execute("UPDATE accepted SET record=? WHERE file_name='new.zip'", (_json(record),))
        with self.assertRaisesRegex(RegistryError, 'candidate migration accepted input mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)

    def test_v11_migration_refuses_corrupt_index_tree(self):
        self.init(); publish(*self.args); old_id = self.to_v11()
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (old_id,)).fetchone()[0])
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', payload['index_tree']['root']))
        with self.assertRaisesRegex(RegistryError, 'tree node corrupt'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)
