"""Shared local path isolation and repository context helpers."""
import os


class RootLayoutError(ValueError):
    """Unsafe package/state layout; no write has been attempted."""


def resolved(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def overlaps(a, b):
    a, b = resolved(a), resolved(b)
    try:
        common = os.path.commonpath((a, b))
    except ValueError:  # distinct Windows drives
        return False
    return common == a or common == b


def validate_roots(**roots):
    """Reject equal or nested roots, resolving existing symlink ancestors first."""
    items = [(name, resolved(path)) for name, path in roots.items() if path is not None]
    for i, (name, path) in enumerate(items):
        for other, target in items[i + 1:]:
            if overlaps(path, target):
                raise RootLayoutError("root-layout: %s (%s) overlaps %s (%s)" % (name, path, other, target))
    # Root-only store APIs do not have a Baseline argument. Detect a package
    # in their ancestry even when accessed through a symlinked directory.
    for name, path in items:
        if name == 'package':
            continue
        current = path
        while True:
            if os.path.isfile(os.path.join(current, 'PACKAGE_MANIFEST.sha256')) or os.path.isfile(os.path.join(current, 'RUN_COMPLETE.json')):
                raise RootLayoutError("root-layout: %s (%s) is inside a package (%s)" % (name, path, current))
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent


def repository_root(root=None):
    return resolved(root if root is not None else os.path.join(os.path.dirname(__file__), '..', '..'))
