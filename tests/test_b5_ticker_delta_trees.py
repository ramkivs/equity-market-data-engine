"""Targeted incremental ticker trees, parity, migration and corruption."""
import copy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.composite_blobs import schema
from serving.incremental_publication import active_snapshot, publish, _sha
from serving.incremental_registry import RegistryError, _json
from serving.query import QueryError
from serving.saved import execute_query_definition
from serving.symbols import resolve_symbol
from serving.ticker_delta_trees import TickerDeltaTrees, empty


class TickerTreeUnitTests(unittest.TestCase):
    def test_overlap_invalid_identity_and_pinned_tree_parity(self):
        db = sqlite3.connect(':memory:')
        try:
            schema(db)
            trees = empty(); view = TickerDeltaTrees(trees, db=db)
            first = {'observations': [('AAA', 'EQ', 'VALID1', 'A', '2024-01-01', '2024-01-05'),
                                      ('RAW', 'EQ', None, 'RAW', None, None)]}
            view.update(first); before = TickerDeltaTrees(copy.deepcopy(trees), db=db)
            view.update({'observations': [('BBB', 'EQ', 'VALID1', 'B', '2024-01-05', '2024-01-10'),
                                          ('AAA', 'BE', 'VALID2', 'A', '2024-01-01', '2024-01-05')]})
            self.assertEqual(before.ticker_series('AAA'), {'EQ'})
            self.assertEqual(view.ticker_series('AAA'), {'EQ', 'BE'})
            self.assertEqual(resolve_symbol(before, 'AAA', 'EQ')['identity'], 'VALID1')
            with self.assertRaisesRegex(ValueError, 'overlapping'):
                resolve_symbol(view, 'AAA', 'EQ')
            self.assertIsNone(resolve_symbol(view, 'RAW', 'EQ')['identity'])
            self.assertEqual(len(view['observations']), 4)
            self.assertEqual(len(before['observations']), 2)
        finally:
            db.close()

    def test_cross_projection_mismatch_fails_full_verify_and_update(self):
        db = sqlite3.connect(':memory:')
        try:
            schema(db); trees = empty(); view = TickerDeltaTrees(trees, db=db)
            row = ('AAA', 'EQ', 'VALID1', 'A', '2024-01-01', '2024-01-05')
            view.update({'observations': [row]})
            trees['identities'] = {'root': None, 'count': 0}
            with self.assertRaisesRegex(ValueError, 'identity census mismatch'):
                view.ticker_observations('AAA', 'EQ')
            with self.assertRaisesRegex(ValueError, 'census mismatch'):
                view['observations']
            with self.assertRaisesRegex(ValueError, 'identity census mismatch'):
                view.update({'observations': [row]})
        finally:
            db.close()


class TickerTreePublicationTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v10(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        payload = dict(selected[0].payload)
        payload['symbol_delta'] = {'observations': payload['symbol_delta']['observations']}
        for name in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides', 'ticker_trees', 'symbol_catalog', 'index_delta', 'index'):
            payload.pop(name)
        payload['format'] = 'catalog-composite/10.0'
        text = _json(payload); old = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (old, text))
            db.execute('UPDATE composite_active SET generation=?', (old,))
        return old

    def test_publication_and_q3_q4_q5_use_targeted_groups(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        old_census = old[0].payload['symbol_delta']['observations']
        self.source.unlink(); self.next_delta()
        import serving.persistent_index_map as trie
        with mock.patch.object(trie, 'entries', side_effect=AssertionError('full tree scan')), \
             mock.patch.object(TickerDeltaTrees, '__getitem__', side_effect=AssertionError('full ticker delta scan')):
            second = publish(*self.args)
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(old[0].payload['symbol_delta']['observations'], old_census)
        with mock.patch.object(TickerDeltaTrees, '__getitem__', side_effect=AssertionError('full ticker delta scan')):
            q3 = execute_query_definition('Q3-instrument', {'symbol':'NEWRELIANCE','series':'EQ'}, self.baseline, self.args[2])
            q4 = execute_query_definition('Q4-filter', {'filters': {'symbol':'NEWRELIANCE'}}, self.baseline, self.args[2])
            q5 = execute_query_definition('Q5-association', {'symbol':'NEWRELIANCE','series':'EQ'}, self.baseline, self.args[2])
        self.assertGreater(q3['result_count'], 0); self.assertGreater(q4['result_count'], 0); self.assertGreater(q5['record_count'], 0)
        with sqlite3.connect(self.dbpath()) as db:
            p = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (second['generation'],)).fetchone()[0])
        self.assertNotIn('symbol_delta', p)
        self.assertEqual(set(p['ticker_trees']), {'tickers', 'identities', 'series'})

    def test_corrupt_tree_fails_targeted_access_and_explicit_full_binding(self):
        from serving.composite_binding import ensure_registry_binding
        for i, kind in enumerate(('tickers', 'identities', 'series')):
            with self.subTest(kind=kind):
                if i:
                    self.tearDown(); self.setUp()
                self.init(); old = publish(*self.args)
                selected = active_snapshot(self.baseline, self.args[1], self.args[2])
                root = selected[0].payload['ticker_trees'][kind]['root']
                with sqlite3.connect(self.dbpath()) as db:
                    db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('broken', root))
                with self.assertRaisesRegex(QueryError, 'ticker'):
                    execute_query_definition('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'}, self.baseline, self.args[2])
                with self.assertRaises(QueryError):
                    ensure_registry_binding(self.baseline, self.args[2], self.args[1])
                self.next_delta()
                with self.assertRaises(RegistryError):
                    publish(*self.args)
                with sqlite3.connect(self.dbpath()) as db:
                    self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old['generation'])

    def test_explicit_binding_checks_ticker_trees_against_retained_rows(self):
        from serving.composite_binding import ensure_registry_binding
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0])
            payload['ticker_trees'] = empty()
            text = _json(payload); digest = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (digest, text))
            db.execute('UPDATE composite_active SET generation=?', (digest,))
        with self.assertRaisesRegex(QueryError, 'ticker delta trees disagree'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])

    def test_v10_migration_pending_rollback_and_pinned_reader(self):
        self.init(); publish(*self.args); old_id = self.to_v10()
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        old_census = list(pinned[0].payload['symbol_delta']['observations'])
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            count = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
            db.execute("CREATE TRIGGER stop_ticker_tree BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'test'); END")
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
                db.execute('DROP TRIGGER stop_ticker_tree')
            result = publish(*self.args)
        self.assertEqual(result['migrated_ticker_trees_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(pinned[0].payload['symbol_delta']['observations'], old_census)
        self.assertGreater(len(active_snapshot(self.baseline, self.args[1], self.args[2])[0].payload['symbol_delta']['observations']), len(old_census))

    def test_v10_migration_without_pending_preserves_query(self):
        self.init(); publish(*self.args); old_id = self.to_v10()
        params = {'symbol':'NEWRELIANCE','series':'EQ'}
        before = execute_query_definition('Q5-association', params, self.baseline, self.args[2])
        self.source.unlink(); result = publish(*self.args)
        after = execute_query_definition('Q5-association', params, self.baseline, self.args[2])
        self.assertEqual(result['migrated_ticker_trees_generation'], old_id)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(_json(before).replace(old_id, result['generation']), _json(after))
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
