"""Detached W2/B3 overrides, migration and snapshot integrity tests."""
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


class DetachedOverrideTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v3(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        payload = dict(selected.payload)
        for key in ('delta', 'evidence', 'w2_delta', 'b2_delta'):
            payload[key] = dict(payload[key].references)
        hashes = set(payload['w2_overrides'].references.values()) | set(payload['b3_overrides'].references.values())
        for key in ('w2_overrides', 'b3_overrides'):
            payload[key] = dict(payload[key])
        payload.pop('derived_trees')
        payload.pop('reference_trees')
        payload.pop('index_tree')
        payload.pop('ticker_proofs_binding')
        payload['symbol_catalog'] = {'observations': payload['symbol_catalog']['observations']}
        payload.pop('index_delta')
        payload.pop('symbol_delta')
        payload['format'] = 'catalog-composite/3.0'
        text = _json(payload); generation = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DELETE FROM composite_generations')
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
            db.executemany('DELETE FROM composite_blobs WHERE digest=?', [(h,) for h in hashes])
        return generation

    def test_unaffected_override_remains_unread_and_pinned(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        overrides = old[0].payload['w2_overrides']
        unaffected = 'INE000000006'
        ref = overrides.references[unaffected]; value = overrides[unaffected]
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
            self.assertNotIn('w2_overrides', payload)
            self.assertGreater(payload['derived_trees']['w2_overrides']['count'], 0)
            self.assertNotIn(_json(value), _json(payload))
        self.source.unlink(); self.next_delta()
        import serving.catalog_publication as cp
        with mock.patch.object(cp, 'put_blob', wraps=cp.put_blob) as put:
            publish(*self.args)
        self.assertNotIn(ref, [call.args[2] for call in put.call_args_list])
        new = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(new[0].payload['w2_overrides'].references[unaffected], ref)
        self.assertEqual(overrides[unaffected], value)

    def test_corrupt_selected_override_fails_closed(self):
        from serving.composite_binding import ensure_registry_binding
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        digest = selected.payload['w2_overrides'].references['INE002A01018']
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', digest))
        with self.assertRaisesRegex(QueryError, 'blob.*digest mismatch'):
            execute_query_definition('Q5-association', {'security_id':'INE002A01018'}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'blob.*digest mismatch'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])
        self.assertGreater(execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])['summary']['row_count'], 0)

    def test_v3_migration_atomic_with_pending_without_old_source_or_baseline_rows(self):
        self.init(); publish(*self.args); old_id = self.to_v3()
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        params = {'security_id':'INE002A01018'}
        before = execute_query_definition('Q5-association', params, self.baseline, self.args[2], composite=old)
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER fail_override_switch BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'failure'); END")
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
                db.execute('DROP TRIGGER fail_override_switch')
            result = publish(*self.args)
        self.assertEqual(result['migrated_overrides_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(execute_query_definition('Q5-association', params, self.baseline, self.args[2], composite=old), before)
        self.assertEqual(len(active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['candidates']), 2)

    def test_v3_migration_without_pending_and_invalid_override(self):
        self.init(); publish(*self.args); old_id = self.to_v3(); self.source.unlink()
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (old_id,)).fetchone()[0])
            payload['b3_overrides']['INE002A01018'][0]['security_id'] = 'WRONG'
            text = _json(payload); bad_id = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (bad_id, text))
            db.execute('UPDATE composite_active SET generation=?', (bad_id,))
        with self.assertRaisesRegex(RegistryError, 'override identity mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], bad_id)
            db.execute('UPDATE composite_active SET generation=?', (old_id,))
        result = publish(*self.args)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(result['migrated_overrides_generation'], old_id)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_unaffected_baseline_identity_has_no_delta_group(self):
        self.init(); publish(*self.args)
        result = execute_query_definition('Q5-association', {'security_id':'INE467B01029'}, self.baseline, self.args[2])
        self.assertGreater(result['record_count'], 0)
        self.assertTrue(result['records'][0]['serving']['continuity'])
