"""Probe: can a verifier in the copied checkout (path B) create a new
verification record that references the receipt produced in path A?

This exercises the remaining ``_repo_matches`` check on ``target_repository``
in ``project_memory/coordination.py``; it is a workflow observation, not an
AC-1(b) signed-evidence test.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
CANDIDATE = Path(sys.argv[1]).resolve()
REMOTE = 'https://github.com/pilot-org/probe-a'
CRITERION = '模块通过测试'


def run(argv, cwd):
    import os
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=env)


def cli(repo, *args):
    return run([PYTHON, '-m', 'project_memory.cli', *args, '--repo', str(repo)], CANDIDATE)


def git(repo, *args):
    out = run(['git', '-C', str(repo), *args], repo)
    if out.returncode:
        raise SystemExit(out.stderr)
    return out.stdout.strip()


def main():
    tmp = Path(tempfile.mkdtemp(prefix='b0-probe-'))
    a = tmp / 'path-a'
    a.mkdir()
    git(a, 'init', '-q')
    git(a, 'config', 'user.email', 'pm03@review.invalid')
    git(a, 'config', 'user.name', 'PM-03')
    (a / 'README.md').write_text('probe\n', encoding='utf-8')
    git(a, 'add', 'README.md')
    git(a, 'commit', '-qm', 'base')
    git(a, 'remote', 'add', 'origin', REMOTE)
    head = git(a, 'rev-parse', 'HEAD')
    command = f'"{PYTHON}" -c "print(1)"'
    cli(a, 'goal', 'create', '--id', 'G-P', '--title', 'probe', '--outcome', 'probe',
        '--owner', 'reviewer', '--criterion', CRITERION)
    payload = json.loads(cli(a, 'test-run', '--command', command, '--agent', 'reviewer').stdout)
    receipt_ref = payload['path']
    log_rel = payload['log']
    cli(a, 'run', 'start', '--goal', 'G-P', '--task', '326', '--run-id', 'run-target',
        '--agent', 'dev', '--model-provider', 'p', '--model-id', 'm1', '--session-id', 's1',
        '--base-sha', head)
    cli(a, 'run', 'finish', '--task', '326', '--run-id', 'run-target', '--completed', 'x',
        '--head-sha', head, '--test-command', command, '--test-exit', '0', '--test-log', log_rel)
    b = tmp / 'path-b'
    shutil.copytree(a, b)

    def mapping_for(repo, tag):
        return {'criteria': [{
            'criterion_id': 'C1', 'goal_id': 'G-P', 'task_id': '326',
            'criterion_description': CRITERION, 'target_repository': str(repo),
            'target_commit_sha': head, 'evidence_id': f'EV-{tag}',
            'evidence_source': 'test', 'evidence_command': command,
            'evidence_log': log_rel, 'evidence_exit_code': 0,
            'evidence_receipt': receipt_ref, 'execution_status': 'passed',
            'coverage_claim': 'covers', 'coverage_review_status': 'confirmed',
            'independent_verifier': 'verifier-b', 'verification_result': 'pass'}]}

    cli(b, 'run', 'start', '--goal', 'G-P', '--task', '326', '--run-id', 'run-verifier',
        '--agent', 'verifier-b', '--model-provider', 'p', '--model-id', 'm2',
        '--session-id', 's2', '--base-sha', head, '--role', 'verifier')
    results = {}
    for tag, declared in (('declared_a_path', str(a)), ('declared_b_path', str(b))):
        path = HERE / f'_probe_{tag}.json'
        path.write_text(json.dumps(mapping_for(declared, tag)), encoding='utf-8')
        proc = cli(b, 'verify', '--target-run', 'run-target', '--verifier-run', 'run-verifier',
                   '--standard', 'acceptance', '--verdict', 'pass',
                   '--evidence-level', 'locally_observed', '--test-command', command,
                   '--test-exit', '0', '--test-log', log_rel, '--test-receipt', receipt_ref,
                   '--criterion-evidence', str(path), '--verification-id', 'VER-' + tag)
        results[tag] = {'exit_code': proc.returncode,
                        'stdout_tail': proc.stdout[-800:], 'stderr_tail': proc.stderr[-800:]}
    out = {'workdir': str(tmp), 'receipt_ref': receipt_ref, 'results': results,
           'assertions': {
               'verify_with_declared_a_path_rejected': results['declared_a_path']['exit_code'] == 1,
               'verify_with_declared_b_path_accepted_structurally':
                   results['declared_b_path']['exit_code'] in (0, 2),
           }}
    (HERE / 'verify_in_copy.json').write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                              encoding='utf-8')
    print(json.dumps(out['assertions'], ensure_ascii=False))


if __name__ == '__main__':
    main()
