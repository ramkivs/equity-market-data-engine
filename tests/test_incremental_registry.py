"""Disposable baseline registry and D21 conflict tests; no M2 data."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests import serving_fixtures as fixtures
from serving.baseline import open_baseline
from serving.incremental_registry import RegistryError, bindings, conflicts, initialize, inspect


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.pkg = base / 'pkg'
        facts = fixtures.build_fixture_package(str(self.pkg))
        self.baseline = open_baseline(str(self.pkg), spec=facts['spec'])
        self.reg, self.state, self.saved, self.history = [str(base / n) for n in ('registry', 'state', 'saved', 'history')]
        self.roots = {'LEGACY': str(base / 'legacy'), 'UDIFF': str(base / 'udiff')}
        for p in self.roots.values():
            Path(p).mkdir()
        self.name = 'fix-leg-2016-01-04.csv'
        self.source = Path(self.roots['LEGACY']) / self.name
        self.source.write_bytes(fixtures._member_bytes(self.name))
        self.args = (self.baseline, self.reg, self.state, self.saved, self.history, self.roots)
        self.before = {str(p.relative_to(self.pkg)): p.read_bytes() for p in self.pkg.rglob('*') if p.is_file()}

    def tearDown(self):
        self.assertEqual(self.before, {str(p.relative_to(self.pkg)): p.read_bytes() for p in self.pkg.rglob('*') if p.is_file()})
        self.tmp.cleanup()

    def setup_registry(self):
        with mock.patch('serving.incremental_registry.sha256_file', side_effect=AssertionError('must not read archives')):
            result = initialize(*self.args)
        self.assertEqual(result['accepted'], fixtures.EXPECTED_MEMBERS)

    def scan(self, name=None, date='2016-01-04', scan_id='synthetic-scan', current=None):
        return inspect(*self.args, 'LEGACY', name or self.name, date, scan_id, current or bindings(self.baseline))

    def test_bootstrap_and_noop_and_stale(self):
        self.setup_registry()
        self.assertEqual(self.scan()['status'], 'UNCHANGED')
        stale = dict(bindings(self.baseline), engine_sha256='new-version')
        self.assertEqual(self.scan(current=stale)['status'], 'STALE')
        self.assertEqual(conflicts(*self.args), [])
        with self.assertRaises(FileExistsError):
            initialize(*self.args)
        self.assertEqual(self.scan()['status'], 'UNCHANGED')

    def test_new_duplicate_changed_and_restart(self):
        self.setup_registry()
        (self.source.parent / 'other.csv').write_bytes(self.source.read_bytes())
        self.assertEqual(self.scan('other.csv', '2016-01-05')['status'], 'ANOMALOUS-DUPLICATE-CONTENT')
        (self.source.parent / 'new.csv').write_bytes(b'new,unvalidated')
        self.assertEqual(self.scan('new.csv', '2025-01-01')['status'], 'NEW-UNVALIDATED')
        self.source.write_bytes(b'changed')
        changed = self.scan(scan_id='first')
        self.assertEqual(changed['status'], 'CHANGED-CONFLICT-UNRESOLVED')
        self.assertEqual(changed['prior']['archive_sha256_observed_raw_bytes'], fixtures.sha256_bytes(fixtures._member_bytes(self.name)))
        self.scan(scan_id='second')
        self.assertEqual(len(conflicts(*self.args)), 1)
        self.assertEqual(conflicts(*self.args)[0]['scan_id'], 'first')
        self.assertEqual(self.scan('new.csv', '2025-01-01')['status'], 'NEW-UNVALIDATED')
        self.source.write_bytes(fixtures._member_bytes(self.name))
        self.assertEqual(self.scan()['status'], 'UNCHANGED')
        self.assertEqual(len(conflicts(*self.args)), 1)

    def test_conflict_transaction_rolls_back_after_failure(self):
        self.setup_registry()
        self.source.write_bytes(b'changed')
        with mock.patch('serving.incremental_registry._json', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.scan()
        self.assertEqual(conflicts(*self.args), [])
        self.assertEqual(self.scan()['status'], 'CHANGED-CONFLICT-UNRESOLVED')

    def test_cli_initialization_inspection_and_conflict_listing(self):
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        prefix = [sys.executable, '-m', 'serving.incremental_registry', '--package', str(self.pkg), '--registry', self.reg,
                  '--state', self.state, '--saved-state', self.saved, '--history-state', self.history,
                  '--legacy-root', self.roots['LEGACY'], '--udiff-root', self.roots['UDIFF']]
        def run(*args):
            proc = subprocess.run(prefix + list(args), env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return json.loads(proc.stdout)['data']
        self.assertEqual(run('init')['accepted'], fixtures.EXPECTED_MEMBERS)
        self.source.write_bytes(b'changed over the wire')
        args = ['inspect', '--root', 'LEGACY', '--relative-path', self.name, '--date', '2016-01-04',
                '--scan-id', 'cli-scan', '--current-bindings', json.dumps(bindings(self.baseline))]
        self.assertEqual(run(*args)['status'], 'CHANGED-CONFLICT-UNRESOLVED')
        self.assertEqual(run('conflicts')[0]['scan_id'], 'cli-scan')

    def test_fail_closed_on_overlap_malformed_and_missing_registry(self):
        with self.assertRaises(RegistryError):
            self.scan()
        with self.assertRaises(ValueError):
            initialize(self.baseline, str(self.pkg / 'nested'), self.state, self.saved, self.history, self.roots)
        self.setup_registry()
        with self.assertRaises(RegistryError):
            self.scan('../outside', '2016-01-04')
        with self.assertRaises(RegistryError):
            self.scan(date='garbage')
        with self.assertRaises(RegistryError):
            inspect(*self.args, 'LEGACY', self.name, '2016-01-04', 'x', {})


if __name__ == '__main__':
    unittest.main()
