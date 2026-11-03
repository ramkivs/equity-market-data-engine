"""B5 Windows handle-lifecycle regressions (disposable synthetic fixtures only).

These tests cover the three failure classes recorded in the Windows B5 run of
3 November 2026 without claiming a Windows result from a Linux run:

* ``os.fsync`` on Windows is the CRT ``_commit`` function and rejects a
  read-only descriptor with ``EBADF`` (``OSError: [Errno 9] Bad file
  descriptor``).  POSIX permits it, so Linux runs cannot detect the defect.
  ``windows_fsync`` emulates the Windows rule on POSIX; on Windows the real
  ``os.fsync`` enforces it directly.
* SQLite connections opened by a test must be closed before temporary-directory
  cleanup.  An open SQLite handle prevents unlink on Windows
  (``PermissionError: [WinError 32]``).  ``sqlite_connection`` owns and closes
  the connection deterministically.
"""

from __future__ import annotations

import contextlib
import errno
import os
import sqlite3
import stat
import tempfile
import unittest
from unittest import mock

from serving.atomic import sync_file
from serving.continuity_catalog import FORMAT as CATALOG_FORMAT, FILENAME, bootstrap, verify_catalog
from serving.index import build_index, write_index
from serving.incremental_publication import publish
from serving.ticker_proofs import FILE as PROOF_FILE
from tests import test_incremental_staging as staging
from tests.sqlite_support import sqlite_connection


@contextlib.contextmanager
def windows_fsync():
    """Enforce the Windows ``os.fsync`` rule (write access required).

    On Windows the real call already has that behavior. On POSIX, reject
    ``fsync`` on a read-only **regular file** descriptor with ``EBADF`` exactly
    as ``_commit`` does. Directory descriptors are not regular files: the
    production code guards directory fsync behind ``os.name == 'posix'``, so it
    must not be rejected by this emulation.
    """
    if os.name == 'nt':
        yield
        return
    import fcntl
    real_fsync = os.fsync

    def checked(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            if flags & os.O_ACCMODE == os.O_RDONLY:
                raise OSError(errno.EBADF, 'Bad file descriptor')
        return real_fsync(fd)

    with mock.patch('os.fsync', side_effect=checked):
        yield


class SyncHandleUnitTests(unittest.TestCase):
    def test_read_only_fsync_is_rejected_and_sync_file_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'durable.sqlite3')
            with open(path, 'wb') as handle:
                handle.write(b'committed bytes')
            with windows_fsync():
                with open(path, 'rb') as handle:
                    with self.assertRaises(OSError) as raised:
                        os.fsync(handle.fileno())
                if os.name != 'nt':
                    self.assertEqual(raised.exception.errno, errno.EBADF)
                # The production helper must succeed under the same rule.
                sync_file(path)
            with open(path, 'rb') as handle:
                self.assertEqual(handle.read(), b'committed bytes')


class SqliteConnectionOwnershipTests(unittest.TestCase):
    def test_connection_is_closed_and_committed_on_exit(self):
        # On Windows, cleanup would raise WinError 32 for any leaked handle,
        # so this is also the direct cleanup regression.
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'registry.sqlite3')
            with sqlite_connection(path) as db:
                db.execute('CREATE TABLE accepted (name TEXT)')
                db.execute("INSERT INTO accepted VALUES ('a')")
                handle = db
            with self.assertRaises(sqlite3.ProgrammingError):
                handle.execute('SELECT 1')
            with sqlite_connection(path) as reopened:
                self.assertEqual(reopened.execute('SELECT name FROM accepted').fetchall(), [('a',)])

    def test_connection_is_closed_and_rolled_back_on_exception(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'registry.sqlite3')
            with sqlite_connection(path) as db:
                db.execute('CREATE TABLE accepted (name TEXT)')
            handle = None
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                with sqlite_connection(path) as db:
                    handle = db
                    db.execute("INSERT INTO accepted VALUES ('a')")
                    raise RuntimeError('interrupted')
            with self.assertRaises(sqlite3.ProgrammingError):
                handle.execute('SELECT 1')
            with sqlite_connection(path) as reopened:
                self.assertEqual(reopened.execute('SELECT name FROM accepted').fetchall(), [])


class WindowsPublicationTests(unittest.TestCase):
    setUp = staging.StagingTests.setUp
    tearDown = staging.StagingTests.tearDown
    stage = staging.StagingTests.stage

    def bootstrap(self):
        write_index(self.args[2], build_index(self.baseline))
        return bootstrap(self.baseline, self.args[2], self.args[1], self.args[3], self.args[4], self.args[5])

    def test_catalog_bootstrap_flushes_through_writable_descriptor(self):
        with windows_fsync():
            result = self.bootstrap()
        self.assertEqual(result['status'], 'BOOTSTRAPPED')
        self.assertTrue(os.path.isfile(os.path.join(self.args[2], FILENAME)))
        self.assertEqual(verify_catalog(self.baseline, self.args[2])['format'], CATALOG_FORMAT)

    def test_publication_builds_ticker_proofs_through_writable_descriptor(self):
        with windows_fsync():
            self.bootstrap()
            self.stage()
            result = publish(*self.args)
        self.assertEqual(result['status'], 'PUBLISHED')
        self.assertTrue(os.path.isfile(os.path.join(self.args[2], PROOF_FILE)))

    def test_no_open_sqlite_handles_remain_at_fixture_cleanup(self):
        # POSIX unlink succeeds even with an open handle, so explicitly inspect
        # descriptors after the same disposable-state work. On Windows the
        # inherited ``StagingTests.tearDown`` -> ``self.tmp.cleanup()`` is itself
        # the WinError 32 check: an open SQLite handle blocks that unlink.
        self.bootstrap()
        self.stage()
        publish(*self.args)
        with sqlite_connection(os.path.join(self.args[1], 'source_registry.sqlite3')) as db:
            self.assertGreater(db.execute('SELECT count(*) FROM accepted').fetchone()[0], 0)
        if os.path.isdir('/proc/self/fd'):
            root = os.path.realpath(self.tmp.name)
            leaked = []
            for name in os.listdir('/proc/self/fd'):
                try:
                    target = os.readlink(os.path.join('/proc/self/fd', name))
                except OSError:
                    continue
                if target.startswith(root + os.sep):
                    leaked.append(target)
            self.assertEqual(leaked, [])
