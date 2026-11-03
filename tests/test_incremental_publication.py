"""Bounded opt-in composite integration tests (synthetic packages only)."""
import json
import os
import sqlite3
import unittest
from unittest import mock
from tests.sqlite_support import sqlite_connection
from tests import test_incremental_staging as staging
from tests import serving_fixtures as fixtures
from serving.incremental_publication import publish, active_snapshot
from serving.incremental_registry import RegistryError
from serving.index import build_index, write_index
from serving.saved import execute_query_definition


class PublicationTests(unittest.TestCase):
    setUp = staging.StagingTests.setUp
    tearDown = staging.StagingTests.tearDown
    stage = staging.StagingTests.stage

    def init(self):
        write_index(self.args[2], build_index(self.baseline))
        return self.stage()

    def test_publish_q3_q4_q5_and_noop(self):
        self.init()
        result = publish(*self.args)
        self.assertEqual(result['status'], 'PUBLISHED')
        snapshot = active_snapshot(self.baseline, self.args[1], self.args[2])
        def run(mode, params):
            return execute_query_definition(mode, params, self.baseline, self.args[2], composite=snapshot)
        q3 = run('Q3-instrument', {'symbol':'RELIANCE','series':'EQ'})
        q4 = run('Q4-filter', {'filters': {'symbol':'RELIANCE','series':'EQ'}})
        q5 = run('Q5-association', {'security_id':'INE002A01018'})
        self.assertTrue(any(x['business_date'] == '2016-01-06' for x in q3['rows']))
        self.assertEqual(len(q3['rows']), len(q4['rows']))
        self.assertEqual(q5['continuity']['availability'], 'available')
        self.assertTrue(any(g['intervals'][-1]['observed_to'] >= '2016-01-06' for r in q5['records'] for g in r['serving']['continuity']))
        with mock.patch('serving.incremental_publication._w2', side_effect=AssertionError('unchanged run regenerated W2')), \
             mock.patch('serving.incremental_publication.build_continuity', side_effect=AssertionError('unchanged run regenerated B3')):
            self.assertEqual(publish(*self.args)['status'], 'UNCHANGED')

    def test_composite_b3_matches_direct_baseline_plus_delta(self):
        from serving.w2_continuity import build_continuity, canonical_rows
        self.init(); publish(*self.args)
        view, _ = active_snapshot(self.baseline, self.args[1], self.args[2])
        pairs = list(canonical_rows(self.baseline))
        for source, text in sorted(view.payload['delta'].items()):
            pairs.extend((source, json.loads(line)) for line in text.splitlines() if line.strip())
        expected = build_continuity(pairs, self.baseline.manifest_digest)
        self.assertEqual(view.payload['b3'], expected)
        for source, text in view.payload['delta'].items():
            for line in text.splitlines():
                row = json.loads(line)
                self.assertTrue(row['provenance']['run_id'].startswith('incremental-'))
                self.assertEqual(row['provenance']['archive_sha256'], source.split('/')[1].split('.')[0])

    def test_limit_no_writes(self):
        self.init()
        with mock.patch('serving.incremental_publication.LIMIT', 1):
            with self.assertRaises(RegistryError):
                publish(*self.args)
        self.assertIsNone(active_snapshot(self.baseline, self.args[1], self.args[2]))

    def test_application_http_dynamic_selection_and_restart(self):
        import socket, subprocess, sys, time, urllib.request
        from pathlib import Path
        from tests.test_incremental_staging import archive_bytes
        self.init()  # legacy delta on 2016-01-06
        original = fixtures._member_bytes('fix-udf-2024-03-05.csv')
        newer = original.replace(b'2024-03-05', b'2025-03-06').replace(b'RELIANCE', b'NEWRELIANCE')
        Path(self.args[-1]['UDIFF'], 'newer.zip').write_bytes(archive_bytes('newer.csv', newer))
        from serving.incremental_staging import prepare
        prepare(*self.args, 'UDIFF', 'newer.zip', '2025-03-06', 'next')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        cmd = [sys.executable, '-m', 'ui', '--package', str(self.pkg), '--state', self.args[2],
               '--saved-state', self.args[3], '--history-state', self.args[4], '--registry', self.args[1], '--port', str(port)]
        def start():
            p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(200):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=1):
                        return p
                except OSError:
                    if p.poll() is not None:
                        self.fail('server exited: %s' % (p.communicate(),))
                    time.sleep(.05)
            p.terminate(); p.communicate(timeout=5); self.fail('server timeout')
        def query(mode, params):
            req = urllib.request.Request('http://127.0.0.1:%d/api/query' % port, data=json.dumps({'mode':mode,'params':params}).encode(),
                                         headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)['query']
        proc = start()
        try:
            self.assertEqual(query('Q3-instrument', {'symbol':'NEWRELIANCE','series':'EQ'})['result_count'], 0)
            result = publish(*self.args)
            after = query('Q3-instrument', {'symbol':'NEWRELIANCE','series':'EQ'})
            self.assertGreater(after['result_count'], 1)
            self.assertTrue(any(r['business_date']=='2025-03-06' for r in after['rows']))
            filtered = query('Q4-filter', {'filters':{'symbol':'NEWRELIANCE','series':'EQ'}})
            self.assertEqual(filtered['result_count'], after['result_count'])
            assoc = query('Q5-association', {'security_id':'INE002A01018'})
            groups = [g for r in assoc['records'] for g in r['serving']['continuity']]
            self.assertTrue(any(any(t['to_symbol']=='NEWRELIANCE' for t in g['transitions']) for g in groups))
        finally:
            proc.terminate(); proc.communicate(timeout=10)
        # Restart must not read candidate archives or re-run the canonical engine.
        Path(self.args[-1]['UDIFF'], 'newer.zip').unlink()
        self.source.unlink()
        proc = start()
        try:
            self.assertEqual(query('Q3-instrument', {'symbol':'NEWRELIANCE','series':'EQ'}), after)
        finally:
            proc.terminate(); proc.communicate(timeout=10)

    def test_transaction_failure_rolls_back_and_retry(self):
        self.init()
        dbpath = os.path.join(self.args[1], 'source_registry.sqlite3')
        from serving.incremental_publication import _schema
        with sqlite_connection(dbpath) as db:
            _schema(db)
            db.execute("CREATE TRIGGER fail_active BEFORE INSERT ON composite_active BEGIN SELECT RAISE(ABORT, 'interrupted'); END")
        with self.assertRaises(RegistryError):
            publish(*self.args)
        with sqlite_connection(dbpath) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS)
            db.execute('DROP TRIGGER fail_active')
        self.assertEqual(publish(*self.args)['status'], 'PUBLISHED')

    def test_changed_source_is_not_published(self):
        self.init()
        self.source.write_bytes(b'changed after staging')
        with self.assertRaisesRegex(RegistryError, 'changed after staging'):
            publish(*self.args)
        self.assertIsNone(active_snapshot(self.baseline, self.args[1], self.args[2]))

    def test_application_request_is_pinned_during_concurrent_switch(self):
        import threading
        from pathlib import Path
        from tests.test_incremental_staging import archive_bytes
        from serving.incremental_staging import prepare
        from ui.api import UiApi
        import ui.api as api_mod
        self.init()
        first = publish(*self.args)
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4], registry_root=self.args[1])
        first_count = api.query({'mode':'Q1-dataset','params':{}})['query']['summary']['row_count']
        data = fixtures._member_bytes('fix-udf-2024-03-05.csv').replace(b'2024-03-05', b'2025-03-06')
        Path(self.args[-1]['UDIFF'], 'later.zip').write_bytes(archive_bytes('later.csv', data))
        prepare(*self.args, 'UDIFF', 'later.zip', '2025-03-06', 'later')
        ready, proceed, result = threading.Event(), threading.Event(), []
        original = api_mod.execute_query_definition
        def delayed(*args, **kwargs):
            ready.set()
            if not proceed.wait(10):
                raise RuntimeError('test timed out')
            return original(*args, **kwargs)
        def reader():
            try:
                result.append(api.query({'mode':'Q1-dataset','params':{}})['query']['summary']['row_count'])
            except Exception as exc:
                result.append(exc)
        with mock.patch('ui.api.execute_query_definition', side_effect=delayed):
            thread = threading.Thread(target=reader); thread.start()
            self.assertTrue(ready.wait(5))
            second = publish(*self.args)
            proceed.set(); thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(result, [first_count])
        self.assertGreater(api.query({'mode':'Q1-dataset','params':{}})['query']['summary']['row_count'], first_count)

    def test_abrupt_exit_before_pointer_commit_rolls_back(self):
        import subprocess, sys
        from serving.incremental_publication import _schema
        self.init()
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        with sqlite_connection(path) as db:
            _schema(db)
            db.execute("CREATE TRIGGER abrupt BEFORE INSERT ON composite_active BEGIN SELECT exit_now(); END")
        code = r'''
import json,os,sys
from serving.baseline import open_baseline
from serving.incremental_registry import bindings
from serving import incremental_staging
import serving.incremental_publication as pub
a=json.loads(sys.argv[1]); base=open_baseline(a[0])
incremental_staging.runtime_bindings=lambda: bindings(base)
original=pub._open
def open_with_exit(*args):
    db,meta=original(*args)
    db.create_function('exit_now',0,lambda:os._exit(47))
    return db,meta
pub._open=open_with_exit
pub.publish(base,*a[1:])
'''
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-c', code, json.dumps([str(self.pkg), *self.args[1:]])], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 47, proc.stderr)
        with sqlite_connection(path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM composite_active').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS)
            db.execute('DROP TRIGGER abrupt')
        self.assertEqual(publish(*self.args)['status'], 'PUBLISHED')

    def test_published_input_change_is_d21_conflict_and_keeps_reader_state(self):
        from serving.incremental_registry import conflicts
        from ui.api import UiApi
        self.init()
        first = publish(*self.args)
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4], registry_root=self.args[1])
        before = api.query({'mode':'Q3-instrument','params':{'symbol':'RELIANCE','series':'EQ'}})
        self.source.write_bytes(b'changed after publication')
        with self.assertRaisesRegex(RegistryError, 'changed after staging'):
            publish(*self.args)
        self.assertEqual(len(conflicts(*self.args)), 1)
        finding = conflicts(*self.args)[0]
        self.assertEqual(finding['status'], 'CHANGED-CONFLICT-UNRESOLVED')
        self.assertEqual(finding['prior_run_id'], finding['prior']['run_id'])
        self.assertEqual(finding['prior_manifest_sha256'], first['generation'])
        self.assertEqual(api.query({'mode':'Q3-instrument','params':{'symbol':'RELIANCE','series':'EQ'}}), before)
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].manifest_digest, first['generation'])

    def test_saved_queries_use_selected_generation_and_corruption_fails_closed(self):
        from serving.saved import create_saved
        from ui.api import UiApi
        self.init(); publish(*self.args)
        create_saved(self.args[3], 'ticker', 'Q3-instrument', {'symbol':'RELIANCE','series':'EQ'})
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4], registry_root=self.args[1])
        out = api.saved_run('ticker')['query']
        self.assertTrue(any(row['business_date'] == '2016-01-06' for row in out['rows']))
        with sqlite_connection(os.path.join(self.args[1], 'source_registry.sqlite3')) as db:
            db.execute("UPDATE composite_generations SET payload=payload || 'tampered'")
        status, document = api.dispatch('POST', '/api/query', {'mode':'Q1-dataset', 'params':{}})
        self.assertNotEqual(status, 200)
        self.assertEqual(document['check'], 'composite-unavailable')

    def test_failed_second_publication_preserves_first_generation(self):
        from pathlib import Path
        from tests.test_incremental_staging import archive_bytes
        from serving.incremental_staging import prepare
        self.init(); first = publish(*self.args)
        data = fixtures._member_bytes('fix-udf-2024-03-05.csv').replace(b'2024-03-05', b'2025-03-06')
        Path(self.args[-1]['UDIFF'], 'next.zip').write_bytes(archive_bytes('next.csv', data))
        prepare(*self.args, 'UDIFF', 'next.zip', '2025-03-06', 'next')
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        with sqlite_connection(path) as db:
            db.execute("CREATE TRIGGER block_switch BEFORE UPDATE ON composite_active BEGIN SELECT RAISE(ABORT, 'interrupted'); END")
        with self.assertRaises(RegistryError):
            publish(*self.args)
        self.assertEqual(active_snapshot(self.baseline, self.args[1], self.args[2])[0].manifest_digest, first['generation'])
        with sqlite_connection(path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM composite_generations').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS + 1)
            db.execute('DROP TRIGGER block_switch')
        second = publish(*self.args)
        self.assertNotEqual(second['generation'], first['generation'])

    def test_calendar_uses_manifest_when_baseline_calendar_absent(self):
        from ui.api import UiApi
        self.init(); publish(*self.args)
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4], registry_root=self.args[1])
        status, body = api.dispatch('POST', '/api/query', {'mode':'Q6-calendar', 'params':{}})
        self.assertEqual(status, 200, body)
        result = body['query']
        self.assertIn('baseline-calendar-absent', result['scope'])
        day = next(item for item in result['records'] if item['trade_date'] == '2016-01-06')
        self.assertTrue(day['file_present'])
        self.assertIn('new.zip', day['member_names'])

    def test_publication_cli_commits_selected_generation(self):
        import subprocess, sys
        self.init()
        base, reg, state, saved, history, roots = self.args
        argv = ['--package', base.root, '--registry', reg, '--state', state, '--saved-state', saved,
                '--history-state', history, '--legacy-root', roots['LEGACY'], '--udiff-root', roots['UDIFF'], 'publish']
        code = r'''
import json,sys
from serving.baseline import open_baseline
from serving.incremental_registry import main,bindings
from serving import incremental_staging
args=json.loads(sys.argv[1]); b=open_baseline(args[1])
incremental_staging.runtime_bindings=lambda: bindings(b)
raise SystemExit(main(args))
'''
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-c', code, json.dumps(argv)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc['data']['status'], 'PUBLISHED')
        self.assertEqual(active_snapshot(self.baseline, reg, state)[0].manifest_digest, doc['data']['generation'])
