"""Synthetic substitution tests for descriptor-anchored state publication."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from serving.atomic import atomic_write_text
from serving.paths import RootLayoutError


class AtomicDirectoryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix' and os.rename in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'), 'requires POSIX dir_fd support')
    def test_swap_before_replace_does_not_redirect_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state, old, pkg = root / 'state', root / 'old', root / 'pkg'
            state.mkdir(); pkg.mkdir()
            (pkg / 'PACKAGE_MANIFEST.sha256').write_text('protected', encoding='utf-8')
            (pkg / 'saved_queries.json').write_text('package contents', encoding='utf-8')
            real_replace = os.replace
            def substitute(source, destination, **kwargs):
                state.rename(old)
                state.symlink_to(pkg, target_is_directory=True)
                return real_replace(source, destination, **kwargs)
            with patch('serving.atomic.os.replace', side_effect=substitute), self.assertRaises(RootLayoutError):
                atomic_write_text(str(state / 'saved_queries.json'), 'user contents')
            self.assertEqual((pkg / 'saved_queries.json').read_text(encoding='utf-8'), 'package contents')
            self.assertEqual((old / 'saved_queries.json').read_text(encoding='utf-8'), 'user contents')

    def test_package_directory_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            pkg = Path(temp) / 'pkg'; pkg.mkdir()
            (pkg / 'PACKAGE_MANIFEST.sha256').write_text('protected', encoding='utf-8')
            # POSIX helper performs an additional marker check itself. The
            # Windows fallback is guarded by callers' existing checks.
            if os.name != 'posix':
                self.skipTest('POSIX descriptor path')
            with self.assertRaises(RootLayoutError):
                atomic_write_text(str(pkg / 'saved_queries.json'), 'no')
            self.assertFalse((pkg / 'saved_queries.json').exists())


if __name__ == '__main__':
    unittest.main()
