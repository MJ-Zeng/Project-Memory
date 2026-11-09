"""A plain ``pip install`` must yield a working ``init``, not a half workspace.

The wheel lands in ``site-packages``, where the repository-root ``skill/`` lookup
cannot reach, so ``setup.py`` copies the same tree into ``project_memory/_skill``
at build time and bootstrap falls back to it.  These guards pin the coupling
between the build shim, the manifest and the resolver; the real build/install/
init round trip runs in the ``packaging`` CI job.
"""
import tempfile
import unittest
from pathlib import Path

from project_memory.bootstrap import resolve_skill_source

REPO = Path(__file__).resolve().parents[1]


class SkillSourceResolutionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='pm-packaging-')
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.tool_root = self.base / 'repo'
        self.package_dir = self.base / 'site-packages' / 'project_memory'

    def _make(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        (path / 'SKILL.md').write_text('# skill\n', encoding='utf-8')
        return path

    def test_repository_tree_wins_when_both_copies_exist(self):
        repo_copy = self._make(self.tool_root / 'skill' / 'project-memory')
        self._make(self.package_dir / '_skill' / 'project-memory')
        self.assertEqual(resolve_skill_source(self.tool_root, self.package_dir), repo_copy)

    def test_wheel_install_falls_back_to_the_packaged_copy(self):
        packaged = self._make(self.package_dir / '_skill' / 'project-memory')
        self.assertEqual(resolve_skill_source(self.tool_root, self.package_dir), packaged)

    def test_missing_both_still_names_the_path_init_reports(self):
        resolved = resolve_skill_source(self.tool_root, self.package_dir)
        self.assertEqual(resolved, self.package_dir / '_skill' / 'project-memory')
        self.assertFalse(resolved.is_dir())


class DistributionInputsTest(unittest.TestCase):
    def test_build_shim_copies_into_the_exact_fallback_directory(self):
        shim = (REPO / 'setup.py').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory(prefix='pm-packaging-') as tmp:
            absent = Path(tmp) / 'absent'
            fallback = resolve_skill_source(absent, absent)
        relative = fallback.relative_to(absent).as_posix()
        self.assertEqual(relative, '_skill/project-memory')
        for part in fallback.relative_to(absent).parts:
            self.assertIn(f"'{part}'", shim,
                          f'setup.py 必须把 Skill 复制到 bootstrap 回退查找的 {relative}')
        self.assertIn("ROOT / 'skill' / 'project-memory'", shim,
                      '构建副本必须来自唯一的 canonical skill/ 源树')
        self.assertIn("cmdclass={'build_py': build_py_with_skill}", shim,
                      '复制必须挂在 build_py 上，否则 wheel 里不会有资源')

    def test_build_shim_fails_closed_without_the_skill_tree(self):
        shim = (REPO / 'setup.py').read_text(encoding='utf-8')
        self.assertIn('raise SystemExit', shim,
                      'sdist 缺 skill/ 时必须显式失败，不能产出装不起 init 的 wheel')

    def test_manifest_ships_everything_needed_to_build_and_test_from_sdist(self):
        manifest = (REPO / 'MANIFEST.in').read_text(encoding='utf-8')
        for entry in ('recursive-include skill *', 'recursive-include tests *.py',
                      'recursive-include fixtures', 'recursive-include examples',
                      'recursive-include .github *',
                      'recursive-include bin *', 'setup.py'):
            self.assertIn(entry, manifest, f'sdist 缺少 {entry}，从 sdist 构建或跑测试会失败')


if __name__ == '__main__':
    unittest.main()