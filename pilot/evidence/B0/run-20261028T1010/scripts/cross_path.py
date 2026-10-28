"""B0 AC-1: cross-path positive case.

Creates a repository at path A, mints a receipt with ``test-run``, records a
verification, copies the whole repository to path B, and checks that in B

* ``verify_receipt.valid`` is true,
* ``_verification_current`` is true,

for the same commit.  Only the candidate code (``--code-root``) is imported.
``goal evidence`` itself needs a signed authority fixture and is therefore not
exercised here (see the Handoff's NOT VERIFIED section).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


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


def run(argv, cwd, log_dir, seq, steps, expected=0, name='step'):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    result = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env=env)
    log = log_dir / f'{seq:02d}-{name}.log'
    stdout = result.stdout.replace('\r\n', '\n').replace('\r', '\n')
    stderr = result.stderr.replace('\r\n', '\n').replace('\r', '\n')
    log.write_text(stdout + '\n--- stderr ---\n' + stderr, encoding='utf-8', newline='\n')
    steps.append({
        'seq': seq,
        'cwd': str(cwd),
        'command': subprocess.list2cmdline(argv),
        'exit_code': result.returncode,
        'expected_exit': expected,
        'stdout_preview': result.stdout[-3000:],
        'stderr_preview': result.stderr[-3000:],
        'log': str(log),
        'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
    })
    return result


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True,
                   capture_output=True, text=True, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--log-dir', required=True)
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
    from project_memory.coordination import _verification_current
    from project_memory.execution import verify_receipt

    py = sys.executable
    a = work / 'path-a'
    a.mkdir()
    git(a, 'init', '-q')
    git(a, 'config', 'user.email', 'b0-cross-path@example.invalid')
    git(a, 'config', 'user.name', 'B0 Cross Path')
    (a / 'README.md').write_text('b0 cross path\n', encoding='utf-8')
    (a / 'tests').mkdir()
    (a / 'tests/check.py').write_text('print("1 passed")\n', encoding='utf-8')
    git(a, 'add', 'README.md', 'tests/check.py')
    git(a, 'commit', '-qm', 'base')
    git(a, 'remote', 'add', 'origin', 'https://github.com/pilot-org/b0-cross-path')
    commit = subprocess.run(['git', '-C', str(a), 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True, encoding='utf-8').stdout.strip()

    def cli(*parts):
        return [py, '-m', 'project_memory', *[str(part) for part in parts],
                '--repo', str(a)]

    steps = []
    run(cli('goal', 'create', '--id', 'G-B0', '--title', 'B0 cross-path',
            '--background', 'B0 AC-1', '--outcome', 'same repo, other path',
            '--owner', 'PM-02', '--criterion', '模块通过测试'),
        code_root, log_dir, 1, steps, name='goal-create')

    command = f'"{py}" -c "print(\'1 passed\')"'
    test_out = work / 'test-run.json'
    run(cli('test-run', '--command', command, '--commit', commit,
            '--agent', 'pm02', '--output', str(test_out)),
        code_root, log_dir, 2, steps, name='test-run')
    receipt_result = json.loads(test_out.read_text(encoding='utf-8'))
    receipt_ref = receipt_result['path']

    run(cli('run', 'start', '--goal', 'G-B0', '--task', '3', '--run-id', 'run-target',
            '--agent', 'dev-agent', '--model-provider', 'qodercn',
            '--model-id', 'executor-model', '--base-sha', commit, '--role', 'executor'),
        code_root, log_dir, 3, steps, name='run-start-target')
    run(cli('run', 'finish', '--task', '3', '--run-id', 'run-target',
            '--completed', 'implemented', '--remaining', 'verify',
            '--head-sha', commit, '--test-command', command,
            '--test-exit', '0', '--test-log', receipt_result['log']),
        code_root, log_dir, 4, steps, name='run-finish-target')
    run(cli('run', 'start', '--goal', 'G-B0', '--task', '3', '--run-id', 'run-verifier',
            '--agent', 'verifier-agent', '--model-provider', 'qodercn',
            '--model-id', 'verifier-model', '--base-sha', commit, '--role', 'verifier'),
        code_root, log_dir, 5, steps, name='run-start-verifier')

    mapping = {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-B0', 'task_id': '3',
        'criterion_description': '模块通过测试',
        'target_repository': str(a), 'target_commit_sha': commit,
        'evidence_id': 'EV-XP-1', 'evidence_source': 'test',
        'evidence_command': receipt_result['receipt']['command'],
        'evidence_log': receipt_result['log'], 'evidence_exit_code': 0,
        'evidence_receipt': receipt_ref, 'execution_status': 'passed',
        'coverage_claim': '覆盖对应标准', 'coverage_review_status': 'confirmed',
        'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}
    mapping_path = work / 'mapping.json'
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding='utf-8')

    # The build configures no signer, so `verify` writes a MANUAL_REVIEW_REQUIRED
    # record and exits 2; that record is still what _verification_current tests.
    run(cli('verify', '--target-run', 'run-target', '--verifier-run', 'run-verifier',
            '--standard', 'acceptance', '--verdict', 'pass',
            '--evidence-level', 'locally_observed', '--test-receipt', receipt_ref,
            '--criterion-evidence', str(mapping_path),
            '--verification-id', 'VER-B0-XP'),
        code_root, log_dir, 6, steps, expected=2, name='verify')

    verification_path = a / '.project-memory/verifications/3/VER-B0-XP.json'
    verification = json.loads(verification_path.read_text(encoding='utf-8'))

    b = work / 'path-b'
    shutil.copytree(a, b)

    checked_a = verify_receipt(a, receipt_ref)
    checked_b = verify_receipt(b, receipt_ref)
    identity_a = execution.repo_identity(a)
    identity_b = execution.repo_identity(b)
    current_a = _verification_current(a, verification)
    current_b = _verification_current(b, verification)
    same_commit = (checked_b.get('receipt') or {}).get('commit_sha') == commit

    assertions = {
        'receipt_valid_in_a': checked_a['valid'] is True,
        'receipt_valid_in_b': checked_b['valid'] is True,
        'verification_current_in_a': current_a is True,
        'verification_current_in_b': current_b is True,
        'same_identity': identity_a['id'] == identity_b['id'],
        'same_commit': same_commit,
        'identity_kind': identity_b['kind'] == 'remote+root',
        'identity_portable': (checked_b.get('identity') or {}).get('portable') is True,
        'identity_has_no_path': str(b) not in json.dumps(identity_b),
    }
    report = {
        'schema': 'b0-cross-path/v1',
        'run_id': out.parent.name,
        'code_root': str(code_root),
        'paths': {'a': str(a), 'b': str(b)},
        'commit_sha': commit,
        'receipt': {
            'ref': receipt_ref,
            'receipt_id': receipt_result['receipt']['receipt_id'],
            'schema_version': receipt_result['receipt']['schema_version'],
            'repo_id': receipt_result['receipt']['repo_id'],
            'content_sha256': receipt_result['receipt']['content_sha256'],
        },
        'verification': {
            'id': verification['verification_id'],
            'status': verification['status'],
            'target_head_sha': verification['target_head_sha'],
        },
        'identity_a': identity_a,
        'identity_b': identity_b,
        'verify_receipt_in_b': {
            'valid': checked_b['valid'],
            'problems': checked_b['problems'],
            'identity': checked_b.get('identity'),
            'legacy_path_bound': checked_b.get('legacy_path_bound'),
        },
        'verify_receipt_in_a': {'valid': checked_a['valid'],
                                'problems': checked_a['problems']},
        'verification_current_in_a': current_a,
        'verification_current_in_b': current_b,
        'assertions': assertions,
        'steps': steps,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8',
                   newline='\n')
    print(json.dumps({'assertions': assertions,
                      'valid_in_b': checked_b['valid'],
                      'current_in_b': current_b}, ensure_ascii=False))
    return 0 if all(assertions.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
