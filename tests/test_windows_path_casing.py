"""Windows path-casing identity regressions (POSIX emulation + real Windows).

The serving layer's path contract is canonical, case-insensitive identity:
``resolved(path) == normcase(realpath(abspath(path)))``. Windows ``normcase``
lowercases the whole path; POSIX ``normcase`` is the identity. Every root
overlap/alias/replacement check and the persisted composite-registry binding use
that canonical form; a caller's original spelling is not identity
(B1_STATE_SAFETY_EXECUTION.md: "the implementation uses that platform's
realpath, normcase and commonpath").

The two Windows/Python 3.14.3 failures of PR #3 were raw-spelling assertions
against canonical values, not defects in ``resolved``/``repository_root``/
``ensure_binding``. These tests emulate Windows ``normcase`` on POSIX so the
contract is exercised in the Linux suite; on Windows the real ``normcase`` is
used. No assertion about path identity, binding integrity or root safety is
relaxed here.
"""
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from tests import test_b1_state_safety as b1
from serving.composite_binding import (
    BINDING_FILE, FORMAT, GUARD_FILE, _binding_digest, _read_file,
    ensure_binding, read_binding,
)
from serving.paths import repository_root, resolved
from serving.query import QueryError


@contextlib.contextmanager
def windows_casing():
    """Give POSIX ``normcase`` Windows' lowercasing behaviour for one block."""
    if os.name == 'nt':
        yield  # real Windows normcase already lowercases
        return
    with mock.patch('os.path.normcase', side_effect=lambda p: os.fspath(p).lower()):
        yield


class CanonicalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_case_variants_resolve_to_one_identity_and_other_root_does_not(self):
        mixed = str(self.root / 'EquiCore' / 'RepoRoot')
        with windows_casing():
            canonical = resolved(mixed)
            self.assertEqual(canonical, mixed.lower())
            self.assertEqual(resolved(mixed.lower()), canonical)
            self.assertEqual(resolved(mixed.upper()), canonical)
            self.assertEqual(resolved(canonical), canonical)  # idempotent
            self.assertEqual(repository_root(mixed), canonical)
            # The canonicalizer does not preserve the caller's spelling. This is
            # exactly why the two Windows assertions on raw spelling failed.
            self.assertNotEqual(repository_root(mixed), mixed)
            self.assertNotEqual(
                resolved(str(self.root / 'EquiCore' / 'OtherRoot')), canonical)
        if os.name != 'nt':
            self.assertEqual(resolved(mixed), mixed)  # POSIX preserves spelling


class ExplicitRepositoryCasingTests(unittest.TestCase):
    setUp = b1.StateSafetyTests.setUp
    tearDown = b1.StateSafetyTests.tearDown

    def test_case_variant_explicit_repository_propagates_same_identity(self):
        from serving import cli
        from ui.api import UiApi
        repo = Path(__file__).resolve().parents[1]
        variant = str(repo).upper()  # identical directory, different spelling
        with windows_casing():
            self.assertEqual(resolved(variant), resolved(str(repo)))
            with patch('serving.cli._open', return_value=self.baseline), \
                 patch('serving.cli.load_d01_inventory', return_value={}) as inv, \
                 patch('serving.cli.query_archive_inventory', return_value={'ok': True}), \
                 patch('serving.cli._print_json'):
                self.assertEqual(
                    cli.main(['inventory', '--package', str(self.pkg), '--m2', '--repo', variant]), 0)
                inv.assert_called_once()
                supplied = inv.call_args.kwargs['repo_root']
                self.assertEqual(supplied, variant)  # CLI keeps caller spelling
                self.assertEqual(resolved(supplied), resolved(str(repo)))
            api = UiApi(self.baseline, str(self.state), str(self.saved), str(self.hist),
                        m2=True, repo_root=variant)
            with patch('serving.saved.load_d01_inventory', return_value={}) as inv, \
                 patch('serving.saved.query_archive_inventory', return_value={'ok': True}):
                self.assertEqual(
                    api.query({'mode': 'Q9-archive-inventory', 'params': {}})['query'], {'ok': True})
                inv.assert_called_once()
                supplied = inv.call_args.kwargs['repo_root']
                self.assertIsNotNone(supplied)
                self.assertEqual(resolved(supplied), resolved(str(repo)))
                self.assertNotEqual(resolved(supplied), resolved(str(self.root)))


class RegistryBindingCasingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'pkg').mkdir()
        (self.root / 'state').mkdir()
        self.registry = self.root / 'RegistryRoot'  # deliberately mixed case
        self.registry.mkdir()
        self.baseline = SimpleNamespace(root=str(self.root / 'pkg'),
                                        manifest_digest='0' * 64)

    def tearDown(self):
        self.tmp.cleanup()

    def test_binding_persists_canonical_identity_and_still_fails_closed(self):
        state = str(self.root / 'state')
        with windows_casing():
            canonical = resolved(self.registry)
            ensure_binding(self.baseline, state, str(self.registry))
            bound = read_binding(self.baseline, state)
            self.assertEqual(bound, canonical)
            self.assertEqual(resolved(bound), bound)  # stored value is canonical
            self.assertNotEqual(bound, str(self.registry))  # spelling is not persisted
            different = str(self.root / 'OtherRegistry')
            self.assertNotEqual(resolved(bound), resolved(different))
            # A genuinely different registry is still refused.
            with self.assertRaisesRegex(QueryError, 'different registry'):
                ensure_binding(self.baseline, state, different)
            # A binding storing the caller's raw (non-canonical) spelling is
            # rejected even with a correct digest: the safety check survives.
            doc = {'format': FORMAT,
                   'baseline_manifest_sha256': self.baseline.manifest_digest,
                   'registry_root': str(self.registry)}
            doc['binding_sha256'] = _binding_digest(
                {key: doc[key] for key in ('format', 'baseline_manifest_sha256', 'registry_root')})
            text = json.dumps(doc, sort_keys=True, separators=(',', ':')) + '\n'
            for name in (BINDING_FILE, GUARD_FILE):
                (self.root / 'state' / name).write_text(text, encoding='utf8')
            with self.assertRaisesRegex(QueryError, 'invalid composite registry binding'):
                _read_file(self.baseline, state, BINDING_FILE)
