"""B5A: the CLI must not be replaced by a same-named ``project_memory`` package.

The trusted entry is the launcher (``project-memory`` console script / isolated
interpreter); ``python -m project_memory`` additionally fails closed when it can
still see a same-named package on ``sys.path``.  See ADR-0005.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from project_memory import execution
from project_memory.common import PMError, git_sha
from project_memory.execution import run_command

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / '_project_memory_launcher.py'
MARKER_ENV = 'B5A_MARKER'


def _env(**overrides):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('PYTHON')}
    env.pop('PYTHONPATH', None)
    env.update({key: str(value) for key, value in overrides.items()})
    return env


def _run(args, cwd, **overrides):
    return subprocess.run([str(arg) for arg in args], cwd=str(cwd),
                          env=_env(**overrides), capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=120)


def _make_shadow(base: Path) -> Path:
    package = base / 'project_memory'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text(
        'import os\n'
        'from pathlib import Path\n'
        'marker = os.environ.get("B5A_MARKER")\n'
        'if marker:\n'
        '    Path(marker).write_text("init")\n'
        'print("SHADOW_INIT")\n', encoding='utf-8')
    (package / '__main__.py').write_text(
        'print("SHADOW_MAIN")\n'
        'raise SystemExit(0)\n', encoding='utf-8')
    return package


class ShadowLaunchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.marker = self.root / 'shadow.marker'

    def tearDown(self):
        self.tmp.cleanup()

    def assert_not_hijacked(self, result):
        output = result.stdout + result.stderr
        self.assertNotIn('SHADOW_INIT', output)
        self.assertNotIn('SHADOW_MAIN', output)
        self.assertFalse(self.marker.exists(), '假冒包写入了 marker')
        self.assertIn('用法', result.stdout)

    def test_launcher_ignores_pythonpath_shadow(self):
        package = _make_shadow(self.root / 'shadow')
        result = _run([sys.executable, LAUNCHER, '--help'], self.root,
                      PYTHONPATH=package.parent, B5A_MARKER=self.marker)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_not_hijacked(result)

    def test_launcher_ignores_cwd_shadow(self):
        _make_shadow(self.root)
        result = _run([sys.executable, LAUNCHER, '--help'], self.root,
                      B5A_MARKER=self.marker)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_not_hijacked(result)

    def test_bare_module_refuses_contaminated_path(self):
        package = _make_shadow(self.root / 'shadow')
        result = _run([sys.executable, '-m', 'project_memory', '--help'], REPO,
                      PYTHONPATH=package.parent, B5A_MARKER=self.marker)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('同名', result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertNotIn('SHADOW_MAIN', result.stdout)

    def test_bare_module_normal_help_still_works(self):
        result = _run([sys.executable, '-m', 'project_memory', '--help'], REPO)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('用法', result.stdout)

    def test_isolated_module_is_trusted_despite_shadow(self):
        _make_shadow(self.root)
        code = ('import sys; sys.path.insert(0, sys.argv[1]); '
                "sys.argv = ['project-memory'] + sys.argv[2:]; import runpy; "
                "runpy.run_module('project_memory', run_name='__main__')")
        result = _run([sys.executable, '-I', '-P', '-c', code, REPO, '--help'],
                      self.root, PYTHONPATH=self.root, B5A_MARKER=self.marker)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_not_hijacked(result)


class LocalExecutionEnvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'b5a@example.invalid')
        self.git('config', 'user.name', 'B5A')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        self.git('add', 'README.md')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def test_local_env_forces_safe_path_and_strips_host_pythonpath(self):
        previous = os.environ.get('PYTHONPATH')
        os.environ['PYTHONPATH'] = '/hostile-shadow'
        try:
            env = execution._local_env(self.repo, None)
        finally:
            if previous is None:
                os.environ.pop('PYTHONPATH', None)
            else:
                os.environ['PYTHONPATH'] = previous
        self.assertEqual(env['PYTHONPATH'], str(self.repo))
        self.assertEqual(env['PYTHONSAFEPATH'], '1')
        self.assertEqual(env['PYTHONNOUSERSITE'], '1')
        self.assertNotIn('/hostile-shadow', env.values())
        with self.assertRaises(PMError):
            execution._local_env(self.repo, {'PYTHONSAFEPATH': '0'})

    def test_test_run_child_ignores_host_path_and_receipt_records_env(self):
        probe_dir = self.repo / 'probe'
        probe_dir.mkdir()
        (probe_dir / 'b5a_shadow_probe.py').write_text('print("PROBE")\n', encoding='utf-8')
        previous = os.environ.get('PYTHONPATH')
        os.environ['PYTHONPATH'] = str(probe_dir)
        try:
            out = run_command(self.repo, [sys.executable, '-c',
                                          'import os; print(os.environ.get("PYTHONPATH", ""))'],
                              self.base)
            shadow = run_command(self.repo, [sys.executable, '-c',
                                             'import b5a_shadow_probe'], self.base)
        finally:
            if previous is None:
                os.environ.pop('PYTHONPATH', None)
            else:
                os.environ['PYTHONPATH'] = previous
        self.assertEqual(out['receipt']['exit_code'], 0)
        self.assertNotIn(str(probe_dir), out['log'])
        self.assertTrue(out['receipt']['isolation']['python_env']['safepath'])
        self.assertTrue(out['receipt']['isolation']['python_env']['nousersite'])
        self.assertNotEqual(shadow['receipt']['exit_code'], 0)


if __name__ == '__main__':
    unittest.main()
