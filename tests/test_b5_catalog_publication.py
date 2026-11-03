"""Catalog-backed publication: actual selected reader path on disposable data."""
import json
import os
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest import mock

from tests import test_incremental_staging as staging
from tests import serving_fixtures as fixtures
from serving.continuity_catalog import bootstrap, FILENAME
from serving.index import build_index, write_index
from serving.incremental_publication import publish, active_snapshot
from serving.incremental_registry import RegistryError, conflicts
from serving.incremental_staging import prepare
from serving.saved import execute_query_definition, create_saved, execute_saved
from serving.w2_continuity import build_continuity, canonical_rows
from ui.api import UiApi


class CatalogPublicationTests(unittest.TestCase):
    setUp = staging.StagingTests.setUp
    tearDown = staging.StagingTests.tearDown
    stage = staging.StagingTests.stage

    def init(self):
        write_index(self.args[2], build_index(self.baseline))
        bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.stage()

    def next_delta(self):
        data = fixtures._member_bytes('fix-udf-2024-03-05.csv').replace(b'2024-03-05', b'2025-03-06').replace(b'RELIANCE', b'NEWRELIANCE')
        Path(self.args[5]['UDIFF'], 'later.zip').write_bytes(staging.archive_bytes('later.csv', data))
        prepare(*self.args, 'UDIFF', 'later.zip', '2025-03-06', 'later')

    def test_actual_publish_does_not_open_baseline_rows_and_serves_q3_q4_q5_q7(self):
        self.init()
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('publication read canonical baseline')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked), \
             mock.patch('serving.incremental_publication.LIMIT', 1):
            result = publish(*self.args)
        self.assertEqual(result['status'], 'PUBLISHED')
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4])
        params = {'symbol':'RELIANCE','series':'EQ'}
        q3 = api.query({'mode':'Q3-instrument','params':params})['query']
        q4 = api.query({'mode':'Q4-filter','params':{'filters':params}})['query']
        self.assertEqual(q3['result_count'], q4['result_count'])
        delta = next(r for r in q3['rows'] if r['business_date'] == '2016-01-06')
        detail = api.query({'mode':'Q7-record-detail','params':{'source_file':delta['serving']['source_file'], 'source_line_number':delta['source_line_number']}})['query']
        self.assertEqual(detail['archive']['digest'], delta['provenance']['archive_sha256'])
        q5 = api.query({'mode':'Q5-association','params':{'security_id':'INE002A01018'}})['query']
        self.assertEqual(q5['continuity']['availability'], 'available')
        self.assertTrue(any(group['intervals'][-1]['observed_to'] >= '2016-01-06' for record in q5['records'] for group in record['serving']['continuity']))
        create_saved(self.args[3], 'selected', 'Q3-instrument', params)
        self.assertEqual(execute_saved(self.args[3], 'selected', self.baseline, self.args[2])['rows'], q3['rows'])
        self.assertEqual(api.history_record({'mode':'Q3-instrument','params':params})['query']['rows'], q3['rows'])
        identity = {'security_id':'INE002A01018'}
        create_saved(self.args[3], 'association', 'Q5-association', identity)
        self.assertEqual(execute_saved(self.args[3], 'association', self.baseline, self.args[2])['records'], q5['records'])
        self.assertEqual(api.history_record({'mode':'Q5-association','params':identity})['query']['records'], q5['records'])

    def test_w2_and_b3_affected_parity_against_complete_small_fixture(self):
        self.init(); publish(*self.args)
        selected, index = active_snapshot(self.baseline, self.args[1], self.args[2])
        rows = list(canonical_rows(self.baseline))
        for source, text in selected.payload['delta'].items():
            rows += [(source, json.loads(line)) for line in text.splitlines() if line.strip()]
        expected = build_continuity(rows, self.baseline.manifest_digest)
        expected_groups = [g for g in expected['identities'] if g['security_id'] == 'INE002A01018']
        self.assertEqual(selected.payload['b3_overrides']['INE002A01018'], expected_groups)
        from serving.incremental_publication import _w2
        full_w2 = _w2([('all', [row for _, row in rows])])
        expected_w2 = next(doc for doc in full_w2 if doc['security_id'] == 'INE002A01018')
        self.assertEqual(selected.payload['w2_overrides']['INE002A01018'], expected_w2)
        q5 = execute_query_definition('Q5-association', {'security_id':'INE467B01029'}, self.baseline, self.args[2], composite=(selected,index))
        self.assertGreater(q5['record_count'], 0)
        self.assertTrue(q5['records'][0]['serving']['continuity'])

    def test_subsequent_publication_requires_only_new_source_and_pins_old_reader(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.source.unlink()
        self.next_delta()
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('historical row was reread')
            return original(obj, rel)
        with mock.patch.object(type(self.baseline), 'path', blocked):
            second = publish(*self.args)
            self.assertNotEqual(first['generation'], second['generation'])
            self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')
        prior = execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2], composite=old)
        current = execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        self.assertGreater(current['summary']['row_count'], prior['summary']['row_count'])
        new = execute_query_definition('Q3-instrument', {'symbol':'NEWRELIANCE','series':'EQ'}, self.baseline, self.args[2])
        self.assertTrue(any(row['business_date'] == '2025-03-06' for row in new['rows']))
        q5 = execute_query_definition('Q5-association', {'security_id':'INE002A01018'}, self.baseline, self.args[2])
        self.assertTrue(any(t['to_symbol']=='NEWRELIANCE' for r in q5['records'] for g in r['serving']['continuity'] for t in g['transitions']))

    def test_transaction_failure_rollback_retry_and_d21(self):
        self.init()
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        from serving.incremental_publication import _schema
        with sqlite3.connect(path) as db:
            _schema(db)
            db.execute("CREATE TRIGGER block BEFORE INSERT ON composite_active BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(RegistryError):
            publish(*self.args)
        self.assertIsNone(active_snapshot(self.baseline, self.args[1], self.args[2]))
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 0)
            db.execute('DROP TRIGGER block')
        publish(*self.args)
        name = 'fix-leg-2016-01-04.csv'
        Path(self.args[5]['LEGACY'], name).write_bytes(b'changed')
        result = prepare(*self.args, 'LEGACY', name, '2016-01-04', 'conflict')
        self.assertEqual(result['status'], 'CHANGED-CONFLICT-UNRESOLVED')
        self.assertEqual(len(conflicts(*self.args)), 1)

    def test_failed_second_publication_preserves_first_and_retries(self):
        self.init(); first = publish(*self.args)
        self.next_delta()
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        with sqlite3.connect(path) as db:
            db.execute("CREATE TRIGGER block_switch BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(RegistryError):
            publish(*self.args)
        selected, _ = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(selected.manifest_digest, first['generation'])
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS + 1)
            db.execute('DROP TRIGGER block_switch')
        self.assertNotEqual(publish(*self.args)['generation'], first['generation'])

    def test_corrupt_catalog_key_fails_closed_before_publication(self):
        self.init()
        with sqlite3.connect(os.path.join(self.args[2], FILENAME)) as db:
            db.execute("UPDATE observations SET w2_identity='HIDDEN' WHERE ordinal=(SELECT min(ordinal) FROM observations WHERE w2_identity='INE002A01018')")
        with self.assertRaises(RegistryError):
            publish(*self.args)
        self.assertIsNone(active_snapshot(self.baseline, self.args[1], self.args[2]))

    def test_subprocess_restart_without_archives_or_registry_flag(self):
        import socket, subprocess, sys, time, urllib.request
        self.init(); published = publish(*self.args)
        self.source.unlink()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        cmd = [sys.executable, '-m', 'ui', '--package', str(self.pkg), '--state', self.args[2],
               '--saved-state', self.args[3], '--history-state', self.args[4], '--port', str(port)]
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
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
                self.fail('server did not start')
            self.assertEqual(status['composite']['generation'], published['generation'])
            req = urllib.request.Request('http://127.0.0.1:%d/api/query' % port,
                  data=json.dumps({'mode':'Q5-association','params':{'security_id':'INE002A01018'}}).encode(),
                  headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=20) as response:
                q5 = json.load(response)['query']
            self.assertEqual(q5['continuity']['availability'], 'available')
            self.assertGreater(q5['record_count'], 0)
        finally:
            proc.terminate(); proc.communicate(timeout=10)

    def test_corrupt_pointer_refuses_to_publish_and_preserves_staging(self):
        self.init()
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        from serving.incremental_publication import _schema
        with sqlite3.connect(path) as db:
            _schema(db)
            db.execute("INSERT INTO composite_active VALUES (1,'missing')")
        with self.assertRaisesRegex(RegistryError, 'pointer'):
            publish(*self.args)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], 'missing')
            self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 1)

    def test_serving_cli_reads_catalog_generation(self):
        import subprocess, sys
        self.init(); publish(*self.args)
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        common = ['--package', str(self.pkg), '--state', self.args[2]]
        process = subprocess.run([sys.executable, '-m', 'serving', 'query', *common, '--identity', 'INE002A01018'],
                                 env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = json.loads(process.stdout)
        self.assertGreater(result['record_count'], 0)
        self.assertEqual(result['continuity']['availability'], 'available')

    def test_registry_cli_publishes_catalog_generation(self):
        import subprocess, sys
        self.init()
        args = ['--package', str(self.pkg), '--registry', self.args[1], '--state', self.args[2],
                '--saved-state', self.args[3], '--history-state', self.args[4],
                '--legacy-root', self.args[5]['LEGACY'], '--udiff-root', self.args[5]['UDIFF'], 'publish']
        code = r"""
import sys
from serving.baseline import open_baseline
from serving.incremental_registry import main,bindings
from serving import incremental_staging
baseline=open_baseline(sys.argv[1],verify_files=False)
incremental_staging.runtime_bindings=lambda: bindings(baseline)
raise SystemExit(main(sys.argv[2:]))
"""
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.run([sys.executable, '-c', code, str(self.pkg), *args], env=env,
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['data']['status'], 'PUBLISHED')
        selected, _ = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(selected.payload['format'], 'catalog-composite/13.0')

    def test_ticker_reuse_recomputes_all_affected_ambiguities(self):
        self.init(); publish(*self.args)
        data = fixtures._member_bytes('fix-udf-2024-03-05.csv').replace(b'2024-03-05', b'2025-03-06')
        data = data.replace(b',TCS,EQ,', b',RELIANCE,EQ,')
        Path(self.args[5]['UDIFF'], 'reuse.zip').write_bytes(staging.archive_bytes('reuse.csv', data))
        prepare(*self.args, 'UDIFF', 'reuse.zip', '2025-03-06', 'reuse')
        publish(*self.args)
        selected, _ = active_snapshot(self.baseline, self.args[1], self.args[2])
        all_rows = list(canonical_rows(self.baseline))
        for source, text in selected.payload['delta'].items():
            all_rows.extend((source, json.loads(line)) for line in text.splitlines() if line.strip())
        expected = build_continuity(all_rows, self.baseline.manifest_digest)
        for identity in ('INE002A01018', 'INE467B01029'):
            expected_groups = [g for g in expected['identities'] if g['security_id'] == identity]
            self.assertEqual(selected.payload['b3_overrides'][identity], expected_groups)
            self.assertTrue(any(g['status'] == 'ambiguous' for g in expected_groups))
        from serving.query import QueryError
        with self.assertRaisesRegex(QueryError, 'symbol-ambiguous'):
            execute_query_definition('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'}, self.baseline, self.args[2])

    def test_inflight_request_pins_prior_catalog_generation(self):
        import ui.api as api_mod
        self.init(); first = publish(*self.args)
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4])
        before = api.query({'mode':'Q1-dataset','params':{}})['query']['summary']['row_count']
        self.next_delta()
        ready, proceed, output = threading.Event(), threading.Event(), []
        original = api_mod.execute_query_definition
        def delayed(*args, **kwargs):
            ready.set()
            if not proceed.wait(10):
                raise RuntimeError('timed out')
            return original(*args, **kwargs)
        def reader():
            try:
                output.append(api.query({'mode':'Q1-dataset','params':{}})['query']['summary']['row_count'])
            except Exception as exc:
                output.append(exc)
        with mock.patch('ui.api.execute_query_definition', side_effect=delayed):
            thread = threading.Thread(target=reader); thread.start()
            self.assertTrue(ready.wait(5))
            second = publish(*self.args)
            proceed.set(); thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(output, [before])
        self.assertGreater(api.query({'mode':'Q1-dataset','params':{}})['query']['summary']['row_count'], before)

    def test_abrupt_process_exit_before_commit_rolls_back_and_retries(self):
        import subprocess, sys
        from serving.incremental_publication import _schema
        self.init()
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        with sqlite3.connect(path) as db:
            _schema(db)
            db.execute("CREATE TRIGGER abrupt_catalog BEFORE INSERT ON composite_active BEGIN SELECT exit_now(); END")
        code = r"""
import json,os,sys
from serving.baseline import open_baseline
from serving.incremental_registry import bindings
from serving import incremental_staging
from serving import catalog_publication as cp
base=open_baseline(sys.argv[1],verify_files=False)
args=json.loads(sys.argv[2])
incremental_staging.runtime_bindings=lambda: bindings(base)
original=cp._open
def open_with_exit(*a):
    db,meta=original(*a)
    db.create_function('exit_now',0,lambda:os._exit(47))
    return db,meta
cp._open=open_with_exit
cp.publish(base,*args)
"""
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-c', code, str(self.pkg), json.dumps(self.args[1:])], env=env,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 47, proc.stderr)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM composite_active').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS)
            db.execute('DROP TRIGGER abrupt_catalog')
        self.assertEqual(publish(*self.args)['status'], 'PUBLISHED')

    def test_bounded_migration_and_new_delta_preserve_pinned_readers(self):
        write_index(self.args[2], build_index(self.baseline))
        self.stage()
        old = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        old_q5 = execute_query_definition('Q5-association', {'security_id':'INE002A01018'}, self.baseline, self.args[2], composite=pinned)
        bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.source.unlink()  # accepted inputs must not require their old source archives
        self.next_delta()
        original = type(self.baseline).path
        def blocked(obj, rel):
            if rel.endswith('.rows.jsonl'):
                raise AssertionError('migration reread historical canonical rows')
            return original(obj, rel)
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        with sqlite3.connect(path) as db:
            db.execute("CREATE TRIGGER block_migration BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT,'failure'); END")
        with mock.patch.object(type(self.baseline), 'path', blocked):
            with self.assertRaises(RegistryError):
                publish(*self.args)
            self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].manifest_digest, old['generation'])
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 2)
                db.execute('DROP TRIGGER block_migration')
            new = publish(*self.args)
        self.assertEqual(new['migrated_bounded_generation'], old['generation'])
        self.assertEqual(new['new_inputs'], 1)
        selected, _ = active_snapshot(self.baseline, self.args[1], self.args[2])
        self.assertEqual(selected.payload['format'], 'catalog-composite/13.0')
        self.assertEqual(len(selected.payload['candidates']), 2)
        self.assertEqual(execute_query_definition('Q5-association', {'security_id':'INE002A01018'}, self.baseline, self.args[2], composite=pinned), old_q5)
        q9 = execute_query_definition('Q9-archive-inventory', {}, self.baseline, self.args[2])
        self.assertEqual(sum(r['source_scope'].startswith('incremental') for r in q9['archives']), 2)

    def test_bounded_migration_without_pending_input_matches_readers(self):
        write_index(self.args[2], build_index(self.baseline))
        self.stage(); old = publish(*self.args)
        pinned = active_snapshot(self.baseline, self.args[1], self.args[2])
        modes = [('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'}),
                 ('Q5-association', {'security_id':'INE002A01018'})]
        before = [execute_query_definition(m, p, self.baseline, self.args[2], composite=pinned) for m,p in modes]
        bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.source.unlink()
        result = publish(*self.args)
        self.assertEqual(result['new_inputs'], 0)
        self.assertEqual(result['migrated_bounded_generation'], old['generation'])
        after = [execute_query_definition(m, p, self.baseline, self.args[2]) for m,p in modes]
        self.assertEqual(json.dumps(before, sort_keys=True).replace(old['generation'], result['generation']), json.dumps(after, sort_keys=True))
        self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_bounded_migration_fails_closed_on_accepted_record_corruption(self):
        write_index(self.args[2], build_index(self.baseline))
        self.stage(); old = publish(*self.args)
        bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        with sqlite3.connect(path) as db:
            record = db.execute("SELECT record FROM accepted WHERE file_name='new.zip'").fetchone()[0]
            damaged = json.loads(record); damaged['rows_sha256'] = '0' * 64
            db.execute("UPDATE accepted SET record=? WHERE file_name='new.zip'", (json.dumps(damaged),))
        with self.assertRaisesRegex(RegistryError, 'accepted input mismatch'):
            publish(*self.args)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('SELECT generation FROM composite_active').fetchone()[0], old['generation'])
            self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM staged_candidates').fetchone()[0], 1)
            db.execute("UPDATE accepted SET record=? WHERE file_name='new.zip'", (record,))
        self.assertEqual(publish(*self.args)['migrated_bounded_generation'], old['generation'])

    def test_duplicate_content_is_not_staged_or_published(self):
        self.init(); first = publish(*self.args)
        other = Path(self.args[5]['LEGACY'], 'copy.zip')
        other.write_bytes(self.source.read_bytes())
        outcome = prepare(*self.args, 'LEGACY', 'copy.zip', '2016-01-07', 'duplicate')
        self.assertEqual(outcome['status'], 'ANOMALOUS-DUPLICATE-CONTENT')
        self.assertEqual(publish(*self.args)['generation'], first['generation'])


class AboveFormerLimitTests(unittest.TestCase):
    def test_publish_against_real_persisted_20009_row_synthetic_baseline(self):
        name = 'fix-leg-2016-01-04.csv'
        original = fixtures.MEMBERS[name]
        lines = list(original[3]) + [original[3][2]] * 20000  # blank ISIN, distinct canonical line numbers
        expanded = (original[0], original[1], original[2], lines, len(lines))
        instance = staging.StagingTests()
        with mock.patch.dict(fixtures.MEMBERS, {name: expanded}):
            instance.setUp()  # complete, consistent synthetic fixture; no M2 or historical archive used
        try:
            member = fixtures._member_bytes(name).replace(b'04-JAN-2016', b'06-JAN-2016')
            instance.source.write_bytes(staging.archive_bytes('new.csv', member))
            index = build_index(instance.baseline)
            self.assertEqual(index['counts']['row_count'], 20009)
            write_index(instance.args[2], index)
            bootstrap(instance.baseline, instance.args[2], instance.args[1], instance.args[3], instance.args[4], instance.args[5])
            instance.stage()
            original_path = type(instance.baseline).path
            def no_historical_read(obj, rel):
                if rel.endswith('.rows.jsonl'):
                    raise AssertionError('publication read historical canonical rows')
                return original_path(obj, rel)
            with mock.patch.object(type(instance.baseline), 'path', no_historical_read):
                result = publish(*instance.args)
            self.assertEqual(result['row_count'], 20012)
            q3 = execute_query_definition('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'}, instance.baseline, instance.args[2])
            self.assertTrue(any(r['business_date']=='2016-01-06' for r in q3['rows']))
        finally:
            instance.tearDown()
