"""Detached delta blobs: atomic migration, scoped verification and reader pins."""
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.saved import execute_query_definition
from serving.query import QueryError


class DetachedDeltaTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def inline_legacy(self):
        selected, _ = active_snapshot(self.baseline, self.args[1], self.args[2])
        payload = dict(selected.payload)
        payload['delta'] = dict(payload['delta'])
        payload['evidence'] = dict(payload['evidence'])
        payload['w2_delta'] = dict(payload['w2_delta'])
        payload['b2_delta'] = dict(payload['b2_delta'])
        payload['w2_overrides'] = dict(payload['w2_overrides'])
        payload['b3_overrides'] = dict(payload['b3_overrides'])
        payload.pop('derived_trees')
        payload.pop('reference_trees')
        payload.pop('index_tree')
        payload.pop('ticker_proofs_binding')
        payload['symbol_catalog'] = {'observations': payload['symbol_catalog']['observations']}
        payload.pop('index_delta')
        payload.pop('symbol_delta')
        payload['format'] = 'catalog-composite/1.0'
        text = _json(payload); generation = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            # Model a pre-v2 installation, preserving its accepted/staged rows.
            db.execute('DELETE FROM composite_generations')
            db.execute('DELETE FROM composite_blobs')
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        return generation

    def test_new_generations_reuse_old_blobs_without_rewriting_them(self):
        self.init(); first = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        source, old_text = next(iter(pinned[0].payload['delta'].items()))
        old_candidate = pinned[0].payload['candidates'][0]
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
            self.assertNotIn('delta', payload)
            self.assertEqual(payload['reference_trees']['delta']['count'], 1)
            self.assertEqual(pinned[0].payload['delta'].references[source], old_candidate['rows_sha256'])
            self.assertNotIn(old_text, _json(payload))
            first_count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            self.assertGreater(first_count, 2)
            db.execute("CREATE TRIGGER immutable_blobs BEFORE UPDATE ON composite_blobs BEGIN SELECT RAISE(ABORT,'immutable'); END")
        self.source.unlink(); self.next_delta()
        import serving.catalog_publication as cp
        real_put = cp.put_blob
        with mock.patch.object(cp, 'put_blob', wraps=real_put) as put:
            second = publish(*self.args)
        self.assertNotIn(old_candidate['rows_sha256'], [c.args[2] for c in put.call_args_list])
        self.assertNotIn(old_candidate['evidence_sha256'], [c.args[2] for c in put.call_args_list])
        self.assertEqual(pinned[0].payload['delta'][source], old_text)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertGreater(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], first_count)
            self.assertEqual(db.execute('SELECT content FROM composite_blobs WHERE digest=?', (old_candidate['rows_sha256'],)).fetchone()[0], old_text)
        self.assertNotEqual(first['generation'], second['generation'])

    def test_accessed_blob_corruption_fails_closed_without_fabricating_rows(self):
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        item = selected[0].payload['candidates'][0]
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('damaged', item['rows_sha256']))
        self.assertGreater(execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])['summary']['row_count'], 0)
        with self.assertRaisesRegex(QueryError, 'blob.*digest mismatch'):
            execute_query_definition('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'blob.*digest mismatch'):
            selected[0].payload['delta']['incremental/' + item['digest'] + '.rows.jsonl']

    def test_evidence_corruption_is_detected_by_inventory_and_rebinding(self):
        from serving.composite_binding import ensure_registry_binding
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        candidate = selected[0].payload['candidates'][0]
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DELETE FROM composite_blobs WHERE digest=?', (candidate['evidence_sha256'],))
        with self.assertRaisesRegex(QueryError, 'blob.*missing'):
            execute_query_definition('Q9-archive-inventory', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'blob.*missing'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])

    def test_generation_reference_mismatch_fails_before_selection(self):
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            text = db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0]
            payload = json.loads(text)
            from serving.persistent_index_map import ReferenceTree
            source = 'incremental/' + payload['candidates'][0]['digest'] + '.rows.jsonl'
            header = {'root': None, 'count': 0}
            ReferenceTree(db, header)[source] = '0' * 64
            payload['reference_trees']['delta'] = header
            bad = _json(payload); digest = _sha(bad)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (digest, bad))
            db.execute('UPDATE composite_active SET generation=?', (digest,))
        with self.assertRaisesRegex(QueryError, 'blob reference'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])

    def test_inline_generation_migrates_atomically_without_old_sources_or_baseline_rows(self):
        self.init(); publish(*self.args)
        legacy_id = self.inline_legacy()
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            db.execute("CREATE TRIGGER fail_blob_switch BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'injected'); END")
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read baseline canonical rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], legacy_id)
                self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)
                db.execute('DROP TRIGGER fail_blob_switch')
            new = publish(*self.args)
        self.assertEqual(new['migrated_inline_generation'], legacy_id)
        self.assertEqual(new['new_inputs'], 1)
        self.assertEqual(old[0].payload['format'], 'catalog-composite/1.0')
        self.assertEqual(len(active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['candidates']), 2)
        q = execute_query_definition('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'}, self.baseline, self.args[2], composite=old)
        self.assertTrue(any(r['business_date'] == '2016-01-06' for r in q['rows']))

    def test_inline_migration_with_no_pending_and_invalid_evidence(self):
        self.init(); publish(*self.args); legacy_id = self.inline_legacy(); self.source.unlink()
        with sqlite3.connect(self.dbpath()) as db:
            text = db.execute('SELECT payload FROM composite_generations WHERE id=?', (legacy_id,)).fetchone()[0]
            data = json.loads(text); item = data['candidates'][0]
            data['delta']['incremental/' + item['digest'] + '.rows.jsonl'] = 'corrupt'
            bad = _json(data); bad_id = _sha(bad)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (bad_id, bad))
            db.execute('UPDATE composite_active SET generation=?', (bad_id,))
        with self.assertRaisesRegex(RegistryError, 'digest mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], bad_id)
            self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], 0)
            db.execute('UPDATE composite_active SET generation=?', (legacy_id,))
        new = publish(*self.args)
        self.assertEqual(new['new_inputs'], 0)
        self.assertEqual(new['migrated_inline_generation'], legacy_id)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
