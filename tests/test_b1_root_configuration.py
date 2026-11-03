"""Four-root configuration and substitution checks with synthetic fixtures."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from tests import serving_fixtures
from serving import cli
from serving.baseline import open_baseline
from serving.index import build_index, write_index
from serving.paths import RootConfiguration, RootLayoutError
from ui.api import UiApi


class RootConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.pkg, self.state, self.saved, self.history = [self.base / p for p in ('pkg', 'state', 'saved', 'history')]
        facts = serving_fixtures.build_fixture_package(str(self.pkg))
        self.baseline = open_baseline(str(self.pkg), spec=facts['spec'])
        write_index(str(self.state), build_index(self.baseline))

    def tearDown(self):
        self.temp.cleanup()

    def config(self, **kwargs):
        values = dict(package=self.pkg, state=self.state, saved=self.saved, history=self.history)
        values.update(kwargs)
        return RootConfiguration(**values)

    def test_all_pairs_reject_equal_and_nested(self):
        roles = ('package', 'state', 'saved', 'history')
        values = dict(package=self.pkg, state=self.state, saved=self.saved, history=self.history)
        for i, a in enumerate(roles):
            for b in roles[i + 1:]:
                for path in (values[a], values[a] / 'child'):
                    with self.subTest(a=a, b=b, path=path), self.assertRaises(RootLayoutError):
                        self.config(**{b: path})

    def test_directory_replacement_rejected_by_direct_reads_and_writes(self):
        self.saved.mkdir()
        api = UiApi(self.baseline, str(self.state), str(self.saved), str(self.history))
        self.saved.rename(self.base / 'old-saved')
        self.saved.mkdir()
        with self.assertRaises(RootLayoutError):
            api.saved_list()
        with self.assertRaises(RootLayoutError):
            api.saved_create({'id': 'a', 'mode': 'Q8-data-quality', 'params': {}})
        status, doc = api.dispatch('GET', '/api/status')
        self.assertEqual((status, doc['check']), (400, 'root-layout'))
        self.assertFalse(list(self.saved.iterdir()))

    def test_retargeted_alias_is_rejected(self):
        self.saved.mkdir()
        alias = self.base / 'alias'
        try:
            alias.symlink_to(self.saved, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        api = UiApi(self.baseline, str(self.state), str(alias), str(self.history))
        alias.unlink()
        alias.symlink_to(self.pkg, target_is_directory=True)
        with self.assertRaises(RootLayoutError):
            api.saved_list()
        self.assertFalse((self.pkg / 'saved_queries.json').exists())

    def test_configuration_must_match_direct_service_arguments(self):
        config = self.config()
        with self.assertRaises(RootLayoutError):
            UiApi(self.baseline, str(self.state), str(self.history), str(self.saved), root_config=config)

    def test_cli_complete_configuration_rejects_mismatch_before_mutation(self):
        flags = ['--root-package', str(self.pkg), '--root-state', str(self.state),
                 '--root-saved', str(self.saved), '--root-history', str(self.history)]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = cli.main(flags + ['saved', 'save', '--saved-state', str(self.history), '--id', 'q', '--mode', 'Q8-data-quality'])
        self.assertEqual(result, 3)
        self.assertIn('root-layout', out.getvalue())
        self.assertFalse(self.history.exists())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(flags + ['saved', 'save', '--saved-state', str(self.saved), '--id', 'q', '--mode', 'Q8-data-quality']), 0)
        self.assertTrue((self.saved / 'saved_queries.json').is_file())

    def test_partial_cli_configuration_fails_closed(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['--root-package', str(self.pkg), 'info', '--state', str(self.state)]), 3)


if __name__ == '__main__':
    unittest.main()
