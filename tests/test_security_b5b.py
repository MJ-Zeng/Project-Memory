"""B5B: default ``test-run`` must not silently execute unisolated code.

The CLI now refuses to run unless the caller explicitly picks a mode:

* no ``--trusted`` and no ``--allow-local-untrusted`` -> refuse, exit 3, no
  snapshot, no receipt, no command side effects;
* ``--allow-local-untrusted`` -> plain child process, receipt labelled
  ``local_untrusted`` (``isolation.mode=none``);
* ``--trusted`` -> WSL2 namespace; if unavailable, fail closed (exit 3) with no
  fallback to a local child process.

See ``docs/decisions/ADR-0006-test-run-isolation.md``.
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from project_memory import trusted_exec
from project_memory.common import git_sha

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
DISABLE_ENV = trusted_exec.DISABLE_ENV
MARKER_SCRIPT = (REPO / 'fixtures' / 'b5b' / 'marker-command.py').read_text(encoding='utf-8')
IS_WIN = sys.platform == 'win32'


def _join(argv):
    return subprocess.list2cmdline(argv) if IS_WIN else shlex.join(argv)


def _cli(repo, *args, env_extra=None, timeout=300):
    """Run the real CLI (``python -m project_memory``) against ``repo``."""
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT)
    env['PYTHONUTF8'] = '1'
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, '-m', 'project_memory', *args, '--repo', str(repo)],
                          cwd=str(repo), env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


def _meta_count(repo, kind, pattern='*'):
    base = Path(repo) / '.project-memory' / kind
    return len(list(base.glob(pattern))) if base.is_dir() else 0


class B5BTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'marker.py').write_text(MARKER_SCRIPT, encoding='utf-8')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        self.git('init', '-q')
        self.git('config', 'user.email', 'b5b@example.invalid')
        self.git('config', 'user.name', 'B5B')
        self.git('add', 'marker.py', 'README.md')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)
        self.marker = self.root / 'host-marker'

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def local_command(self):
        return _join([sys.executable, 'marker.py', str(self.marker)])

    # AC-1: no mode flag -> refuse, no execution, no receipt, no marker.
    def test_default_without_flag_refuses_without_side_effects(self):
        before_receipts = _meta_count(self.repo, 'receipts')
        before_snapshots = _meta_count(self.repo, 'snapshots')
        result = _cli(self.repo, 'test-run', '--command', self.local_command(),
                      '--commit', self.base)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('拒绝执行', result.stderr)
        self.assertFalse(self.marker.exists(), '默认拒绝时命令仍被执行，写入了宿主 marker')
        self.assertEqual(_meta_count(self.repo, 'receipts'), before_receipts,
                         '默认拒绝时不应写收据')
        self.assertEqual(_meta_count(self.repo, 'snapshots'), before_snapshots,
                         '默认拒绝时不应创建快照')
        self.assertEqual(result.stdout.strip(), '', '默认拒绝不应输出成功结果')

    # Both flags is ambiguous -> refuse too.
    def test_both_modes_refused(self):
        result = _cli(self.repo, 'test-run', '--command', self.local_command(),
                      '--commit', self.base, '--trusted', '--allow-local-untrusted')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('不能同时使用', result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertEqual(_meta_count(self.repo, 'receipts'), 0)

    # AC-2/AC-5: explicit local executes and the receipt tells the truth.
    def test_explicit_local_executes_and_labels_untrusted(self):
        result = _cli(self.repo, 'test-run', '--command', self.local_command(),
                      '--commit', self.base, '--allow-local-untrusted',
                      '--agent', 'b5b-test')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists(), '显式 local 应执行命令并写入 marker')
        self.assertIn('警告', result.stderr)
        payload = json.loads(result.stdout)
        receipt = payload['receipt']
        self.assertEqual(payload['mode'], 'local')
        self.assertEqual(receipt['exit_code'], 0)
        self.assertEqual(receipt['isolation']['mode'], 'none')
        self.assertFalse(receipt['isolation']['os_isolation'])
        self.assertEqual(receipt['execution_provenance']['kind'], 'local_untrusted')
        self.assertFalse(receipt['execution_provenance']['trusted'])
        self.assertEqual(receipt['trust'], 'local_untrusted')
        self.assertNotEqual(receipt['isolation']['mode'], trusted_exec.MODE)
        # Receipt file really exists where the result points.
        self.assertTrue((self.repo / payload['path']).is_file())

    # AC-3: trusted executes inside WSL2 namespace; host marker never appears.
    @unittest.skipUnless(trusted_exec.wsl_available()[0], 'WSL2 sandbox 不可用')
    def test_trusted_runs_isolated_and_host_marker_absent(self):
        sandbox_cmd = 'python3 marker.py /tmp/b5b-sandbox-marker'
        result = _cli(self.repo, 'test-run', '--command', sandbox_cmd,
                      '--commit', self.base, '--trusted', '--agent', 'b5b-test',
                      timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        receipt = payload['receipt']
        self.assertEqual(receipt['exit_code'], 0, '沙箱内命令应成功执行')
        self.assertEqual(receipt['isolation']['mode'], trusted_exec.MODE)
        self.assertTrue(receipt['isolation']['os_isolation'])
        self.assertEqual(receipt['execution_provenance']['kind'], 'trusted_launcher')
        self.assertEqual(receipt['trust'], 'isolated_local_attestation')
        self.assertTrue(receipt.get('attestation_path'))
        log = (self.repo / receipt['log_path']).read_text(encoding='utf-8')
        self.assertIn('marker-written', log)

        # A command that targets the host path must not reach it.
        host_cmd = f'python3 marker.py {trusted_exec.to_wsl_path(self.marker)}'
        result2 = _cli(self.repo, 'test-run', '--command', host_cmd,
                       '--commit', self.base, '--trusted', '--agent', 'b5b-test',
                       timeout=600)
        self.assertEqual(result2.returncode, 0, result2.stdout + result2.stderr)
        payload2 = json.loads(result2.stdout)
        self.assertFalse(self.marker.exists(), 'trusted 模式下宿主 marker 不得出现')
        log2 = (self.repo / payload2['receipt']['log_path']).read_text(encoding='utf-8')
        self.assertIn('marker-write-failed', log2,
                      '沙箱内应看不到宿主路径（/mnt 被屏蔽）')

    # AC-4/AC-6: trusted unavailable -> exit 3, no fallback to local, no execution.
    def test_trusted_unavailable_fails_closed_without_fallback(self):
        before_receipts = _meta_count(self.repo, 'receipts')
        before_snapshots = _meta_count(self.repo, 'snapshots')
        result = _cli(self.repo, 'test-run', '--command', self.local_command(),
                      '--commit', self.base, '--trusted',
                      env_extra={DISABLE_ENV: '1'})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'BLOCKED')
        self.assertIsNone(payload['receipt'])
        self.assertIn('fail-closed', payload['error'])
        self.assertFalse(self.marker.exists(), 'trusted 不可用时不得回退 local 执行')
        self.assertEqual(_meta_count(self.repo, 'receipts'), before_receipts)
        self.assertEqual(_meta_count(self.repo, 'snapshots'), before_snapshots)

    # AC-8: hostile host PYTHONPATH must not leak into the local child (B5A env cleanup).
    def test_local_child_ignores_host_pythonpath(self):
        hostile = self.root / 'hostile'
        hostile.mkdir()
        (hostile / 'b5b_shadow_probe.py').write_text('print("SHADOW")\n', encoding='utf-8')
        probe = self.root / 'probe.json'
        script = ('import json, os, sys\n'
                  'try:\n'
                  '    import b5b_shadow_probe\n'
                  '    imported = True\n'
                  'except Exception:\n'
                  '    imported = False\n'
                  'json.dump({"pythonpath": os.environ.get("PYTHONPATH", ""),\n'
                  '           "imported": imported, "sys_path0": sys.path[0]},\n'
                  '          open(sys.argv[1], "w", encoding="utf-8"))\n')
        (self.repo / 'probe.py').write_text(script, encoding='utf-8')
        self.git('add', 'probe.py')
        self.git('commit', '-qm', 'probe')
        base = git_sha(self.repo)
        command = _join([sys.executable, 'probe.py', str(probe)])
        result = _cli(self.repo, 'test-run', '--command', command, '--commit', base,
                      '--allow-local-untrusted',
                      env_extra={'PYTHONPATH': os.pathsep.join([str(ROOT), str(hostile)])})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(probe.read_text(encoding='utf-8'))
        self.assertNotIn(str(hostile), observed['pythonpath'])
        self.assertFalse(observed['imported'], '子进程不应导入宿主 PYTHONPATH 中的模块')
        self.assertNotIn(str(hostile), observed['sys_path0'])
        payload = json.loads(result.stdout)
        self.assertTrue(payload['receipt']['isolation']['python_env']['safepath'])
        self.assertTrue(payload['receipt']['isolation']['python_env']['nousersite'])


class B5AWrapperRegression(unittest.TestCase):
    """AC-8: the B5A native wrapper still resists a same-named package on PYTHONPATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.marker = self.root / 'shadow.marker'

    def tearDown(self):
        self.tmp.cleanup()

    def test_wrapper_ignores_pythonpath_shadow_package(self):
        shadow = self.root / 'shadow' / 'project_memory'
        shadow.mkdir(parents=True)
        (shadow / '__init__.py').write_text(
            'import os\nfrom pathlib import Path\n'
            'm = os.environ.get("B5B_MARKER")\n'
            'if m:\n    Path(m).write_text("init")\n'
            'print("SHADOW_INIT")\n', encoding='utf-8')
        (shadow / '__main__.py').write_text(
            'print("SHADOW_MAIN")\nraise SystemExit(0)\n', encoding='utf-8')
        if IS_WIN:
            cmd = [os.environ.get('COMSPEC', 'cmd.exe'), '/c',
                   str(REPO / 'bin' / 'project-memory.cmd'), '--help']
        else:
            cmd = ['sh', str(REPO / 'bin' / 'project-memory'), '--help']
        env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
        env.update({'PROJECT_MEMORY_PYTHON': sys.executable,
                    'PYTHONPATH': str(shadow.parent), 'B5B_MARKER': str(self.marker)})
        result = subprocess.run(cmd, cwd=str(self.root), env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=120)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn('SHADOW_INIT', output)
        self.assertNotIn('SHADOW_MAIN', output)
        self.assertFalse(self.marker.exists())
        self.assertIn('用法', result.stdout)


if __name__ == '__main__':
    unittest.main()
