"""Single-member staging only. These tests never access the M2 package."""
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import zipfile

from serving.baseline import open_baseline
from serving.incremental_registry import RegistryError, bindings, conflicts, initialize
from serving.incremental_staging import list_staged, prepare
from tests import serving_fixtures as fixtures


def archive_bytes(member, content):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, content)
    return buffer.getvalue()


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.pkg = base / 'pkg'
        fact = fixtures.build_fixture_package(str(self.pkg))
        self.baseline = open_baseline(str(self.pkg), spec=fact['spec'])
        roots = {x: str(base / x) for x in ('LEGACY', 'UDIFF')}
        for root in roots.values():
            Path(root).mkdir()
        self.source = Path(roots['LEGACY']) / 'new.zip'
        member = fixtures._member_bytes('fix-leg-2016-01-04.csv').replace(b'04-JAN-2016', b'06-JAN-2016')
        self.source.write_bytes(archive_bytes('new.csv', member))
        self.args = (self.baseline, *(str(base / x) for x in ('registry', 'state', 'saved', 'history')), roots)
        initialize(*self.args)
        self.before = {str(p.relative_to(self.pkg)): p.read_bytes() for p in self.pkg.rglob('*') if p.is_file()}
        self.patch = mock.patch('serving.incremental_staging.runtime_bindings', return_value=bindings(self.baseline))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.assertEqual(self.before, {str(p.relative_to(self.pkg)): p.read_bytes() for p in self.pkg.rglob('*') if p.is_file()})
        self.tmp.cleanup()

    def stage(self, date='2016-01-06'):
        return prepare(*self.args, 'LEGACY', 'new.zip', date, 'scan-1')

    def test_valid_staged_noop_not_accepted_and_deterministic(self):
        result = self.stage()
        self.assertEqual(result['status'], 'VALIDATED-STAGED-NOT-PUBLISHED')
        self.assertGreater(result['record']['rows'], 0)
        self.assertEqual(list_staged(*self.args), [result['record']])
        with mock.patch('serving.incremental_staging.build_canonical', side_effect=AssertionError('must not reprocess')):
            again = self.stage()
        self.assertEqual(again['status'], 'ALREADY-STAGED')
        self.assertEqual(again['record'], result['record'])
        db = sqlite3.connect(os.path.join(self.args[1], 'source_registry.sqlite3'))
        try:
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS)
        finally:
            db.close()

    def test_invalid_and_wrong_date_never_staged(self):
        for payload, date in ((b'not a zip', '2016-01-06'),
                              (archive_bytes('x.csv', b'not a canonical csv'), '2016-01-06'),
                              (self.source.read_bytes(), '2016-01-07')):
            self.source.write_bytes(payload)
            with self.assertRaises(RegistryError):
                self.stage(date)
            self.assertEqual(list_staged(*self.args), [])

    def test_version_mismatch_and_duplicate_date_fail_closed(self):
        with mock.patch('serving.incremental_staging.runtime_bindings', return_value=dict(bindings(self.baseline), engine_sha256='wrong')):
            with self.assertRaises(RegistryError):
                self.stage()
        with self.assertRaises(RegistryError):
            self.stage('2016-01-04')
        self.assertEqual(list_staged(*self.args), [])

    def test_changed_baseline_is_held_never_staged(self):
        name = 'fix-leg-2016-01-04.csv'
        Path(self.args[-1]['LEGACY'], name).write_bytes(b'changed')
        out = prepare(*self.args, 'LEGACY', name, '2016-01-04', 'conflict-scan')
        self.assertEqual(out['status'], 'CHANGED-CONFLICT-UNRESOLVED')
        self.assertEqual(len(conflicts(*self.args)), 1)
        self.assertEqual(list_staged(*self.args), [])

    def test_changed_staged_candidate_is_never_replaced(self):
        first = self.stage()
        self.source.write_bytes(archive_bytes('different.csv', b'new content'))
        with self.assertRaises(RegistryError):
            self.stage()
        self.assertEqual(list_staged(*self.args), [first['record']])

    def test_interrupted_write_rolls_back_and_retry_succeeds(self):
        path = os.path.join(self.args[1], 'source_registry.sqlite3')
        # A trigger simulates a publication failure at the INSERT boundary.
        with sqlite3.connect(path) as db:
            from serving.incremental_staging import _schema
            _schema(db)
            db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON staged_candidates BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        with self.assertRaises(RegistryError):
            self.stage()
        self.assertEqual(list_staged(*self.args), [])
        with sqlite3.connect(path) as db:
            db.execute('DROP TRIGGER fail_insert')
        self.assertEqual(self.stage()['status'], 'VALIDATED-STAGED-NOT-PUBLISHED')

    def test_deterministic_replay_in_disposable_independent_registry(self):
        first = self.stage()['record']
        other = Path(self.tmp.name) / 'independent'
        roots = {'LEGACY': str(other / 'legacy'), 'UDIFF': str(other / 'udiff')}
        for path in roots.values():
            Path(path).mkdir(parents=True)
        Path(roots['LEGACY'], 'new.zip').write_bytes(self.source.read_bytes())
        args = (self.baseline, *(str(other / x) for x in ('registry', 'state', 'saved', 'history')), roots)
        initialize(*args)
        replay = prepare(*args, 'LEGACY', 'new.zip', '2016-01-06', 'another-scan')['record']
        self.assertEqual(first, replay)

    def test_multi_member_and_corrupt_zip_are_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('a.csv', b'a')
            z.writestr('b.csv', b'b')
        self.source.write_bytes(buf.getvalue())
        with self.assertRaises(RegistryError):
            self.stage()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED) as z:
            z.writestr('a.csv', b'abcdefghijk')
        corrupt = buf.getvalue().replace(b'abcdefghijk', b'abcdefghijX', 1)
        self.source.write_bytes(corrupt)
        with self.assertRaises(RegistryError):
            self.stage()
        self.assertEqual(list_staged(*self.args), [])
