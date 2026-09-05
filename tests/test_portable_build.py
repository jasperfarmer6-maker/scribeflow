from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'macos'))
from portable_runtime import copy_ignore, verify_links


class PortableRuntimeTests(unittest.TestCase):
    def test_relative_links_survive_relocation(self):
        with tempfile.TemporaryDirectory(prefix='迁移 空格 ') as temporary:
            root = Path(temporary) / 'Bundle'
            root.mkdir()
            (root / 'python3.12').write_text('test')
            (root / 'python').symlink_to('python3.12')
            moved = root.with_name('移动 App')
            root.rename(moved)
            verify_links(moved)
            self.assertEqual((moved / 'python').read_text(), 'test')

    def test_absolute_external_and_broken_links_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            link = root / 'python'
            for target in ('/usr/bin/python3', '../external-python', 'missing-python'):
                link.symlink_to(target)
                with self.assertRaises(RuntimeError):
                    verify_links(root)
                link.unlink()

    def test_private_install_metadata_and_editable_paths_excluded(self):
        names = ['direct_url.json', '_editable_impl_project.pth', '__editable__.project.pth', '__pycache__', 'a.pyc', 'LICENSE', 'METADATA', 'module.py']
        ignored = copy_ignore('/unused', names)
        self.assertEqual(set(names) - ignored, {'LICENSE', 'METADATA', 'module.py'})

if __name__ == '__main__':
    unittest.main()
