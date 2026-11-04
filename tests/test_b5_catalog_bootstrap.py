"""Disposable package tests for the first B5 continuity increment."""
import contextlib
import io
import os
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests.sqlite_support import sqlite_connection
from tests import test_incremental_staging as staging
from serving.baseline import BaselineError, open_baseline
from serving.continuity_catalog import (CatalogError, FILENAME, bootstrap, open_catalog,
                                        observations_for_identity, ticker_catalog, verify_catalog)
from serving.index import build_index, write_index
from serving.symbols import build_symbol_catalog


class CatalogBootstrapTests(unittest.TestCase):
    setUp = staging.StagingTests.setUp
    tearDown = staging.StagingTests.tearDown

    def build(self):
        index = build_index(self.baseline)
        write_index(self.args[2], index)
        result = bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        return index, result

    def test_bootstrap_reuse_and_b2_catalog_parity(self):
        index, result = self.build()
        self.assertEqual(result['status'], 'BOOTSTRAPPED')
        self.assertEqual(result['row_count'], index['counts']['row_count'])
        db, meta = open_catalog(self.baseline, self.args[2])
        try:
            actual = ticker_catalog(db, meta)
            expected = build_symbol_catalog(self.baseline, index)
            self.assertEqual(set(actual['observations']), set(expected['observations']))
            invalid = list(observations_for_identity(db, 'INE123'))
            self.assertTrue(invalid)
            self.assertEqual(list(observations_for_identity(db, 'INE123', kind='b2')), [])
            observations = list(observations_for_identity(db, 'INE002A01018'))
            self.assertTrue(observations)
            self.assertTrue(any(row['source_values'].get('underlying_symbol') == 'RELIANCE' for _, row in observations))
            self.assertTrue(all(row['provenance']['member_name'] for _, row in observations))
        finally:
            db.close()
        with mock.patch.object(type(self.baseline), 'path', side_effect=AssertionError('baseline was reread')):
            second = bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
            self.assertEqual(second['status'], 'ALREADY-BOOTSTRAPPED')
            verify_catalog(self.baseline, self.args[2])
        self.assertEqual(result['observation_sha256'], second['observation_sha256'])

    def test_projection_corruption_and_index_corruption_fail_closed(self):
        self.build()
        path = os.path.join(self.args[2], FILENAME)
        with sqlite_connection(path) as db:
            db.execute("UPDATE observations SET raw_symbol='wrong' WHERE ordinal=1")
        with self.assertRaisesRegex(CatalogError, 'observation/index mismatch'):
            verify_catalog(self.baseline, self.args[2])
        with self.assertRaises(CatalogError):
            bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])

    def test_ticker_corruption_and_binding_mismatch_fail_closed(self):
        index, _ = self.build()
        path = os.path.join(self.args[2], FILENAME)
        with sqlite_connection(path) as db:
            db.execute("UPDATE tickers SET ticker='CORRUPT' WHERE rowid=(SELECT min(rowid) FROM tickers)")
        with self.assertRaisesRegex(CatalogError, 'ticker census or digest mismatch'):
            verify_catalog(self.baseline, self.args[2])
        index['counts']['row_count'] += 1
        write_index(self.args[2], index)
        with self.assertRaisesRegex(CatalogError, 'binding mismatch'):
            open_catalog(self.baseline, self.args[2])

    def test_interrupted_bootstrap_never_publishes_and_retry_succeeds(self):
        write_index(self.args[2], build_index(self.baseline))
        args = (self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        with mock.patch('serving.continuity_catalog.os.link', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                bootstrap(*args)
        self.assertFalse(Path(self.args[2], FILENAME).exists())
        self.assertEqual(bootstrap(*args)['status'], 'BOOTSTRAPPED')

    def test_lazy_open_does_not_hash_rows_and_detects_tamper_on_access(self):
        import serving.baseline as mod
        row_file = self.baseline.row_files()[0]
        real_sha = mod.sha256_file
        calls = []
        def track(path):
            calls.append(os.path.realpath(path))
            return real_sha(path)
        with mock.patch('serving.baseline.sha256_file', side_effect=track):
            lazy = open_baseline(str(self.pkg), spec=self.baseline.spec, verify_files=False)
        self.assertFalse(any(path.endswith('.rows.jsonl') for path in calls))
        self.assertIn('verify-02-presence-only', lazy.checks_passed)
        path = self.pkg / row_file
        before = path.read_bytes()
        try:
            path.write_bytes(before + b'corrupt')
            with self.assertRaisesRegex(BaselineError, 'verify-access'):
                lazy.path(row_file)
            with self.assertRaises(BaselineError):
                open_baseline(str(self.pkg), spec=self.baseline.spec)
        finally:
            path.write_bytes(before)

    def test_normal_ui_startup_reuses_index_without_hashing_rows(self):
        import serving.baseline as mod
        from ui import serve
        self.build()
        real_sha = mod.sha256_file
        calls = []
        def track(path):
            calls.append(os.path.realpath(path))
            return real_sha(path)
        class Server:
            def __init__(self, *_args): self.daemon_threads = False
            def serve_forever(self): pass
            def server_close(self): pass
        argv = ['--package', str(self.pkg), '--state', self.args[2], '--saved-state', self.args[3],
                '--history-state', self.args[4], '--port', '8613']
        with mock.patch('serving.baseline.sha256_file', side_effect=track), \
             mock.patch('ui.serve.ThreadingHTTPServer', Server), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(serve.main(argv), 0)
        self.assertFalse(any(path.endswith('.rows.jsonl') for path in calls))

    def test_corrupt_historical_row_is_rejected_through_real_ui_query(self):
        from ui.api import UiApi
        index = build_index(self.baseline)
        write_index(self.args[2], index)
        lazy = open_baseline(str(self.pkg), spec=self.baseline.spec, verify_files=False)
        api = UiApi(lazy, self.args[2], self.args[3], self.args[4])
        row_file = next(k for k, v in index['files'].items() if v.get('business_date_min') == '2016-01-04')
        path = self.pkg / row_file
        before = path.read_bytes()
        try:
            path.write_bytes(before + b'corrupt')
            status, response = api.dispatch('POST', '/api/query', {'mode':'Q2-date-range',
                'params':{'date_from':'2016-01-04','date_to':'2016-01-04'}})
            self.assertNotEqual(status, 200)
            self.assertEqual(response['check'], 'serving-state')
            self.assertIn('verify-access', response['detail'])
        finally:
            path.write_bytes(before)

    def test_bootstrap_cli_and_catalog_verification_cli(self):
        import subprocess, sys
        write_index(self.args[2], build_index(self.baseline))
        common = ['--package', str(self.pkg), '--registry', self.args[1], '--state', self.args[2],
                  '--saved-state', self.args[3], '--history-state', self.args[4],
                  '--legacy-root', self.args[5]['LEGACY'], '--udiff-root', self.args[5]['UDIFF']]
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        for operation in ('bootstrap', 'catalog-verify'):
            proc = subprocess.run([sys.executable, '-m', 'serving.incremental_registry', *common, operation],
                                  capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('"result":"pass"', proc.stdout)

    def test_process_exit_during_bootstrap_leaves_no_active_catalog(self):
        import subprocess, sys
        write_index(self.args[2], build_index(self.baseline))
        code = r"""
import os, sys
from serving.baseline import open_baseline
from serving.continuity_catalog import bootstrap
import serving.continuity_catalog as catalog
base=open_baseline(sys.argv[1])
catalog.os.link=lambda *_: os._exit(47)
bootstrap(base,sys.argv[3],sys.argv[2],sys.argv[4],sys.argv[5],{'LEGACY':sys.argv[6], 'UDIFF':sys.argv[7]})
"""
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-c', code, str(self.pkg), self.args[1], self.args[2],
                               self.args[3], self.args[4], self.args[5]['LEGACY'], self.args[5]['UDIFF']],
                              capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(proc.returncode, 47, proc.stderr)
        self.assertFalse(Path(self.args[2], FILENAME).exists())
        self.assertEqual(bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])['status'], 'BOOTSTRAPPED')

    def test_repeated_bootstrap_cli_does_not_hash_canonical_files(self):
        import serving.baseline as mod
        from serving.incremental_registry import main
        self.build()
        common = ['--package', str(self.pkg), '--registry', self.args[1], '--state', self.args[2],
                  '--saved-state', self.args[3], '--history-state', self.args[4],
                  '--legacy-root', self.args[5]['LEGACY'], '--udiff-root', self.args[5]['UDIFF'], 'bootstrap']
        original, calls = mod.sha256_file, []
        def track(path):
            calls.append(os.path.realpath(path))
            return original(path)
        with mock.patch('serving.baseline.sha256_file', side_effect=track), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(common), 0)
        self.assertFalse(any(path.endswith('.rows.jsonl') for path in calls))

    def test_existing_unknown_catalog_is_not_replaced(self):
        write_index(self.args[2], build_index(self.baseline))
        target = Path(self.args[2], FILENAME)
        target.write_bytes(b'user-owned unknown state')
        with self.assertRaises(CatalogError):
            bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])
        self.assertEqual(target.read_bytes(), b'user-owned unknown state')
