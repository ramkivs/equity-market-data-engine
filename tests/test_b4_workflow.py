"""B4 bounded continuity, legacy EQ and executable UI entry points."""
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock
from pathlib import Path

from tests import serving_fixtures
from serving.baseline import open_baseline
from serving.continuity_view import MAX_AUTOMATIC_ROWS, get_continuity
from serving.index import build_index, write_index
from serving.query import parse_associations, query_associations, query_filters
from serving.saved import execute_query_definition
from serving.w2_continuity import build_continuity, canonical_rows
from ui.derive import quick_filter_params


class B4WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pkg = os.path.join(self.tmp.name, 'pkg')
        facts = serving_fixtures.build_fixture_package(self.pkg)
        self.handle = open_baseline(self.pkg, spec=facts['spec'])
        self.index = build_index(self.handle)
        self.state = os.path.join(self.tmp.name, 'state')
        write_index(self.state, self.index)

    def tearDown(self):
        self.tmp.cleanup()

    def test_eq_preset_includes_legacy_without_segment(self):
        filters = quick_filter_params('EQ (all)')['params']['filters']
        rows = query_filters(self.handle, self.index, filters)
        self.assertTrue(any(row['format_family'] == 'legacy13' and not row['source_values']['segment'] for row in rows))
        self.assertTrue(all(row['source_values']['series'] == 'EQ' for row in rows))

    def test_q5_derives_matching_b3_without_modifying_package(self):
        before = {os.path.relpath(os.path.join(d, f), self.pkg): Path(d, f).read_bytes()
                  for d, _, fs in os.walk(self.pkg) for f in fs}
        original = parse_associations(self.handle)
        response = execute_query_definition('Q5-association', {'security_id': 'INE002A01018'}, self.handle, self.state)
        self.assertEqual(response['continuity']['availability'], 'available')
        expected = build_continuity(canonical_rows(self.handle), self.handle.manifest_digest)
        group = next(g for g in expected['identities'] if g['security_id'] == 'INE002A01018')
        summary = response['records'][0]['serving']['continuity'][0]
        self.assertEqual(summary['status'], group['status'])
        self.assertEqual(summary['transitions'], group['transitions'])
        self.assertEqual(summary['intervals'], [{k: i[k] for k in ('symbol', 'observed_from', 'observed_to')} for i in group['intervals']])
        self.assertEqual(parse_associations(self.handle), original)
        for relative, data in before.items():
            with open(os.path.join(self.pkg, relative), 'rb') as f:
                self.assertEqual(f.read(), data)

    def test_large_or_untrusted_count_never_scans(self):
        for count in (MAX_AUTOMATIC_ROWS + 1, None, -1, True):
            idx = copy.deepcopy(self.index)
            idx['counts']['row_count'] = count
            with mock.patch('serving.continuity_view.canonical_rows', side_effect=AssertionError('must not scan')):
                status, document = get_continuity(self.handle, idx)
                self.assertEqual(status['availability'], 'unavailable')
                self.assertIsNone(document)
        idx = copy.deepcopy(self.index)
        idx['counts']['row_count'] = MAX_AUTOMATIC_ROWS + 1
        rows = query_associations(self.handle, idx, security_id='INE002A01018', documents=parse_associations(self.handle))
        self.assertTrue(rows)
        self.assertEqual(rows[0]['serving']['continuity'], [])

    def test_hard_limit_when_index_count_is_inaccurate(self):
        from serving import continuity_view
        with mock.patch.dict(continuity_view._cache, {}, clear=True), \
             mock.patch('serving.continuity_view.canonical_rows', return_value=iter([None] * (MAX_AUTOMATIC_ROWS + 1))), \
             mock.patch('serving.continuity_view.build_continuity', side_effect=lambda rows, digest: list(rows)):
            status, result = get_continuity(self.handle, self.index)
        self.assertEqual(status['availability'], 'error')
        self.assertIn('row limit exceeded', status['reason'])
        self.assertIsNone(result)

    def test_both_module_entrypoints_start_and_serve(self):
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        for module in ('ui', 'ui.serve'):
            help_run = subprocess.run([sys.executable, '-m', module, '--help'], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(help_run.returncode, 0, help_run.stderr)
            self.assertIn('--package', help_run.stdout)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            root = os.path.join(self.tmp.name, module.replace('.', '-'))
            args = [sys.executable, '-m', module, '--package', self.pkg, '--state', root + '-state',
                    '--saved-state', root + '-saved', '--history-state', root + '-history', '--port', str(port)]
            proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        self.fail('server exited: ' + proc.communicate()[0])
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:%s/api/status' % port, timeout=1) as resp:
                            self.assertEqual(json.load(resp)['result'], 'pass')
                        break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.05)
                else:
                    self.fail('server did not start: ' + module)
            finally:
                proc.terminate()
                proc.communicate(timeout=10)
