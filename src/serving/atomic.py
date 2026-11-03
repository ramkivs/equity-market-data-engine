"""Atomic local state file publication with directory anchoring where supported."""
import contextlib
import os
import secrets
import tempfile

from .paths import RootLayoutError, resolved, validate_roots


def atomic_write_text(path, text, sync=False):
    directory = os.path.dirname(path) or "."
    name = os.path.basename(path)
    # Windows does not expose the POSIX dir_fd interface. Keep the previous
    # same-directory atomic replace there; Windows-specific protection requires
    # a separate handle-based implementation and validation.
    if not (os.name == "posix" and os.open in os.supports_dir_fd and
            os.rename in os.supports_dir_fd and os.unlink in os.supports_dir_fd and
            hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")):
        fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + name + ".", suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                if sync:
                    handle.flush()
                    os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return

    # Use an absolute resolved path and open the final directory without following
    # a last-component symlink. The descriptor pins the actual directory for the
    # temp create, replace and cleanup even if its pathname is later retargeted.
    target = resolved(directory)
    validate_roots(state=target)
    dirfd = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    tmp = None
    try:
        opened = os.fstat(dirfd)
        try:
            current = os.stat(directory)
        except OSError as exc:
            raise RootLayoutError("root-layout: state directory changed: %s" % exc)
        if resolved(directory) != target or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise RootLayoutError("root-layout: state directory changed before publication: %s" % directory)
        validate_roots(state=directory)
        # Reserve the temp name directly in the pinned directory.
        tmp = ".%s.%s.part" % (name, secrets.token_hex(16))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(tmp, flags, 0o600, dir_fd=dirfd)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            if sync:
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        tmp = None
        try:
            current = os.stat(directory)
        except OSError as exc:
            raise RootLayoutError("root-layout: state directory changed during publication: %s" % exc)
        if resolved(directory) != target or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise RootLayoutError("root-layout: state directory changed during publication: %s" % directory)
    finally:
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=dirfd)
        os.close(dirfd)
