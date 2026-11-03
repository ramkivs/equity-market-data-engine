"""Independent B5 verification: existing read-only server restart behavior.

This is not an incremental-ingestion implementation. It uses only a disposable
synthetic package, no source-archive directory and no real M2 data.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

from serving.baseline import open_baseline
from serving.saved import create_saved
from serving.history import record_execution
from tests import serving_fixtures
from ui.serve import _ensure_index


def snapshot(root):
    root = Path(root)
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()} if root.exists() else {}


class ExistingRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.pkg, self.state, self.saved, self.history = (root / x for x in ('pkg', 'state', 'saved', 'history'))
        facts = serving_fixtures.build_fixture_package(str(self.pkg))
        self.handle = open_baseline(str(self.pkg), spec=facts['spec'])

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_existing_index_is_loaded_not_rebuilt(self):
        first = _ensure_index(self.handle, str(self.state))
        self.state.joinpath('user-owned-sentinel').write_text('retain', encoding='utf8')
        before = snapshot(self.state)
        with mock.patch('ui.serve.build_index', side_effect=AssertionError('unexpected build')), \
             mock.patch('ui.serve.write_index', side_effect=AssertionError('unexpected write')), \
             mock.patch('ui.serve.rebuild_state', side_effect=AssertionError('unexpected rebuild')):
            second = _ensure_index(self.handle, str(self.state))
        self.assertEqual(first, second)
        self.assertEqual(before, snapshot(self.state))

    def test_two_real_server_starts_reuse_state_and_leave_package_untouched(self):
        # Initialize once, then make both executions genuine restarts.
        _ensure_index(self.handle, str(self.state))
        self.state.joinpath('user-owned-sentinel').write_text('retain', encoding='utf8')
        create_saved(str(self.saved), 'existing', 'Q1-dataset', {})
        record_execution(str(self.history), 'Q1-dataset', {}, self.handle, str(self.state))
        package_before, state_before = snapshot(self.pkg), snapshot(self.state)
        saved_before, history_before = snapshot(self.saved), snapshot(self.history)
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        results = []
        for module in ('ui', 'ui.serve'):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            args = [sys.executable, '-m', module, '--package', str(self.pkg), '--state', str(self.state),
                    '--saved-state', str(self.saved), '--history-state', str(self.history), '--port', str(port)]
            proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                url = 'http://127.0.0.1:%d' % port
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        self.fail('server exited: %s' % (proc.communicate(),))
                    try:
                        with urllib.request.urlopen(url + '/api/status', timeout=1) as response:
                            self.assertEqual(json.load(response)['result'], 'pass')
                        break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.05)
                else:
                    self.fail('server did not start')
                for route in ('/api/saved', '/api/history'):
                    with urllib.request.urlopen(url + route, timeout=5) as response:
                        self.assertEqual(json.load(response)['count'], 1)
                request = urllib.request.Request(url + '/api/query', data=json.dumps({'mode': 'Q1-dataset', 'params': {}}).encode(),
                                                 headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(request, timeout=5) as response:
                    results.append(json.load(response)['query'])
            finally:
                proc.terminate()
                proc.communicate(timeout=10)
            self.assertEqual(snapshot(self.pkg), package_before)
            self.assertEqual(snapshot(self.state), state_before)
            self.assertEqual(snapshot(self.saved), saved_before)
            self.assertEqual(snapshot(self.history), history_before)
        self.assertEqual(results[0], results[1])
