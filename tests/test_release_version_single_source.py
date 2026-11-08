"""H1: the published code must self-report the version the package claims.

``project_memory.evidence`` writes ``__version__`` into the ``generator.version``
field of an evidence manifest and then signs that payload, so a second hardcoded
version in ``pyproject.toml`` silently mislabels signed evidence.  ``v1.1.0``
shipped with ``__init__.py`` still reading ``1.0.0``.  The guard is structural:
the package metadata must have no static ``version`` key and must read the
version from ``project_memory.__version__``.  ``--version`` reports the same
string, so there is no fourth place to keep in sync.
"""
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

import project_memory

REPO = Path(__file__).resolve().parents[1]


class VersionSingleSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pyproject = tomllib.loads((REPO / 'pyproject.toml').read_text(encoding='utf-8'))

    def test_version_is_a_release_string(self):
        self.assertRegex(project_memory.__version__, r'^\d+\.\d+\.\d+$',
                         '__version__ 必须是 x.y.z，不能带占位或开发后缀')

    def test_pyproject_has_no_static_version(self):
        project_table = self.pyproject['project']
        self.assertNotIn('version', project_table,
                         'pyproject 不得写死 version：与 __version__ 双份维护必然漂移')
        self.assertIn('version', project_table.get('dynamic', []),
                      'version 必须声明为 dynamic')

    def test_dynamic_version_reads_the_package_attribute(self):
        attr = self.pyproject['tool']['setuptools']['dynamic']['version']['attr']
        self.assertEqual(attr, 'project_memory.__version__',
                         'dynamic version 必须取 project_memory.__version__')
        module, _, name = attr.rpartition('.')
        self.assertEqual(getattr(__import__(module), name), project_memory.__version__)

    def test_cli_version_reports_the_same_source(self):
        proc = subprocess.run([sys.executable, '-m', 'project_memory', '--version'],
                              capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), f'project-memory {project_memory.__version__}')


if __name__ == '__main__':
    unittest.main()
