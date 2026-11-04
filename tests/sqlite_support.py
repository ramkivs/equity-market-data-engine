"""Deterministic SQLite connection ownership for the disposable test fixtures.

``sqlite3.Connection`` used as a context manager commits or rolls back the
transaction but **does not close the connection**. The object is reclaimed only
when its last reference (and any reference cycle through cursors/statements) is
collected, which is not ordered relative to ``TemporaryDirectory.cleanup()``.

On POSIX an open handle does not prevent unlink, so the leak is invisible. On
Windows an open SQLite handle prevents deleting the file
(``PermissionError: [WinError 32]``) during temporary-directory cleanup. Tests
that open a registry/catalog/proof database inside a ``TemporaryDirectory`` must
therefore close it deterministically, before fixture teardown.

``sqlite_connection`` preserves the exact transaction semantics of using a
connection as a context manager (commit on success, rollback on exception) and
adds an unconditional close.
"""

from __future__ import annotations

import contextlib
import sqlite3


@contextlib.contextmanager
def sqlite_connection(*args, **kwargs):
    """Yield a connection, commit/rollback on exit, then always close it."""
    db = sqlite3.connect(*args, **kwargs)
    try:
        with db:
            yield db
    finally:
        db.close()
