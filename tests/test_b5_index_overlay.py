"""Incremental serving-index overlay and format-5 migration tests."""
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
from serving.index import load_index


class IndexOverlayTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta

    def dbpath(self):
        return Path(self.args[1], 'source_registry.sqlite3')

    def to_v5(self):
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        payload = dict(selected.payload)
        for key in ('delta', 'evidence', 'w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides'):
            payload[key] = dict(payload[key].references)
        payload.pop('ticker_proof_tree')
        payload.pop('identity_proof_tree')
        payload.pop('candidate_tree')
        payload.pop('ticker_trees')
        payload['symbol_delta'] = {'observations': payload['symbol_delta']['observations']}
        payload.pop('derived_trees')
        payload.pop('reference_trees')
        payload.pop('index_tree')
        payload.pop('ticker_proofs_binding'); payload.pop('index_delta'); payload.pop('symbol_catalog')
        payload['format'] = 'catalog-composite/5.0'
        text = _json(payload); generation = _sha(text)
        with sqlite3.connect(self.dbpath()) as db:
            db.execute('DELETE FROM composite_generations')
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        return generation

    def test_snapshot_only_has_delta_files_and_publication_skips_index_composition(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        base, _ = load_index(self.args[2], self.baseline)
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
        self.assertNotIn('index', payload)
        self.assertNotIn('index_delta', payload)
        self.assertEqual(payload['index_tree']['file_count'], 1)
        self.assertFalse(set(base['files']) & set(old[0].payload['index_delta']['files']))
        self.assertEqual(old[1]['counts']['row_count'], base['counts']['row_count'] + old[0].payload['candidates'][0]['rows'])
        self.source.unlink(); self.next_delta()
        path = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('publication read baseline canonical rows')
            return path(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked), \
             mock.patch('serving.catalog_publication.compose_index', side_effect=AssertionError('ordinary publication composed baseline index')):
            result = publish(*self.args)
        current = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(result['row_count'], current[1]['counts']['row_count'])
        unique = {tuple(pair) for meta in current[1]['files'].values() for pair in meta['instruments']}
        self.assertEqual(current[1]['counts']['instrument_pairs'], len(unique))
        self.assertEqual(sum(part['row_count'] for part in current[1]['partitions'].values()), current[1]['counts']['row_count'])
        self.assertEqual(len(current[0].payload['index_delta']['files']), 2)
        self.assertGreater(current[1]['counts']['row_count'], old[1]['counts']['row_count'])
        self.assertEqual(execute_query_definition('Q8-data-quality', {}, self.baseline, self.args[2])['flag_census'], current[1]['flag_census'])

    def test_v5_migration_pinned_reader_rollback_pending_and_no_old_source(self):
        self.init(); publish(*self.args); old_id = self.to_v5()
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        old_index = old[1]
        self.source.unlink(); self.next_delta()
        with sqlite3.connect(self.dbpath()) as db:
            db.execute("CREATE TRIGGER stop_index BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'failure'); END")
        path = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration read baseline rows')
            return path(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            with sqlite3.connect(self.dbpath()) as db:
                self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old_id)
                self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)
                db.execute('DROP TRIGGER stop_index')
            result = publish(*self.args)
        self.assertEqual(result['migrated_index_generation'], old_id)
        self.assertEqual(result['new_inputs'], 1)
        self.assertEqual(old[1], old_index)
        self.assertGreater(active_snapshot(self.baseline, self.args[1], self.args[2])[1]['counts']['row_count'], old_index['counts']['row_count'])

    def test_v5_migration_checks_flags_against_rows_and_retries_no_pending(self):
        self.init(); publish(*self.args); old_id = self.to_v5(); self.source.unlink()
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (old_id,)).fetchone()[0])
            payload['index']['flag_census']['invented'] = 1
            text = _json(payload); bad_id = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (bad_id, text))
            db.execute('UPDATE composite_active SET generation=?', (bad_id,))
        with self.assertRaisesRegex(RegistryError, 'index disagrees with retained incremental rows'):
            publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], bad_id)
            db.execute('UPDATE composite_active SET generation=?', (old_id,))
        result = publish(*self.args)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(result['migrated_index_generation'], old_id)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_invalid_overlay_fails_closed_on_selection_and_publication(self):
        self.init(); publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0])
            payload['index_tree']['file_count'] += 1
            text = _json(payload); bad_id = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (bad_id, text))
            db.execute('UPDATE composite_active SET generation=?', (bad_id,))
        with self.assertRaisesRegex(QueryError, 'index.*census'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(RegistryError, 'index.*census'):
            publish(*self.args)
