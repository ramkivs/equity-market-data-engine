"""B1 regressions: synthetic packages and disposable state only."""
import json
import os
import queue
import threading
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import serving_fixtures
from serving.archive import D01InventoryError, load_d01_inventory
from serving.baseline import open_baseline
from serving.history import load_history, record_execution
from serving.index import build_index, load_index, write_index, ServingIndexError
from serving.paths import RootLayoutError, resolved, validate_roots
from serving.rebuild import rebuild_state
from serving.saved import create_saved, load_saved, execute_saved
from ui.api import UiApi
from ui.serve import _ensure_index, main as ui_main

REPO = Path(__file__).resolve().parents[1]


class StateSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pkg = self.root / 'pkg'
        facts = serving_fixtures.build_fixture_package(str(self.pkg))
        self.baseline = open_baseline(str(self.pkg), spec=facts['spec'])
        self.state = self.root / 'state'
        self.saved = self.root / 'saved'
        self.hist = self.root / 'history'
        self.document = build_index(self.baseline)
        write_index(str(self.state), self.document)

    def tearDown(self):
        self.temp.cleanup()

    def package_snapshot(self):
        return {str(p.relative_to(self.pkg)): p.read_bytes() for p in self.pkg.rglob('*') if p.is_file()}

    def test_layout_equal_nested_alias_and_sibling_prefix(self):
        for a, b in [(self.state, self.state), (self.state, self.state / 'child'), (self.state, self.root)]:
            with self.subTest(a=a, b=b), self.assertRaises(RootLayoutError):
                validate_roots(state=a, saved=b)
        validate_roots(state=self.state, saved=self.root / 'state-other')
        alias = self.root / 'alias'
        try:
            alias.symlink_to(self.pkg, target_is_directory=True)
        except OSError as exc:
            self.skipTest('symlink unavailable: %s' % exc)
        with self.assertRaises(RootLayoutError):
            validate_roots(package=self.pkg, state=alias / 'new')
        with self.assertRaises(RootLayoutError):
            create_saved(str(alias / 'new'), 'a', 'Q8-data-quality', {})

    def test_direct_ui_and_cli_reject_package_writes(self):
        before = self.package_snapshot()
        for action in (
            lambda: write_index(str(self.pkg / 'new'), self.document),
            lambda: rebuild_state(self.baseline, str(self.pkg)),
            lambda: create_saved(str(self.pkg / 'saved'), 'a', 'Q8-data-quality', {}),
            lambda: record_execution(str(self.pkg / 'hist'), 'Q8-data-quality', {}, self.baseline, str(self.state)),
            lambda: UiApi(self.baseline, str(self.state), str(self.pkg / 'saved'), str(self.hist)),
        ):
            with self.assertRaises(RootLayoutError):
                action()
        self.assertEqual(ui_main(['--package', str(self.pkg), '--state', str(self.pkg / 'bad'), '--saved-state', str(self.saved), '--history-state', str(self.hist)]), 3)
        env = dict(os.environ, PYTHONPATH=str(REPO / 'src'), PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-m', 'serving', 'build', '--package', str(self.pkg), '--state', str(self.pkg / 'new')], cwd=str(self.root), env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('root-layout', result.stdout)
        self.assertEqual(before, self.package_snapshot())

    def test_index_compatibility_interruption_and_restart_preserve_user_stores(self):
        create_saved(str(self.saved), 'a', 'Q8-data-quality', {})
        record_execution(str(self.hist), 'Q8-data-quality', {}, self.baseline, str(self.state))
        before_saved = load_saved(str(self.saved))
        before_history = load_history(str(self.hist))
        self.assertEqual(load_index(str(self.state), self.baseline)[0]['format'], 'serving-index/1.2')
        with patch('ui.serve.build_index', side_effect=AssertionError('unnecessary rebuild')):
            _ensure_index(self.baseline, str(self.state))
        # Simulate crash between the two atomic replacements: mismatched pair fails closed.
        changed = dict(self.document, counts=dict(self.document['counts'], row_count=999))
        from serving import index
        original = index._write_text
        calls = []
        def interrupt(path, text):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('simulated interruption')
            original(path, text)
        with patch('serving.index._write_text', side_effect=interrupt), self.assertRaises(OSError):
            write_index(str(self.state), changed)
        with self.assertRaises(ServingIndexError):
            load_index(str(self.state), self.baseline)
        _ensure_index(self.baseline, str(self.state))
        self.assertEqual(load_index(str(self.state), self.baseline)[0], self.document)
        stale = dict(self.document, package=dict(self.document['package'], run_id='old'))
        write_index(str(self.state), stale)
        (self.state / '.interrupted.part').write_text('keep', encoding='utf-8')
        _ensure_index(self.baseline, str(self.state))
        self.assertEqual(load_index(str(self.state), self.baseline)[0], self.document)
        self.assertEqual((self.state / '.interrupted.part').read_text(encoding='utf-8'), 'keep')
        self.assertEqual(load_saved(str(self.saved)), before_saved)
        self.assertEqual(load_history(str(self.hist)), before_history)
        self.assertEqual(before_saved['format'], 'serving-saved-queries/1.0')
        self.assertEqual(before_history['format'], 'serving-query-history/1.0')

    def test_index_file_alias_does_not_overwrite_target(self):
        target = self.pkg / 'RUN_COMPLETE.json'
        before = target.read_bytes()
        index_file = self.state / 'serving_index.json'
        index_file.unlink()
        try:
            index_file.symlink_to(target)
        except OSError as exc:
            self.skipTest('symlink unavailable: %s' % exc)
        write_index(str(self.state), self.document)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(index_file.is_symlink())

    def test_q9_cli_and_ui_propagate_explicit_repository(self):
        from serving import cli
        with patch('serving.cli._open', return_value=self.baseline), \
             patch('serving.cli.load_d01_inventory', return_value={}) as inv, \
             patch('serving.cli.query_archive_inventory', return_value={'ok': True}), \
             patch('serving.cli._print_json'):
            self.assertEqual(cli.main(['inventory', '--package', str(self.pkg), '--m2', '--repo', str(REPO)]), 0)
            inv.assert_called_once_with(repo_root=str(REPO))
        api = UiApi(self.baseline, str(self.state), str(self.saved), str(self.hist), m2=True, repo_root=str(REPO))
        with patch('serving.saved.load_d01_inventory', return_value={}) as inv, \
             patch('serving.saved.query_archive_inventory', return_value={'ok': True}):
            self.assertEqual(api.query({'mode': 'Q9-archive-inventory', 'params': {}})['query'], {'ok': True})
            inv.assert_called_once()
            # UiApi anchors its repository context with repository_root() ->
            # resolved(), i.e. the canonical case-insensitive Windows identity.
            # On Windows normcase lowercases the spelling; identity, not spelling,
            # is the contract (B1_STATE_SAFETY_EXECUTION.md). The CLI above still
            # propagates the caller's spelling byte-for-byte.
            ui_repo_root = inv.call_args.kwargs['repo_root']
            self.assertIsNotNone(ui_repo_root)
            self.assertEqual(resolved(ui_repo_root), resolved(str(REPO)))
            self.assertNotEqual(resolved(ui_repo_root), resolved(str(self.root)))

    def test_external_cwd_cli_inventory_and_qualification(self):
        env = dict(os.environ, PYTHONPATH=str(REPO / 'src'), PYTHONDONTWRITEBYTECODE='1')
        for cwd in (str(REPO), str(self.root)):
            for command in (['inventory', '--package', str(self.pkg), '--repo', str(REPO)],
                            ['qualification', '--package', str(self.pkg), '--repo', str(REPO)]):
                result = subprocess.run([sys.executable, '-m', 'serving'] + command,
                                        cwd=cwd, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIsInstance(json.loads(result.stdout), dict)

    def test_non_utf8_index_recovery(self):
        (self.state / 'serving_index.json').write_bytes(b'\xffbad')
        with self.assertRaises(ServingIndexError):
            load_index(str(self.state), self.baseline)
        _ensure_index(self.baseline, str(self.state))
        self.assertEqual(load_index(str(self.state), self.baseline)[0], self.document)

    def test_root_only_writers_reject_existing_other_stores(self):
        from serving.history import save_history_document
        self.assertFalse(self.saved.exists())
        with self.assertRaises(RootLayoutError):
            create_saved(str(self.state), 'a', 'Q8-data-quality', {})
        with self.assertRaises(RootLayoutError):
            create_saved(str(self.state / 'nested'), 'a', 'Q8-data-quality', {})
        create_saved(str(self.saved), 'a', 'Q8-data-quality', {})
        with self.assertRaises(RootLayoutError):
            write_index(str(self.saved), self.document)
        with self.assertRaises(RootLayoutError):
            save_history_document(str(self.saved), {'format': 'serving-query-history/1.0', 'entries': [], 'next_seq': 1})
        self.assertEqual(load_saved(str(self.saved))['format'], 'serving-saved-queries/1.0')

    def test_ui_external_cwd_restart_reuses_state_and_preserves_stores(self):
        create_saved(str(self.saved), 'a', 'Q8-data-quality', {})
        record_execution(str(self.hist), 'Q8-data-quality', {}, self.baseline, str(self.state))
        before_package = self.package_snapshot()
        paths = [self.state / 'serving_index.json', self.state / 'serving_index.sha256',
                 self.saved / 'saved_queries.json', self.saved / 'saved_queries.sha256',
                 self.hist / 'query_history.json', self.hist / 'query_history.sha256']
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        env = dict(os.environ, PYTHONPATH=str(REPO / 'src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        command = [sys.executable, '-m', 'ui.serve', '--package', str(self.pkg),
                   '--state', str(self.state), '--saved-state', str(self.saved),
                   '--history-state', str(self.hist), '--repo', str(REPO), '--port', '0']
        # A real subprocess, launched from outside the repository; stop it after
        # its ready line, without waiting for network traffic or altering state.
        proc = subprocess.Popen(command, cwd=str(self.root), env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        lines = queue.Queue()
        reader = threading.Thread(target=lambda: lines.put(proc.stdout.readline()), daemon=True)
        reader.start()
        try:
            try:
                line = lines.get(timeout=20)
            except queue.Empty:
                self.fail('UI did not report readiness within 20 seconds')
            self.assertEqual(json.loads(line)['result'], 'ready', line)
        finally:
            proc.terminate()
            proc.communicate(timeout=10)
            reader.join(timeout=1)
        self.assertEqual(before, [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths])
        self.assertEqual(before_package, self.package_snapshot())

    def test_interrupted_user_store_pair_fails_closed_without_deletion(self):
        from serving import saved, history
        create_saved(str(self.saved), 'a', 'Q8-data-quality', {})
        record_execution(str(self.hist), 'Q8-data-quality', {}, self.baseline, str(self.state))
        for module, root, call, loader, error in (
            (saved, self.saved, lambda: saved.create_saved(str(self.saved), 'b', 'Q8-data-quality', {}), saved.load_saved, saved.SavedQueryError),
            (history, self.hist, lambda: history.record_execution(str(self.hist), 'Q8-data-quality', {}, self.baseline, str(self.state)), history.load_history, history.HistoryError),
        ):
            original = module._atomic_write_text
            calls = []
            def interrupt(path, text):
                calls.append(path)
                if len(calls) == 2:
                    raise OSError('simulated interrupted sidecar publication')
                return original(path, text)
            with self.subTest(module=module.__name__), patch.object(module, '_atomic_write_text', side_effect=interrupt):
                with self.assertRaises(OSError):
                    call()
                with self.assertRaises(error):
                    loader(str(root))
                self.assertTrue(all(Path(path).is_file() for path in calls))

    def test_external_cwd_d01_and_explicit_root(self):
        original = os.getcwd()
        try:
            os.chdir(self.root)
            self.assertEqual(len(load_d01_inventory()), 2462)
            self.assertEqual(len(load_d01_inventory(repo_root=str(REPO))), 2462)
            with self.assertRaises(D01InventoryError):
                load_d01_inventory(repo_root=str(self.root))
            create_saved(str(self.saved), 'inventory', 'Q9-archive-inventory', {})
            with patch('serving.saved.load_d01_inventory', return_value={}) as inventory, patch('serving.saved.query_archive_inventory', return_value={'ok': True}):
                execute_saved(str(self.saved), 'inventory', self.baseline, str(self.state), m2=True, repo_root=str(REPO))
                record_execution(str(self.hist), 'Q9-archive-inventory', {}, self.baseline, str(self.state), m2=True, repo_root=str(REPO))
                self.assertEqual(inventory.call_count, 2)
                self.assertTrue(all(call.kwargs['repo_root'] == str(REPO) for call in inventory.call_args_list))
        finally:
            os.chdir(original)


if __name__ == '__main__':
    unittest.main()
