"""B5 selected-generation reader coverage, with disposable synthetic data."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

from tests import test_incremental_staging as staging
from serving.incremental_publication import publish
from serving.index import build_index, write_index
from serving.saved import create_saved, execute_saved, execute_query_definition
from serving.query import QueryError
from ui.api import UiApi


class CompositeReadersTests(unittest.TestCase):
    setUp = staging.StagingTests.setUp
    tearDown = staging.StagingTests.tearDown
    stage = staging.StagingTests.stage

    def init(self):
        write_index(self.args[2], build_index(self.baseline))
        self.stage()
        return publish(*self.args)

    def test_normal_app_q7_q10_saved_and_history_select_composite(self):
        published = self.init()
        api = UiApi(self.baseline, self.args[2], self.args[3], self.args[4])  # no --registry
        status = api.status()
        self.assertEqual(status['composite']['generation'], published['generation'])
        params = {'symbol': 'RELIANCE', 'series': 'EQ'}
        result = api.query({'mode':'Q3-instrument', 'params':params})['query']
        delta = next(row for row in result['rows'] if row['business_date'] == '2016-01-06')
        detail = api.query({'mode':'Q7-record-detail', 'params':{'source_file':delta['serving']['source_file'], 'source_line_number':delta['source_line_number']}})['query']
        self.assertEqual(detail['row']['provenance'], delta['provenance'])
        self.assertEqual(detail['archive']['digest'], delta['provenance']['archive_sha256'])
        self.assertEqual(detail['archive']['state'], 'PUBLISHED')
        self.assertEqual(detail['archive']['generation'], published['generation'])
        self.assertEqual(detail['reconciliation_availability'], 'not-published-for-incremental-input')
        baseline_row = next(row for row in result['rows'] if row['business_date'] != '2016-01-06')
        baseline_detail = api.query({'mode':'Q7-record-detail', 'params':{'source_file':baseline_row['serving']['source_file'], 'source_line_number':baseline_row['source_line_number']}})['query']
        self.assertNotIn('reconciliation_availability', baseline_detail)
        qualification = api.query({'mode':'Q10-qualification', 'params':{}})['query']
        self.assertIn('qualified-baseline-only', qualification['subject_scope'])
        self.assertEqual(qualification['composite_generation'], published['generation'])
        create_saved(self.args[3], 'sel', 'Q3-instrument', params)
        saved = execute_saved(self.args[3], 'sel', self.baseline, self.args[2])
        self.assertEqual(saved['rows'], result['rows'])
        hist = api.history_record({'mode':'Q3-instrument', 'params':params})
        self.assertEqual(hist['outcome'], 'success')
        self.assertEqual(hist['query']['rows'], result['rows'])
        for mode in ('Q6-calendar', 'Q8-data-quality', 'Q9-archive-inventory'):
            response, body = api.dispatch('POST', '/api/query', {'mode':mode, 'params':{}})
            self.assertEqual(response, 200, body)
            query = body['query']
            self.assertEqual(query.get('composite_generation', query.get('summary', {}).get('composite_generation')), published['generation'])
            create_saved(self.args[3], mode.lower(), mode, {})
            self.assertEqual(execute_saved(self.args[3], mode.lower(), self.baseline, self.args[2]), query)
            self.assertEqual(api.history_record({'mode':mode, 'params':{}})['query'], query)

    def test_normal_server_restart_selects_durable_binding(self):
        published = self.init()
        self.source.unlink()  # restart uses durable state, not source archives
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        cmd = [sys.executable, '-m', 'ui', '--package', str(self.pkg), '--state', self.args[2],
               '--saved-state', self.args[3], '--history-state', self.args[4], '--port', str(port)]
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(200):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=1) as resp:
                        status = json.load(resp)
                    break
                except OSError:
                    if proc.poll() is not None:
                        self.fail('server exited: %s' % (proc.communicate(),))
                    time.sleep(.05)
            else:
                self.fail('server did not start')
            self.assertEqual(status['composite']['generation'], published['generation'])
            payload = json.dumps({'mode':'Q3-instrument','params':{'symbol':'RELIANCE','series':'EQ'}}).encode()
            req = urllib.request.Request('http://127.0.0.1:%d/api/query' % port, data=payload,
                                         headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                query = json.load(resp)['query']
            self.assertTrue(any(row['business_date'] == '2016-01-06' for row in query['rows']))
        finally:
            proc.terminate(); proc.communicate(timeout=10)

    def test_serving_cli_uses_bound_generation_and_scoped_readers(self):
        self.init()
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        common = ['--package', str(self.pkg), '--state', self.args[2]]
        proc = subprocess.run([sys.executable, '-m', 'serving', 'query', *common, 'RELIANCE', 'EQ'], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(any(r['business_date'] == '2016-01-06' for r in json.loads(proc.stdout)['rows']))
        proc = subprocess.run([sys.executable, '-m', 'serving', 'quality', *common], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['reconciliation']['incremental_availability'], 'not-published')
        for command in (['query', *common, '--calendar', '--from', '2016-01-06', '--to', '2016-01-06'], ['inventory', *common]):
            proc = subprocess.run([sys.executable, '-m', 'serving', *command], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertTrue(result.get('composite_generation') or result.get('summary', {}).get('composite_generation'))

    def test_invalid_or_mismatched_binding_fails_closed(self):
        self.init()
        path = Path(self.args[2], 'composite_registry.json')
        original = path.read_text()
        path.write_text('{bad json', encoding='utf8')
        with self.assertRaises(QueryError):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        doc = json.loads(original)
        doc['registry_root'] = str(Path(self.tmp.name, 'elsewhere'))
        path.write_text(json.dumps(doc), encoding='utf8')
        with self.assertRaisesRegex(QueryError, 'digest mismatch'):
            execute_query_definition('Q1-dataset', {}, self.baseline, self.args[2])
        path.write_text(original, encoding='utf8')
        wrong = Path(self.tmp.name, 'wrong-registry'); wrong.mkdir()
        with self.assertRaises(QueryError):
            from serving.composite_binding import ensure_binding
            ensure_binding(self.baseline, self.args[2], str(wrong))

    def test_nominal_m2_count_is_rejected_before_actual_processing(self):
        # This is a sentinel count, NOT a 5.7m-row fixture or a scale test.
        from serving.incremental_registry import RegistryError
        index = build_index(self.baseline)
        index['counts']['row_count'] = 5_700_000
        write_index(self.args[2], index)
        self.stage()
        with self.assertRaisesRegex(RegistryError, 'baseline exceeds bounded continuity limit'):
            publish(*self.args)
        self.assertFalse(Path(self.args[2], 'composite_registry.json').exists())

    def test_legacy_registry_can_be_bound_once_by_explicit_startup(self):
        published = self.init()
        Path(self.args[2], 'composite_registry.json').unlink()  # simulate pre-binding publication
        legacy = UiApi(self.baseline, self.args[2], self.args[3], self.args[4], registry_root=self.args[1])
        self.assertEqual(legacy.status()['composite']['generation'], published['generation'])
        normal = UiApi(self.baseline, self.args[2], self.args[3], self.args[4])
        self.assertEqual(normal.status()['composite']['generation'], published['generation'])
