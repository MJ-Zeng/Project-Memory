"""B5A: the CLI must not be replaced by a same-named ``project_memory`` package.

The trusted entry is the native ``project-memory`` wrapper (``bin/project-memory``
/ ``bin/project-memory.cmd``), which isolates the interpreter (``-I -P``) before
any module name is resolved and runs the launcher by absolute path; the launcher
then imports ``project_memory`` only from a trusted root.  ``python -m
project_memory`` additionally fails closed when it can still see a same-named
package on ``sys.path``.  A pip ``module:function`` console_script is NOT used:
it resolves a top-level module through the ambient ``sys.path`` before isolation
and is therefore preemptable (B5A.1).  See ADR-0005.
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
BIN = REPO / 'bin'
IS_WIN = sys.platform == 'win32'
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


def _console_cmd(args):
    """The supported console entry: a native OS wrapper, not a module:function.

    The wrapper isolates the interpreter (-I -P) before Python resolves any
    module name and runs the launcher by absolute path.  ``PROJECT_MEMORY_PYTHON``
    pins the interpreter so the test is deterministic and does not depend on a
    possibly-broken ``python`` on PATH.  See ADR-0005.
    """
    if IS_WIN:
        wrapper = BIN / 'project-memory.cmd'
        comspec = os.environ.get('COMSPEC', 'cmd.exe')
        return [comspec, '/c', wrapper, *args]
    return ['sh', BIN / 'project-memory', *args]


def _make_fake_launcher(base: Path) -> Path:
    """A hostile ``_project_memory_launcher.py`` that only proves it ran."""
    base.mkdir(parents=True, exist_ok=True)
    fake = base / '_project_memory_launcher.py'
    fake.write_text('print("FAKE_LAUNCHER")\n'
                    'raise SystemExit(0)\n', encoding='utf-8')
    return fake


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


class ConsoleEntryTest(unittest.TestCase):
    """The supported console entry is a native OS wrapper (B5A.1).

    A pip ``module:function`` console_script resolves ``_project_memory_launcher``
    through the ambient ``sys.path`` before any isolation, so a same-named file on
    ``PYTHONPATH``/cwd runs first (``FAKE_LAUNCHER``).  The wrapper instead runs
    ``-I -P`` + the launcher by absolute path, so no top-level name is resolved
    through ``sys.path``.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.marker = self.root / 'shadow.marker'

    def tearDown(self):
        self.tmp.cleanup()

    def assert_trusted_help(self, result):
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn('FAKE_LAUNCHER', output)
        self.assertNotIn('SHADOW_INIT', output)
        self.assertNotIn('SHADOW_MAIN', output)
        self.assertFalse(self.marker.exists(), '假冒包写入了 marker')
        self.assertIn('用法', result.stdout)

    def test_console_entry_normal_help(self):
        result = _run(_console_cmd(['--help']), self.root,
                      PROJECT_MEMORY_PYTHON=sys.executable)
        self.assert_trusted_help(result)

    def test_console_entry_ignores_pythonpath_fake_launcher(self):
        fake = _make_fake_launcher(self.root / 'pp')
        result = _run(_console_cmd(['--help']), self.root,
                      PROJECT_MEMORY_PYTHON=sys.executable,
                      PYTHONPATH=fake.parent, B5A_MARKER=self.marker)
        self.assert_trusted_help(result)

    def test_console_entry_ignores_cwd_fake_launcher(self):
        cwd = self.root / 'cwd'
        _make_fake_launcher(cwd)
        result = _run(_console_cmd(['--help']), cwd,
                      PROJECT_MEMORY_PYTHON=sys.executable,
                      B5A_MARKER=self.marker)
        self.assert_trusted_help(result)

    def test_console_entry_ignores_pythonpath_fake_package(self):
        package = _make_shadow(self.root / 'pp')
        result = _run(_console_cmd(['--help']), self.root,
                      PROJECT_MEMORY_PYTHON=sys.executable,
                      PYTHONPATH=package.parent, B5A_MARKER=self.marker)
        self.assert_trusted_help(result)

    def test_console_entry_ignores_cwd_fake_package(self):
        cwd = self.root / 'cwd'
        cwd.mkdir()
        _make_shadow(cwd)
        result = _run(_console_cmd(['--help']), cwd,
                      PROJECT_MEMORY_PYTHON=sys.executable,
                      B5A_MARKER=self.marker)
        self.assert_trusted_help(result)

    def test_pyproject_does_not_ship_module_function_console_script(self):
        import tomllib
        data = tomllib.loads((REPO / 'pyproject.toml').read_text(encoding='utf-8'))
        scripts = data.get('project', {}).get('scripts', {})
        self.assertNotIn('project-memory', scripts,
                         'project-memory 不得是 module:function console_script（B5A.1）')


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
