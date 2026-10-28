"""B0 pre-fix reproduction, run against the baseline code (73be8e3).

The driver executes this with ``cwd`` set to an archive export of the baseline
commit, so ``import project_memory`` resolves the *old* implementation.  It
shows the defect the task fixes: the same commit in a copied checkout is
rejected because ``repo_id`` hashes the absolute path.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True,
                   capture_output=True, text=True, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--base-sha', required=True)
    args = parser.parse_args()

    # Run with cwd set to the baseline export; import the old implementation.
    sys.path.insert(0, str(Path.cwd()))
    from project_memory import execution
    from project_memory.execution import run_command, verify_receipt

    work = Path(tempfile.mkdtemp(prefix='b0-prefix-'))
    try:
        a = work / 'path-a'
        a.mkdir()
        git(a, 'init', '-q')
        git(a, 'config', 'user.email', 'b0-prefix@example.invalid')
        git(a, 'config', 'user.name', 'B0 Pre Fix')
        (a / 'README.md').write_text('b0 prefix\n', encoding='utf-8')
        git(a, 'add', 'README.md')
        git(a, 'commit', '-qm', 'base')
        commit = subprocess.run(['git', '-C', str(a), 'rev-parse', 'HEAD'], check=True,
                                capture_output=True, text=True, encoding='utf-8').stdout.strip()
        out = run_command(a, [sys.executable, '-c', "print('1 passed')"], 'HEAD',
                          executed_by='pm02')
        checked_a = verify_receipt(a, out['path'])
        b = work / 'path-b'
        shutil.copytree(a, b)
        checked_b = verify_receipt(b, out['path'])
        report = {
            'schema': 'b0-pre-fix/v1',
            'baseline_sha': args.base_sha,
            'code_imported_from': str(Path(execution.__file__).resolve().parent),
            'commit_sha': commit,
            'receipt_schema_version': out['receipt']['schema_version'],
            'receipt_repo_id': out['receipt']['repo_id'],
            'repo_id_path_a': execution.repo_id(a),
            'repo_id_path_b': execution.repo_id(b),
            'valid_in_a': checked_a['valid'],
            'problems_in_a': checked_a['problems'],
            'valid_in_b': checked_b['valid'],
            'problems_in_b': checked_b['problems'],
            'reproduced': (checked_a['valid'] is True and checked_b['valid'] is False
                           and execution.repo_id(a) != execution.repo_id(b)),
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding='utf-8', newline='\n')
        print(json.dumps({'reproduced': report['reproduced'],
                          'valid_in_a': report['valid_in_a'],
                          'valid_in_b': report['valid_in_b'],
                          'receipt_repo_id': report['receipt_repo_id'],
                          'repo_id_path_b': report['repo_id_path_b']},
                         ensure_ascii=False))
        return 0 if report['reproduced'] else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
