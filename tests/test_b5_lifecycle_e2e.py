"""Repeatable, disposable B5 publication, recovery and reader lifecycle."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest import mock
import urllib.request

from tests import serving_fixtures as fixtures
from tests import test_incremental_staging as staging
from tests import test_b5_catalog_publication as catalog_tests
from serving.composite_binding import ensure_registry_binding
from serving.continuity_catalog import verify_catalog
from serving.incremental_publication import active_snapshot, publish
from serving.incremental_registry import RegistryError
from serving.incremental_staging import prepare
from serving.query import QueryError
from serving.saved import create_saved, execute_query_definition, execute_saved
from serving.ticker_proofs import FILE as PROOF_FILE, recover
from ui.api import UiApi


class B5LifecycleTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init

    def query(self, mode, params=None, snapshot=None):
        return execute_query_definition(mode, params or {}, self.baseline, self.args[2], composite=snapshot)

    def stage_date(self, date):
        data = fixtures._member_bytes('fix-udf-2024-03-05.csv').replace(b'2024-03-05', date.encode()).replace(b'RELIANCE', b'NEWRELIANCE')
        name = 'delta-' + date + '.zip'
        path = Path(self.args[5]['UDIFF'], name)
        path.write_bytes(staging.archive_bytes('delta.csv', data))
        self.assertEqual(prepare(*self.args, 'UDIFF', name, date, 'lifecycle-' + date)['status'], 'VALIDATED-STAGED-NOT-PUBLISHED')
        return path

    def test_repeated_publication_restart_d21_recovery_and_all_readers(self):
        self.init()
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('publication reread historical canonical rows')
            return original(obj, rel)
        import serving.continuity_catalog as catalog
        with mock.patch.object(type(self.baseline), 'path', blocked), \
             mock.patch.object(catalog, '_validated_groups', wraps=catalog._validated_groups) as validate_groups:
            first = publish(*self.args)
        self.assertEqual(validate_groups.call_count, 1)
        self.source.unlink()
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        pinned_inventory = self.query('Q9-archive-inventory', snapshot=pinned)
        dbpath = Path(self.args[1], 'source_registry.sqlite3')
        dates = ['2025-03-06', '2025-03-07', '2025-03-10', '2025-03-11', '2025-03-12']
        generation = first['generation']
        for number, date in enumerate(dates):
            archive = self.stage_date(date)
            if number == 1:
                changed = Path(self.args[5]['LEGACY'], 'fix-leg-2016-01-04.csv')
                changed.write_bytes(b'changed historic content')
                outcome = prepare(*self.args, 'LEGACY', changed.name, '2016-01-04', 'd21-lifecycle')
                self.assertEqual(outcome['status'], 'CHANGED-CONFLICT-UNRESOLVED')
            if number == 2:
                with sqlite3.connect(dbpath) as db:
                    accepted_before = db.execute('SELECT count(*) FROM accepted').fetchone()[0]
                    blobs_before = db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0]
                    db.execute("CREATE TRIGGER fail_lifecycle BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'interruption'); END")
                with mock.patch.object(type(self.baseline), 'path', blocked):
                    with self.assertRaises(RegistryError):
                        publish(*self.args)
                with sqlite3.connect(dbpath) as db:
                    self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], generation)
                    self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], accepted_before)
                    self.assertEqual(db.execute('SELECT count(*) FROM composite_blobs').fetchone()[0], blobs_before)
                    db.execute('DROP TRIGGER fail_lifecycle')
            with mock.patch.object(type(self.baseline), 'path', blocked), \
                 mock.patch('serving.incremental_staging.build_canonical', side_effect=AssertionError('publication reparsed archive')):
                outcome = publish(*self.args)
            self.assertEqual(outcome['new_inputs'], 1)
            self.assertNotEqual(outcome['generation'], generation)
            generation = outcome['generation']
            archive.unlink()
        self.assertEqual(self.query('Q9-archive-inventory', snapshot=pinned), pinned_inventory)
        self.assertEqual(self.query('Q8-data-quality', snapshot=pinned)['changed']['record_count'], 0)
        self.assertEqual(self.query('Q8-data-quality')['changed']['record_count'], 1)
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].manifest_digest, generation)

        q1 = self.query('Q1-dataset')
        q2 = self.query('Q2-date-range', {'date_from':'2025-03-06', 'date_to':'2025-03-12'})
        q3 = self.query('Q3-instrument', {'symbol':'NEWRELIANCE', 'series':'EQ'})
        q4 = self.query('Q4-filter', {'filters':{'symbol':'NEWRELIANCE', 'series':'EQ'}})
        q5 = self.query('Q5-association', {'symbol':'NEWRELIANCE', 'series':'EQ'})
        q6 = self.query('Q6-calendar', {'date_from':'2025-03-06', 'date_to':'2025-03-12'})
        q8 = self.query('Q8-data-quality')
        q9 = self.query('Q9-archive-inventory')
        q10 = self.query('Q10-qualification')
        self.assertTrue(q1)
        self.assertEqual({r['business_date'] for r in q2['rows']}, set(dates))
        self.assertTrue(set(dates) <= {r['business_date'] for r in q3['rows']})
        self.assertEqual(q3['result_count'], q4['result_count'])
        self.assertGreater(q5['record_count'], 0)
        self.assertTrue(all(x['file_present'] for x in q6['records'] if x['trade_date'] in dates))
        self.assertEqual(q8['reconciliation']['incremental_availability'], 'not-published')
        delta_archives = [a for a in q9['archives'] if a['source_scope'].startswith('incremental')]
        self.assertEqual(len(delta_archives), 6)
        self.assertTrue(all(a['d01'] is None and a['archive_sha256_d01'] is None for a in delta_archives))
        self.assertIsNone(q9['summary']['archive_set_digest'])
        self.assertIn('qualified-baseline-only', q10['subject_scope'])
        self.assertEqual(q10['composite_generation'], generation)
        row = next(r for r in q3['rows'] if r['business_date'] == dates[-1])
        q7 = self.query('Q7-record-detail', {'source_file':row['serving']['source_file'], 'source_line_number':row['source_line_number']})
        self.assertEqual(q7['archive']['digest'], row['provenance']['archive_sha256'])
        self.assertEqual(q7['reconciliation_availability'], 'not-published-for-incremental-input')

        create_saved(self.args[3], 'lifecycle-inventory', 'Q9-archive-inventory', {})
        self.assertEqual(execute_saved(self.args[3], 'lifecycle-inventory', self.baseline, self.args[2]), q9)
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4])
        self.assertEqual(api.history_record({'mode':'Q9-archive-inventory', 'params':{}})['query'], q9)

        # Missing derived proofs and a removed binding fail closed; recover only
        # from the verified compact catalog and explicitly repair the known path.
        proof = Path(self.args[2], PROOF_FILE)
        proof.unlink()
        with self.assertRaises(QueryError):
            self.query('Q1-dataset')
        with mock.patch.object(type(self.baseline), 'path', blocked):
            self.assertEqual(recover(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])['generation'], generation)
        Path(self.args[2], 'composite_registry.json').unlink()
        with self.assertRaisesRegex(QueryError, 'binding missing'):
            self.query('Q1-dataset')
        with mock.patch.object(type(self.baseline), 'path', blocked):
            facts = ensure_registry_binding(self.baseline, self.args[2], self.args[1])
            verify_catalog(self.baseline, self.args[2])
        self.assertEqual(facts['generation'], generation)
        self.assertEqual(facts['accepted_incremental'], 6)
        self.assertEqual(self.query('Q9-archive-inventory'), q9)

        # Exercise a fresh application process after every accepted source was
        # removed; its state must still select the same committed generation.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        cmd = [sys.executable, '-m', 'ui', '--package', str(self.pkg), '--state', self.args[2], '--saved-state', self.args[3], '--history-state', self.args[4], '--port', str(port)]
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(200):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=1) as response:
                        status = json.load(response)
                    break
                except OSError:
                    if proc.poll() is not None:
                        self.fail('server exited: %s' % (proc.communicate(),))
                    time.sleep(.05)
            else:
                self.fail('server failed to start')
            self.assertEqual(status['composite']['generation'], generation)
            request = urllib.request.Request('http://127.0.0.1:%d/api/query' % port,
                data=json.dumps({'mode':'Q9-archive-inventory','params':{}}).encode(),
                headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(request, timeout=20) as response:
                self.assertEqual(json.load(response)['query'], q9)
        finally:
            proc.terminate(); proc.communicate(timeout=10)
