"""Independent PM-03 probe: run_command/test-run child must not import a fake
package/module from a hostile host PYTHONPATH, and must record env cleanup."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CAND = Path(r"C:\Documents\02_Research\Code\project-memory-verification-lab\import-workspace\pm-pilot-03\.pilot\b5a-candidate")
sys.path.insert(0, str(CAND))
from project_memory.common import git_sha
from project_memory.execution import run_command

OUT = Path(r"C:\Users\ZMJ\AppData\Local\Temp\b5a-review-20261029T011209Z")


def git(repo, *a):
    subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True,
                   text=True, encoding='utf-8')


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(repo, 'init', '-q')
        git(repo, 'config', 'user.email', 'r@example.invalid')
        git(repo, 'config', 'user.name', 'R')
        (repo / 'README.md').write_text('hi\n', encoding='utf-8')
        git(repo, 'add', 'README.md')
        git(repo, 'commit', '-qm', 'base')
        base = git_sha(repo)

        hostile = repo / 'hostile'
        hostile.mkdir()
        (hostile / 'b5a_leak_probe.py').write_text('print("LEAK")\n', encoding='utf-8')
        fake = hostile / 'project_memory'
        fake.mkdir()
        (fake / '__init__.py').write_text('print("SHADOW_INIT")\n', encoding='utf-8')

        prev = os.environ.get('PYTHONPATH')
        os.environ['PYTHONPATH'] = str(hostile)
        try:
            envres = run_command(repo, [sys.executable, '-c',
                'import os,sys;'
                'print("PYTHONPATH="+os.environ.get("PYTHONPATH",""));'
                'print("SAFEPATH="+os.environ.get("PYTHONSAFEPATH",""));'
                'print("NOUSERSITE="+os.environ.get("PYTHONNOUSERSITE",""));'
                'print("SYSPATH0="+repr(sys.path[0]))'], base)
            leak = run_command(repo, [sys.executable, '-c', 'import b5a_leak_probe'], base)
            shadow = run_command(repo, [sys.executable, '-c',
                                        'import project_memory;print("IMPORTED",project_memory.__file__)'], base)
        finally:
            if prev is None:
                os.environ.pop('PYTHONPATH', None)
            else:
                os.environ['PYTHONPATH'] = prev

        elog = (repo / envres['log']).read_text(encoding='utf-8')
        slog = (repo / shadow['log']).read_text(encoding='utf-8')
        receipt = envres['receipt']
        snap = receipt.get('snapshot_id')
        snap_tree = str(repo / '.project-memory' / 'snapshots' / snap / 'tree') if snap else None
        iso = receipt.get('isolation', {})
        penv = iso.get('python_env', {})
        result = {
            'host_pythonpath': str(hostile),
            'env_exit': receipt['exit_code'],
            'env_log': elog,
            'leak_exit': leak['receipt']['exit_code'],
            'shadow_exit': shadow['receipt']['exit_code'],
            'shadow_log': slog,
            'receipt_isolation': iso,
            'assertions': {
                'host_path_not_in_child_env': str(hostile) not in elog,
                'child_pythonpath_is_snapshot': snap_tree is not None and ('PYTHONPATH=' + snap_tree) in elog,
                'safepath_1': 'SAFEPATH=1' in elog,
                'nousersite_1': 'NOUSERSITE=1' in elog,
                'leak_module_not_importable': leak['receipt']['exit_code'] != 0,
                'shadow_pkg_not_executed': 'SHADOW_INIT' not in slog,
                'receipt_python_env_safepath': penv.get('safepath') is True,
                'receipt_python_env_nousersite': penv.get('nousersite') is True,
                'receipt_python_env_stripped_has_pythonpath': 'PYTHONPATH' in (penv.get('stripped') or []),
            },
        }
        (OUT / 'test-run-env.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result['assertions'], indent=2))
        return 0 if all(result['assertions'].values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
