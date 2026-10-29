"""Probe test-run's child environment: hostile host PYTHONPATH must not leak.

Writes evidence/B5A/<run>/test-run-env.json.  Uses a throwaway git repo so no
receipts land in the product checkout.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from project_memory.common import git_sha
from project_memory.execution import run_command

RUN = Path(__file__).resolve().parent


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True, encoding='utf-8')


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(repo, 'init', '-q')
        git(repo, 'config', 'user.email', 'b5a@example.invalid')
        git(repo, 'config', 'user.name', 'B5A')
        (repo / 'README.md').write_text('hello\n', encoding='utf-8')
        git(repo, 'add', 'README.md')
        git(repo, 'commit', '-qm', 'base')
        base = git_sha(repo)

        hostile = repo / 'hostile'
        hostile.mkdir()
        (hostile / 'b5a_shadow_probe.py').write_text('print("SHADOW_PROBE")\n',
                                                     encoding='utf-8')
        previous = os.environ.get('PYTHONPATH')
        os.environ['PYTHONPATH'] = str(hostile)
        try:
            env_child = run_command(
                repo,
                [sys.executable, '-c',
                 'import os, sys; print("PYTHONPATH=" + os.environ.get("PYTHONPATH", "")); '
                 'print("SAFEPATH=" + os.environ.get("PYTHONSAFEPATH", "")); '
                 'print("NOUSERSITE=" + os.environ.get("PYTHONNOUSERSITE", "")); '
                 'print("SYSPATH0=" + repr(sys.path[0]))'],
                base)
            probe_child = run_command(
                repo, [sys.executable, '-c', 'import b5a_shadow_probe'], base)
        finally:
            if previous is None:
                os.environ.pop('PYTHONPATH', None)
            else:
                os.environ['PYTHONPATH'] = previous

        env_log = (repo / env_child['log']).read_text(encoding='utf-8')
        probe_log = (repo / probe_child['log']).read_text(encoding='utf-8')
        receipt = env_child['receipt']
        snapshot_tree = str(repo / '.project-memory' / 'snapshots' /
                            receipt['snapshot_id'] / 'tree')
        result = {
            'host_pythonpath': str(hostile),
            'env_child': {'exit_code': receipt['exit_code'], 'log': env_log},
            'probe_child': {'exit_code': probe_child['receipt']['exit_code'],
                            'log': probe_log},
            'receipt': {
                'path': env_child['path'],
                'snapshot_tree': snapshot_tree,
                'trust': receipt['trust'],
                'isolation': receipt['isolation'],
                'content_sha256': receipt['content_sha256'],
            },
            'assertions': {
                'host_path_absent_from_child_env':
                    'PYTHONPATH=' + str(hostile) not in env_log,
                'child_pythonpath_is_snapshot': 'PYTHONPATH=' + snapshot_tree in env_log,
                'safepath_enabled': 'SAFEPATH=1' in env_log,
                'nousersite_enabled': 'NOUSERSITE=1' in env_log,
                'sys_path0_is_explicit_pythonpath':
                    'SYSPATH0=' + repr(snapshot_tree) in env_log,
                'shadow_probe_not_importable': probe_child['receipt']['exit_code'] != 0,
                'receipt_records_python_env':
                    receipt['isolation'].get('python_env', {}).get('safepath') is True,
            },
        }
        (RUN / 'test-run-env.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('wrote test-run-env.json')
        print(json.dumps(result['assertions'], ensure_ascii=False, indent=2))
        return 0 if all(result['assertions'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
