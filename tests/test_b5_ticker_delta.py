"""Composite ticker census separation and migration on disposable data."""
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.saved import execute_query_definition
from serving.symbols import build_symbol_catalog


class TickerDeltaTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v4(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        payload = dict(selected.payload)
        for key in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides'):
            payload[key] = dict(payload[key].references)
        payload.pop('ticker_trees')
        payload['symbol_delta'] = {'observations': payload['symbol_delta']['observations']}
        payload.pop('derived_trees')
        payload.pop('reference_trees')
        payload.pop('index_tree')
        payload.pop('ticker_proofs_binding')
        payload['symbol_catalog'] = {'observations': payload['symbol_catalog']['observations']}
        payload.pop('index_delta')
        payload.pop('symbol_delta')
        payload['format'] = 'catalog-composite/4.0'
        text = _json(payload); generation = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DELETE FROM composite_generations')
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        return generation

    def test_generation_does_not_embed_baseline_census_and_resolves_parity(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
        self.assertNotIn('symbol_catalog', payload)
        self.assertNotIn('symbol_delta', payload)
        self.assertIn('ticker_trees', payload)
        self.assertLess(len(old[0].payload['symbol_delta']['observations']), len(old[0].payload['symbol_catalog']['observations']))
        recomputed = build_symbol_catalog(old[0], old[1])
        self.assertEqual(set(map(tuple, recomputed['observations'])), set(map(tuple, old[0].payload['symbol_catalog']['observations'])))
        self.source.unlink(); self.next_delta()
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('publication read historical canonical rows')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked), \
             mock.patch('serving.composite_blobs.get', side_effect=AssertionError('ordinary publication read old raw delta')):
            second = publish(*self.args)
        self.assertNotEqual(first['generation'], second['generation'])
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        expected = build_symbol_catalog(selected[0], selected[1])
        self.assertEqual(set(map(tuple, expected['observations'])), set(map(tuple, selected[0].payload['symbol_catalog']['observations'])))
        query = execute_query_definition('Q3-instrument', {'symbol':'NEWRELIANCE','series':'EQ'}, self.baseline, self.args[2])
        self.assertTrue(any(row['business_date'] == '2025-03-06' for row in query['rows']))
        self.assertFalse(any(o[0] == 'NEWRELIANCE' for o in old[0].payload['symbol_catalog']['observations']))

    def test_v4_migration_with_pending_rollback_and_no_old_archive_reads(self):
        self.init(); publish(*self.args); old_id = self.to_v4()
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        old_census = old[0].payload['symbol_catalog']
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            db.execute("CREATE TRIGGER block_ticker_switch BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
        path = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read baseline canonical rows')
            return path(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)
                self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)
                db.execute('DROP TRIGGER block_ticker_switch')
            result = publish(*self.args)
        self.assertEqual(result['migrated_tickers_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(old[0].payload['symbol_catalog'], old_census)
        self.assertEqual(len(active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['candidates']), 2)

    def test_v4_migration_checks_census_and_can_retry_without_pending(self):
        self.init(); publish(*self.args); old_id = self.to_v4(); self.source.unlink()
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (old_id,)).fetchone()[0])
            payload['symbol_catalog']['observations'].pop()
            text = _json(payload); bad_id = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (bad_id, text))
            db.execute('UPDATE composite_active SET generation=?', (bad_id,))
        with self.assertRaisesRegex(RegistryError, 'ticker census disagrees'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], bad_id)
            db.execute('UPDATE composite_active SET generation=?', (old_id,))
        result = publish(*self.args)
        self.assertEqual(result['migrated_tickers_generation'], old_id)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_invalid_delta_census_fails_closed_before_selection_or_publication(self):
        from serving.query import QueryError
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0])
            payload['ticker_trees']['tickers']['count'] = -1
            text = _json(payload); bad_id = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (bad_id, text))
            db.execute('UPDATE composite_active SET generation=?', (bad_id,))
        with self.assertRaises(QueryError):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaises(RegistryError):
            publish(*self.args)

    def test_v4_migration_refuses_inconsistent_accepted_evidence(self):
        self.init(); publish(*self.args); old_id = self.to_v4()
        with sqlite3.connect(self.dbpath()) as db:
            record = json.loads(db.execute("SELECT record FROM accepted WHERE file_name='new.zip'").fetchone()[0])
            record['rows_sha256'] = '0' * 64
            db.execute("UPDATE accepted SET record=? WHERE file_name='new.zip'", (_json(record),))
        with self.assertRaisesRegex(RegistryError, 'accepted input mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)

    def test_v4_migration_refuses_corrupt_retained_delta(self):
        self.init(); publish(*self.args); old_id = self.to_v4()
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (old_id,)).fetchone()[0])
            digest = next(iter(payload['delta'].values()))
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', digest))
        with self.assertRaisesRegex(RegistryError, 'blob.*digest mismatch'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)
