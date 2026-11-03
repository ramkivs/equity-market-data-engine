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


_STORE_FILES = {
    "state": ("serving_index.json", "serving_index.sha256"),
    "saved": ("saved_queries.json", "saved_queries.sha256"),
    "history": ("query_history.json", "query_history.sha256"),
}


def validate_store_root(root, role):
    """Reject an existing different store at this root or an ancestor.

    Root-only operations cannot know other unprovided, empty roots. The UI and
    the CLI's four-root configuration provide complete pairwise validation.
    """
    validate_roots(**{role: root})
    current = resolved(root)
    while True:
        for other, names in _STORE_FILES.items():
            if other != role:
                for name in names:
                    if os.path.lexists(os.path.join(current, name)):
                        raise RootLayoutError("root-layout: %s root is inside or equal to an existing %s store: %s" % (role, other, current))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def repository_root(root=None):
    return resolved(root if root is not None else os.path.join(os.path.dirname(__file__), '..', '..'))


class RootConfiguration:
    """A four-root layout, with substitution detection for existing directories.

    Paths are anchored when configured. Each validation detects retargeted aliases
    and replacement of directories or existing ancestors. This is a fail-closed
    check, not a filesystem transaction or protection from a concurrent attacker.
    """

    def __init__(self, package, state, saved, history):
        self._inputs = {name: os.path.abspath(os.fspath(path)) for name, path in
                        (("package", package), ("state", state),
                         ("saved", saved), ("history", history))}
        self.roots = {name: resolved(path) for name, path in self._inputs.items()}
        validate_roots(**self.roots)
        self._identities = {}
        self._remember_existing()

    def _remember_existing(self):
        for root in self.roots.values():
            path = root
            while True:
                if os.path.isdir(path):
                    info = os.stat(path)
                    identity = (info.st_dev, info.st_ino)
                    old = self._identities.get(path)
                    if old is not None and old != identity:
                        raise RootLayoutError("root-layout: directory replaced: %s" % path)
                    self._identities[path] = identity
                elif path in self._identities:
                    raise RootLayoutError("root-layout: directory disappeared: %s" % path)
                parent = os.path.dirname(path)
                if parent == path:
                    break
                path = parent

    def validate(self):
        for name, original in self._inputs.items():
            if resolved(original) != self.roots[name]:
                raise RootLayoutError("root-layout: configured %s path changed: %s" % (name, original))
        validate_roots(**self.roots)
        self._remember_existing()
        return self
