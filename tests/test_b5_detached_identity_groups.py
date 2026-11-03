"""Incremental identity group blobs and migration on disposable fixtures."""
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.saved import execute_query_definition
from serving.query import QueryError


class IdentityGroupTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v2(self):
        selected, _ = active_snapshot(self.baseline, self.args[1], self.args[2])
        p = dict(selected.payload)
        p['delta'] = dict(p['delta'].references); p['evidence'] = dict(p['evidence'].references)
        old_hashes = set(p['w2_delta'].references.values()) | set(p['b2_delta'].references.values())
        p['w2_delta'] = dict(p['w2_delta']); p['b2_delta'] = dict(p['b2_delta'])
        p['w2_overrides'] = dict(p['w2_overrides']); p['b3_overrides'] = dict(p['b3_overrides'])
        p.pop('candidate_tree')
        p.pop('ticker_trees')
        p['symbol_delta'] = {'observations': p['symbol_delta']['observations']}
        p.pop('derived_trees')
        p.pop('reference_trees')
        p.pop('index_tree')
        p.pop('ticker_proofs_binding')
        p['symbol_catalog'] = {'observations': p['symbol_catalog']['observations']}
        p.pop('index_delta')
        p.pop('symbol_delta')
        p['format'] = 'catalog-composite/2.0'
        text = _json(p); old = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DELETE FROM composite_generations')
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (old, text))
            db.execute('UPDATE composite_active SET generation=?', (old,))
            db.executemany('DELETE FROM composite_blobs WHERE digest=?', [(h,) for h in old_hashes])
        return old

    def test_only_affected_groups_are_loaded_and_old_group_is_pinned(self):
        self.init(); first = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        groups = pinned[0].payload['w2_delta']
        unaffected = 'INE000000006'
        before_ref = groups.references[unaffected]; before_rows = groups[unaffected]
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
            self.assertNotIn('w2_delta', payload)
            self.assertGreater(payload['derived_trees']['w2_delta']['count'], 0)
            self.assertNotIn(_json(before_rows), _json(payload))
        self.source.unlink(); self.next_delta()
        import serving.catalog_publication as cp
        with mock.patch.object(cp, 'load_group_from_db', wraps=cp.load_group_from_db) as loaded:
            second = publish(*self.args)
        self.assertNotIn(unaffected, [c.args[2] for c in loaded.call_args_list])
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(selected[0].payload['w2_delta'].references[unaffected], before_ref)
        self.assertEqual(groups[unaffected], before_rows)
        self.assertNotEqual(first['generation'], second['generation'])

    def test_affected_group_corruption_blocks_publication_and_rebinding(self):
        from serving.composite_binding import ensure_registry_binding
        self.init(); first = publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        digest = selected[0].payload['w2_delta'].references['INE002A01018']
        with sqlite3.connect(self.dbpath()) as db:
            original = db.execute('SELECT content FROM composite_blobs WHERE digest=?', (digest,)).fetchone()[0]
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', digest))
        with self.assertRaisesRegex(QueryError, 'blob.*digest mismatch'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.next_delta()
        with self.assertRaisesRegex(RegistryError, 'group blob.*digest mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], first['generation'])
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', (original, digest))
        self.assertEqual(publish(*self.args)['new_inputs'], 1)

    def test_v2_migration_atomic_no_pending_no_baseline_or_archive_reads(self):
        self.init(); publish(*self.args); legacy = self.to_v2()
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        params = {'security_id':'INE002A01018'}
        before = execute_query_definition('Q5-association', params, self.baseline, self.args[2], composite=pinned)
        self.source.unlink()
        with sqlite3.connect(self.dbpath()) as db:
            before_count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER stop_migration BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read baseline rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], before_count)
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], legacy)
                db.execute('DROP TRIGGER stop_migration')
            result = publish(*self.args)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(result['migrated_groups_generation'], legacy)
        after = execute_query_definition('Q5-association', params, self.baseline, self.args[2])
        self.assertEqual(_json(before).replace(legacy, result['generation']), _json(after))
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_v2_migration_with_pending_input_preserves_existing_records(self):
        self.init(); publish(*self.args); legacy = self.to_v2()
        self.source.unlink(); self.next_delta()
        result = publish(*self.args)
        self.assertEqual(result['migrated_groups_generation'], legacy)
        self.assertEqual(result['new_inputs'], 1)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(len(selected[0].payload['candidates']), 2)
        self.assertGreater(len(selected[0].payload['w2_delta']['INE002A01018']), 0)
        q9 = execute_query_definition('Q9-archive-inventory', {}, self.baseline, self.args[2])
        self.assertEqual(sum(item['source_scope'].startswith('incremental') for item in q9['archives']), 2)

    def test_group_reference_schema_invalid_fails_closed(self):
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0])
            payload['derived_trees']['w2_delta']['count'] = -1
            text = _json(payload); digest = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (digest, text))
            db.execute('UPDATE composite_active SET generation=?', (digest,))
        with self.assertRaisesRegex(QueryError, 'reference tree'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(RegistryError, 'reference tree'):
            publish(*self.args)

    def test_v2_migration_refuses_misidentified_projection(self):
        self.init(); publish(*self.args); legacy = self.to_v2()
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (legacy,)).fetchone()[0])
            group = payload['w2_delta']['INE002A01018']
            group[0][1]['source_values']['security_isin'] = 'INCORRECT'
            text = _json(payload); bad = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (bad, text))
            db.execute('UPDATE composite_active SET generation=?', (bad,))
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
        with self.assertRaisesRegex(RegistryError, 'group key mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], bad)
            self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], count)
