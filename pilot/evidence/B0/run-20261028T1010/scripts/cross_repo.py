"""B0 AC-2/AC-4: cross-repository negative cases plus legacy receipt marking.

Cases (all receipts are minted in repository A):

1. copy of A (same root commit, same remote)  -> accepted (positive control);
2. copy of A with a different remote         -> rejected, error names repository;
3. fresh repository with a different root    -> rejected, error names repository;
4. A's receipt downgraded to schema 1.0 and checked at its original path
   -> accepted but labelled ``legacy_path_bound`` / non-portable;
5. copy of A carrying that legacy receipt    -> rejected, error names legacy.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REMOTE_A = 'https://github.com/pilot-org/repo-a'
REMOTE_B = 'https://github.com/pilot-org/repo-b'


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True,
                   capture_output=True, text=True, encoding='utf-8')


def rmtree(path):
    """Remove a tree that may contain read-only files (Windows .git objects)."""
    def onerror(func, target, exc):
        try:
            os.chmod(target, 0o700)
            func(target)
        except OSError:
            pass
    if Path(path).exists():
        shutil.rmtree(path, onerror=onerror)


def make_repo(path, text, remote=None):
    path.mkdir(parents=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.email', 'b0-cross-repo@example.invalid')
    git(path, 'config', 'user.name', 'B0 Cross Repo')
    (path / 'README.md').write_text(text, encoding='utf-8')
    git(path, 'add', 'README.md')
    git(path, 'commit', '-qm', 'base')
    if remote:
        git(path, 'remote', 'add', 'origin', remote)
    return subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], check=True,
                          capture_output=True, text=True, encoding='utf-8').stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--log-dir', required=True)
    parser.add_argument('--checker', required=True)
    args = parser.parse_args()

    code_root = Path(args.code_root).resolve()
    work = Path(args.work).resolve()
    out = Path(args.out).resolve()
    log_dir = Path(args.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    rmtree(work)
    work.mkdir(parents=True)

    sys.path.insert(0, str(code_root))
    from project_memory import execution
    from project_memory.execution import run_command

    a = work / 'repo-a'
    commit_a = make_repo(a, 'repo a\n', REMOTE_A)
    minted = run_command(a, [sys.executable, '-c', "print('1 passed')"], 'HEAD',
                         executed_by='pm02')
    receipt_ref = minted['path']

    steps = []
    seq = [0]

    def check(name, repo, expected, receipt=None):
        seq[0] += 1
        argv = [sys.executable, str(Path(args.checker)), '--code-root', str(code_root),
                '--repo', str(repo), '--receipt', receipt or receipt_ref]
        result = subprocess.run(argv, cwd=str(code_root), capture_output=True, text=True,
                                encoding='utf-8', errors='replace',
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        log = log_dir / f'{seq[0]:02d}-{name}.log'
        stdout = result.stdout.replace('\r\n', '\n').replace('\r', '\n')
        stderr = result.stderr.replace('\r\n', '\n').replace('\r', '\n')
        log.write_text(stdout + '\n--- stderr ---\n' + stderr,
                       encoding='utf-8', newline='\n')
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {'valid': None, 'problems': ['checker output was not JSON'],
                      'raw': result.stdout}
        steps.append({
            'case': name,
            'repo': str(repo),
            'command': subprocess.list2cmdline(argv),
            'exit_code': result.returncode,
            'expected_exit': expected,
            'result': parsed,
            'log': str(log),
            'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
        })
        return result.returncode, parsed

    same = work / 'same-identity-copy'
    shutil.copytree(a, same)
    same_code, same_result = check('same-identity-copy', same, 0)

    other_remote = work / 'other-remote-copy'
    shutil.copytree(a, other_remote)
    git(other_remote, 'remote', 'set-url', 'origin', REMOTE_B)
    remote_code, remote_result = check('different-remote', other_remote, 3)

    other_root = work / 'other-root-repo'
    make_repo(other_root, 'different history\n', REMOTE_A)
    copied = other_root / receipt_ref
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_text((a / receipt_ref).read_text(encoding='utf-8'), encoding='utf-8')
    root_code, root_result = check('different-root', other_root, 3)

    # Downgrade A's receipt to schema 1.0 (path-bound) without deleting history.
    legacy_path = a / receipt_ref
    legacy = json.loads(legacy_path.read_text(encoding='utf-8'))
    legacy['schema_version'] = '1.0'
    legacy.pop('repo_identity', None)
    legacy['repo_id'] = execution._legacy_repo_id(a)
    legacy['content_sha256'] = execution._canonical_receipt_digest(legacy)
    legacy_path.write_text(json.dumps(legacy, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    legacy_code, legacy_result = check('legacy-original-path', a, 0)
    legacy_copy = work / 'legacy-copy'
    shutil.copytree(a, legacy_copy)
    legacy_copy_code, legacy_copy_result = check('legacy-copied-path', legacy_copy, 3)

    identity_a = execution.repo_identity(a)
    identity_remote = execution.repo_identity(other_remote)
    identity_root = execution.repo_identity(other_root)
    assertions = {
        'same_copy_accepted': same_code == 0 and same_result.get('valid') is True,
        'different_remote_rejected': remote_code == 3 and remote_result.get('valid') is False,
        'different_remote_error_names_repository': any(
            '仓库' in problem for problem in remote_result.get('problems', [])),
        'different_root_rejected': root_code == 3 and root_result.get('valid') is False,
        'different_root_error_names_repository': any(
            '仓库' in problem for problem in root_result.get('problems', [])),
        'identities_differ_for_remote': identity_a['id'] != identity_remote['id'],
        'identities_differ_for_root': identity_a['id'] != identity_root['id'],
        'legacy_valid_at_original_path': (legacy_code == 0
                                          and legacy_result.get('valid') is True
                                          and legacy_result.get('legacy_path_bound') is True
                                          and (legacy_result.get('identity') or {}).get('portable') is False),
        'legacy_rejected_across_paths': (legacy_copy_code == 3
                                         and legacy_copy_result.get('valid') is False),
        'legacy_error_names_legacy': any(
            'legacy' in problem for problem in legacy_copy_result.get('problems', [])),
    }
    report = {
        'schema': 'b0-cross-repo/v1',
        'run_id': out.parent.name,
        'code_root': str(code_root),
        'receipt': {'ref': receipt_ref,
                    'receipt_id': minted['receipt']['receipt_id'],
                    'repo_id': minted['receipt']['repo_id']},
        'commit_a': commit_a,
        'identities': {
            'repo_a': identity_a,
            'other_remote': identity_remote,
            'other_root': identity_root,
        },
        'cases': steps,
        'assertions': assertions,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8',
                   newline='\n')
    print(json.dumps({'assertions': assertions}, ensure_ascii=False))
    return 0 if all(assertions.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
