"""Baseline (pre-fix) reproduction for B0, run with PM-03's own fixture.

Uses the BASE checkout only for the receipt generation + verification so the
P-1 failure can be observed directly, then repeats the copy with the candidate
checkout to show the delta on equivalent inputs.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
BASE = Path(sys.argv[1]).resolve()
CANDIDATE = Path(sys.argv[2]).resolve()
REMOTE = 'https://github.com/pilot-org/baseline-a'

CHECK = r'''
import json, sys
from pathlib import Path
from project_memory.execution import verify_receipt, repo_id
repo = Path(sys.argv[1]); ref = sys.argv[2]
checked = verify_receipt(repo, ref)
print(json.dumps({'valid': checked['valid'], 'problems': checked['problems'],
                  'repo_id': (checked['receipt'] or {}).get('repo_id'),
                  'schema': (checked['receipt'] or {}).get('schema_version'),
                  'identity': checked.get('identity'),
                  'current_repo_id': repo_id(repo)},
                 ensure_ascii=False))
'''


def run(argv, cwd):
    env = dict(__import__('os').environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=env)


def git(repo, *args):
    proc = run(['git', '-C', str(repo), *args], repo)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr)
    return proc.stdout.strip()


def make_repo(path):
    path.mkdir(parents=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.email', 'pm03@review.invalid')
    git(path, 'config', 'user.name', 'PM-03 Reviewer')
    (path / 'README.md').write_text('baseline fixture\n', encoding='utf-8')
    git(path, 'add', 'README.md')
    git(path, 'commit', '-qm', 'base')
    git(path, 'remote', 'add', 'origin', REMOTE)
    return git(path, 'rev-parse', 'HEAD')


def main():
    tmp = Path(tempfile.mkdtemp(prefix='b0-baseline-'))
    repo_a = tmp / 'path-a'
    head = make_repo(repo_a)
    command = f'"{PYTHON}" -c "print(1)"'
    produced = run([PYTHON, '-m', 'project_memory.cli', 'test-run', '--command', command,
                    '--agent', 'pm03', '--repo', str(repo_a)], BASE)
    if produced.returncode != 0:
        raise SystemExit(produced.stderr)
    payload = json.loads(produced.stdout)
    ref = payload['path']
    repo_b = tmp / 'path-b'
    shutil.copytree(repo_a, repo_b)

    def check(code_root, repo):
        proc = run([PYTHON, '-c', CHECK, str(repo), ref], code_root)
        return {'exit_code': proc.returncode, **json.loads(proc.stdout)}

    base_a = check(BASE, repo_a)
    base_b = check(BASE, repo_b)
    cand_b = check(CANDIDATE, repo_b)
    path_hash_a = hashlib.sha256(str(repo_a.resolve()).casefold().encode('utf-8')).hexdigest()
    path_hash_b = hashlib.sha256(str(repo_b.resolve()).casefold().encode('utf-8')).hexdigest()
    result = {
        'workdir': str(tmp), 'head': head, 'receipt_path': ref,
        'receipt_schema_from_base': payload['receipt'].get('schema_version'),
        'path_hash_a': path_hash_a, 'path_hash_b': path_hash_b,
        'base_a': base_a, 'base_b': base_b, 'candidate_b_on_base_receipt': cand_b,
        'assertions': {
            'base_valid_at_original_path': base_a['valid'],
            'base_invalid_after_copy': not base_b['valid'],
            'base_copy_error_is_repository_identity': any('仓库' in p for p in base_b['problems']),
            'base_repo_id_equals_sha256_of_absolute_path': base_a['repo_id'] == path_hash_a,
            'base_current_identity_differs_after_copy': base_b['current_repo_id'] == path_hash_b,
            'candidate_rejects_legacy_receipt_across_path': not cand_b['valid'],
        },
    }
    (HERE / 'baseline_before.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['assertions'], ensure_ascii=False))
    print('WORKDIR=' + str(tmp))


if __name__ == '__main__':
    main()
