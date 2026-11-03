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

    def test_unrelated_readers_do_not_materialize_derived_reference_trees(self):
        self.init(); first = publish(*self.args)
        with sqlite3.connect(self.dbpath()) as db:
            payload = json.loads(db.execute('SELECT payload FROM composite_generations WHERE id=?', (first['generation'],)).fetchone()[0])
        roots = {header['root'] for header in list(payload['derived_trees'].values()) + list(payload['reference_trees'].values()) if header['root'] is not None}
        import serving.persistent_index_map as trie
        original = trie.entries
        traversed = []
        def tracked(db, root):
            traversed.append(root)
            if root in roots:
                raise AssertionError('unrelated query traversed derived reference tree')
            return original(db, root)
        with mock.patch.object(trie, 'entries', side_effect=tracked):
            one = execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
            four = execute_query_definition('Q4-filter', {'filters': {'symbol':'RELIANCE'}}, self.baseline, self.args[2])
        self.assertGreater(one['summary']['row_count'], 0)
        self.assertGreater(four['result_count'], 0)
        self.assertTrue(traversed)  # remaining candidate/reference/index materialization still occurs
        self.assertFalse(roots.intersection(traversed))

    def test_selected_identity_q5_preserves_results_without_derived_census_scan(self):
        from serving.query import parse_associations, query_associations
        from serving.persistent_index_map import PinnedReferenceMap
        self.init(); publish(*self.args)
        identities = ('INE002A01018', 'INE009A01021', 'INE000000006', 'NOT-PRESENT', '')
        expected = {}
        for identity in identities:
            selected, index = active_snapshot(self.baseline, self.args[1], self.args[2])
            expected[identity] = query_associations(selected, index, security_id=identity,
                                                    documents=parse_associations(selected))
        with mock.patch.object(PinnedReferenceMap, '_materialize', side_effect=AssertionError('derived census scanned')):
            for identity in identities:
                result = execute_query_definition('Q5-association', {'security_id':identity}, self.baseline, self.args[2])
                self.assertEqual(result['records'], list(expected[identity]))

    def test_new_identity_q5_keeps_published_line_number_and_pinned_snapshot(self):
        from tests import serving_fixtures as fixtures
        from tests import test_incremental_staging as staging
        from serving.incremental_staging import prepare
        from serving.query import parse_associations, query_associations
        self.init(); publish(*self.args)
        data = fixtures._member_bytes('fix-udf-2024-03-05.csv').replace(b'2024-03-05', b'2025-03-06').replace(b'INE002A01018', b'INE040A01034')
        path = Path(self.args[5]['UDIFF'], 'new-identity.zip')
        path.write_bytes(staging.archive_bytes('new.csv', data))
        prepare(*self.args, 'UDIFF', path.name, '2025-03-06', 'new-identity')
        publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        expected = query_associations(pinned[0], pinned[1], security_id='INE040A01034', documents=parse_associations(pinned[0]))
        self.assertTrue(expected)
        selected = execute_query_definition('Q5-association', {'security_id':'INE040A01034'}, self.baseline, self.args[2], composite=pinned)
        self.assertEqual(selected['records'], list(expected))
        path.unlink()
        path = Path(self.args[5]['UDIFF'], 'new-identity-next.zip')
        path.write_bytes(staging.archive_bytes('next.csv', data.replace(b'2025-03-06', b'2025-03-07')))
        prepare(*self.args, 'UDIFF', path.name, '2025-03-07', 'new-identity-next')
        publish(*self.args)
        self.assertEqual(execute_query_definition('Q5-association', {'security_id':'INE040A01034'}, self.baseline, self.args[2], composite=pinned), selected)

    def test_selected_q5_defers_unrelated_derived_corruption_to_full_verification(self):
        import serving.persistent_index_map as trie
        from serving.composite_binding import ensure_registry_binding
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        root = selected.payload['derived_trees']['w2_delta']['root']
        with sqlite3.connect(self.dbpath()) as db:
            paths = {}
            for identity in ('INE002A01018', 'INE000000006'):
                visited = set(); original = trie._read
                def track(conn, digest, depth):
                    visited.add(digest)
                    return original(conn, digest, depth)
                with mock.patch.object(trie, '_read', side_effect=track):
                    self.assertIsNotNone(trie.lookup(db, root, identity))
                paths[identity] = visited
            unrelated = next(iter(paths['INE000000006'] - paths['INE002A01018']))
            db.execute('UPDATE composite_blobs SET content=? WHERE digest=?', ('corrupt', unrelated))
        result = execute_query_definition('Q5-association', {'security_id':'INE002A01018'}, self.baseline, self.args[2])
        self.assertGreater(result['record_count'], 0)
        with self.assertRaisesRegex(QueryError, 'reference tree invalid'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])

    def test_missing_override_for_delta_fails_closed_during_q5_and_binding(self):
        from serving.composite_binding import ensure_registry_binding
        from serving.persistent_index_map import insert
        self.init(); publish(*self.args)
        current = active_snapshot(self.baseline, self.args[1], self.args[2])[0]
        refs = dict(current.payload['b3_overrides'].references)
        identity = next(iter(current.payload['b2_delta'].references))
        self.assertIn(identity, refs)
        refs['ADDED-OTHER-IDENTITY'] = refs.pop(identity)
        with sqlite3.connect(self.dbpath()) as db:
            text = db.execute('SELECT g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation').fetchone()[0]
            payload = json.loads(text); root = None
            for key, value in sorted(refs.items()):
                root = insert(db, root, key, {'digest': value})
            payload['derived_trees']['b3_overrides']['root'] = root
            text = _json(payload); generation = _sha(text)
            db.execute('INSERT INTO composite_generations VALUES (?,?)', (generation, text))
            db.execute('UPDATE composite_active SET generation=?', (generation,))
        execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'override reference census mismatch'):
            execute_query_definition('Q5-association', {'security_id':identity}, self.baseline, self.args[2])
        with self.assertRaisesRegex(QueryError, 'override reference census mismatch'):
            ensure_registry_binding(self.baseline, self.args[2], self.args[1])

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
                # Unrelated Q1 no longer traverses derived identity trees.
                execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
                with self.assertRaisesRegex(QueryError, 'reference tree invalid'):
                    execute_query_definition('Q5-association', {'security_id':'INE002A01018'}, self.baseline, self.args[2])
                from serving.composite_binding import ensure_registry_binding
                with self.assertRaisesRegex(QueryError, 'reference tree invalid'):
                    ensure_registry_binding(self.baseline, self.args[2], self.args[1])
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
