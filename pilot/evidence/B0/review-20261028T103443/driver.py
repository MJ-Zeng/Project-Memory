"""PM-03 independent B0 reproduction driver.

Written from scratch for review; it does not import or call any script that
ships in the candidate tree.  Code under test is invoked only through the
``project_memory`` package of a given checkout (candidate or base), by running
``python -m project_memory.cli`` / ``-c`` snippets with that checkout as cwd.

Outputs review-<run>/cross_path.json, cross_repo.json, legacy.json, and appends
one JSON line per command to commands.jsonl.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATE = Path(sys.argv[1]).resolve()
BASE = Path(sys.argv[2]).resolve()
PYTHON = sys.executable
CRITERION = '模块通过测试'
REMOTE_A = 'https://github.com/pilot-org/portable-a'
REMOTE_B = 'https://gitlab.example.invalid/pilot-org/portable-a'

commands_path = HERE / 'commands.jsonl'


def log_command(record):
    with open(commands_path, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def run(argv, cwd, purpose, check=False):
    started = time.time()
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=env)
    entry = {
        'purpose': purpose,
        'cwd': str(cwd),
        'argv': [str(a) for a in argv],
        'exit_code': proc.returncode,
        'duration_s': round(time.time() - started, 3),
        'stdout_sha256': sha256_bytes(proc.stdout.encode('utf-8')),
        'stderr_sha256': sha256_bytes(proc.stderr.encode('utf-8')),
        'stdout_tail': proc.stdout[-2000:],
        'stderr_tail': proc.stderr[-2000:],
    }
    log_command(entry)
    if check and proc.returncode != 0:
        raise SystemExit(f'command failed ({purpose}): {argv}\n{proc.stdout}\n{proc.stderr}')
    return proc


def cli(code_root, repo, *args, purpose, check=True):
    # --repo is accepted on every leaf/subcommand parser; put it last so it
    # works for both flat (verify, test-run) and nested (goal create) commands.
    return run([PYTHON, '-m', 'project_memory.cli', *args, '--repo', str(repo)],
               cwd=code_root, purpose=purpose, check=check)


def py(code_root, snippet, purpose, check=True):
    """Run a python snippet with ``code_root`` importable as the package root."""
    return run([PYTHON, '-c', snippet], cwd=code_root, purpose=purpose, check=check)


def git(repo, *args, check=True):
    return run(['git', '-C', str(repo), *args], cwd=repo, purpose='git ' + ' '.join(args),
               check=check)


def make_repo(path, remote=None, message='base'):
    path.mkdir(parents=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.email', 'pm03@review.invalid')
    git(path, 'config', 'user.name', 'PM-03 Reviewer')
    (path / 'README.md').write_text('b0 review fixture\n', encoding='utf-8')
    (path / 'tests').mkdir()
    (path / 'tests' / 'test_smoke.py').write_text(
        'def test_ok():\n    assert True\n', encoding='utf-8')
    git(path, 'add', 'README.md', 'tests/test_smoke.py')
    git(path, 'commit', '-qm', message)
    if remote:
        git(path, 'remote', 'add', 'origin', remote)
    return git(path, 'rev-parse', 'HEAD').stdout.strip()


def copy_tree(src, dst):
    shutil.copytree(src, dst)
    return dst


def receipt_assertions(code_root, repo, receipt_ref):
    snippet = r'''
import json, sys
from pathlib import Path
from project_memory.execution import verify_receipt, repo_identity
repo = Path(sys.argv[1]); ref = sys.argv[2]
checked = verify_receipt(repo, ref)
identity = repo_identity(repo)
print(json.dumps({
    'valid': checked['valid'],
    'problems': checked['problems'],
    'legacy_path_bound': checked['legacy_path_bound'],
    'identity_result': checked['identity'],
    'current_identity': identity,
    'receipt_repo_id': (checked['receipt'] or {}).get('repo_id'),
    'receipt_schema': (checked['receipt'] or {}).get('schema_version'),
    'receipt_identity_field': (checked['receipt'] or {}).get('repo_identity'),
}, ensure_ascii=False))
'''
    proc = run([PYTHON, '-c', snippet, str(repo), receipt_ref], cwd=code_root,
               purpose='verify_receipt assertions', check=True)
    return json.loads(proc.stdout)


def build_workflow(code_root, repo, tag):
    """Create goal, target run, receipt, verifier run and verification record."""
    cli(code_root, repo, 'goal', 'create', '--id', 'G-B0', '--title', 'B0 review goal',
        '--outcome', 'receipt portable across checkouts', '--owner', 'reviewer',
        '--criterion', CRITERION, purpose=f'{tag}: goal create')
    command = f'"{PYTHON}" -c "import sys; print(\'1 passed\'); sys.exit(0)"'
    out = cli(code_root, repo, 'test-run', '--command', command, '--agent', 'reviewer',
              purpose=f'{tag}: test-run')
    payload = json.loads(out.stdout)
    receipt = payload['receipt']
    receipt_ref = payload['path']
    log_rel = payload['log']
    head = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    cli(code_root, repo, 'run', 'start', '--goal', 'G-B0', '--task', '325',
        '--run-id', 'run-target', '--agent', 'dev-agent', '--model-provider', 'review',
        '--model-id', 'target-model', '--session-id', 's-target', '--base-sha', head,
        '--role', 'executor', purpose=f'{tag}: run start target')
    cli(code_root, repo, 'run', 'finish', '--task', '325', '--run-id', 'run-target',
        '--completed', 'ran', '--head-sha', head, '--test-command', command,
        '--test-exit', '0', '--test-log', log_rel,
        purpose=f'{tag}: run finish target')
    cli(code_root, repo, 'run', 'start', '--goal', 'G-B0', '--task', '325',
        '--run-id', 'run-verifier', '--agent', 'verifier-agent', '--model-provider',
        'review', '--model-id', 'verifier-model', '--session-id', 's-verifier',
        '--base-sha', head, '--role', 'verifier', purpose=f'{tag}: run start verifier')
    mapping = {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-B0', 'task_id': '325',
        'criterion_description': CRITERION, 'target_repository': str(repo),
        'target_commit_sha': head, 'evidence_id': 'EV-1', 'evidence_source': 'test',
        'evidence_command': command, 'evidence_log': log_rel,
        'evidence_exit_code': 0, 'evidence_receipt': receipt_ref,
        'execution_status': 'passed', 'coverage_claim': 'covers criterion',
        'coverage_review_status': 'confirmed', 'independent_verifier': 'verifier-agent',
        'verification_result': 'pass'}]}
    mapping_path = HERE / f'_mapping_{tag}.json'
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding='utf-8')
    verify = cli(code_root, repo, 'verify', '--target-run', 'run-target',
                 '--verifier-run', 'run-verifier', '--standard', 'acceptance',
                 '--verdict', 'pass', '--evidence-level', 'locally_observed',
                 '--test-command', command, '--test-exit', '0',
                 '--test-log', log_rel, '--test-receipt', receipt_ref,
                 '--criterion-evidence', str(mapping_path),
                 purpose=f'{tag}: verify', check=False)
    verify_payload = {}
    try:
        verify_payload = json.loads(verify.stdout or '{}')
    except json.JSONDecodeError:
        verify_payload = {}
    return {'receipt_id': receipt['receipt_id'], 'receipt_ref': receipt_ref,
            'command': command, 'head': head,
            'verify_exit': verify.returncode, 'verify_stdout': verify.stdout[-3000:],
            'verify_stderr': verify.stderr[-2000:],
            'verification_id': (verify_payload.get('verification') or {}).get('verification_id'),
            'log': log_rel}


def current_check(code_root, repo, verification_id):
    snippet = r'''
import json, sys
from pathlib import Path
from project_memory.coordination import _find_record, _load, _verification_current
repo = Path(sys.argv[1]); ref = sys.argv[2]
path = _find_record(repo, 'verifications', ref)
record = _load(path) if path else None
print(json.dumps({'found': path is not None,
                  'current': bool(record) and _verification_current(repo, record),
                  'status': (record or {}).get('status'),
                  'verdict': (record or {}).get('verdict')}, ensure_ascii=False))
'''
    proc = run([PYTHON, '-c', snippet, str(repo), verification_id], cwd=code_root,
               purpose='_verification_current check', check=True)
    return json.loads(proc.stdout)


def goal_evaluate(code_root, repo):
    proc = cli(code_root, repo, 'goal', 'evaluate', '--id', 'G-B0',
               purpose='goal evaluate', check=False)
    return {'exit_code': proc.returncode, 'stdout': proc.stdout[-4000:],
            'stderr': proc.stderr[-2000:]}


def main():
    tmp = Path(tempfile.mkdtemp(prefix='b0-review-'))
    summary = {'workdir': str(tmp), 'python': PYTHON, 'candidate_root': str(CANDIDATE)}
    # ---------------------------------------------------------------- cross path
    a = tmp / 'path-a'
    head = make_repo(a, REMOTE_A)
    flow = build_workflow(CANDIDATE, a, 'A')
    a_receipt = receipt_assertions(CANDIDATE, a, flow['receipt_ref'])
    a_identity = a_receipt['current_identity']
    verification_id = flow.get('verification_id') or 'VER-1'
    a_current = current_check(CANDIDATE, a, verification_id)
    a_eval = goal_evaluate(CANDIDATE, a)

    b = copy_tree(a, tmp / 'path-b')
    b_receipt = receipt_assertions(CANDIDATE, b, flow['receipt_ref'])
    b_current = current_check(CANDIDATE, b, verification_id)
    b_eval = goal_evaluate(CANDIDATE, b)

    cross_path = {
        'head': head,
        'receipt_id': flow['receipt_id'],
        'verification_id': verification_id,
        'workflow_verify_exit': flow['verify_exit'],
        'a': {'receipt': a_receipt, 'current': a_current, 'goal_evaluate': a_eval},
        'b': {'receipt': b_receipt, 'current': b_current, 'goal_evaluate': b_eval},
        'identity_equal': a_receipt['current_identity']['id'] == b_receipt['current_identity']['id'],
        'identity_contains_path': (str(a) in json.dumps(b_receipt['current_identity'])
                                   or str(b) in json.dumps(b_receipt['current_identity'])),
        'assertions': {
            'A_valid': a_receipt['valid'],
            'B_valid': b_receipt['valid'],
            'B_current': b_current['current'],
            'identity_equal': a_receipt['current_identity']['id'] == b_receipt['current_identity']['id'],
            'no_path_in_identity': not (str(a) in json.dumps(b_receipt['current_identity'])
                                        or str(b) in json.dumps(b_receipt['current_identity'])),
        },
    }
    (HERE / 'cross_path.json').write_text(json.dumps(cross_path, ensure_ascii=False, indent=2),
                                          encoding='utf-8')

    # ---------------------------------------------------------------- cross repo
    cases = {}
    # case 1: same root commit, different remote
    other_remote = copy_tree(a, tmp / 'other-remote')
    git(other_remote, 'remote', 'set-url', 'origin', REMOTE_B)
    cases['same_root_different_remote'] = receipt_assertions(CANDIDATE, other_remote, flow['receipt_ref'])
    # case 2: different root commit, no remote
    other_root = tmp / 'other-root'
    make_repo(other_root, None, message='unrelated base')
    target = other_root / '.project-memory' / 'receipts' / f'{flow["receipt_id"]}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(a / '.project-memory' / 'receipts' / f'{flow["receipt_id"]}.json', target)
    cases['different_root_no_remote'] = receipt_assertions(CANDIDATE, other_root, flow['receipt_ref'])
    # case 3: different root commit, same remote
    other_root_remote = tmp / 'other-root-same-remote'
    make_repo(other_root_remote, REMOTE_A, message='unrelated base, same remote')
    target = other_root_remote / '.project-memory' / 'receipts' / f'{flow["receipt_id"]}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(a / '.project-memory' / 'receipts' / f'{flow["receipt_id"]}.json', target)
    cases['different_root_same_remote'] = receipt_assertions(CANDIDATE, other_root_remote,
                                                             flow['receipt_ref'])
    # case 4: A has remote, copy drops it (root-only vs remote+root)
    no_remote = copy_tree(a, tmp / 'no-remote')
    git(no_remote, 'remote', 'remove', 'origin')
    cases['same_root_missing_remote'] = receipt_assertions(CANDIDATE, no_remote, flow['receipt_ref'])
    cross_repo = {
        'cases': cases,
        'assertions': {
            name: {'rejected': not data['valid'],
                   'mentions_repository_identity': any('仓库' in p for p in data['problems'])}
            for name, data in cases.items()
        },
    }
    (HERE / 'cross_repo.json').write_text(json.dumps(cross_repo, ensure_ascii=False, indent=2),
                                          encoding='utf-8')

    # ---------------------------------------------------------------- legacy 1.0
    legacy_root = tmp / 'legacy-a'
    legacy_head = make_repo(legacy_root, REMOTE_A, message='legacy base')
    base_out = cli(BASE, legacy_root, 'test-run', '--command',
                   f'"{PYTHON}" -c "import sys; print(\'1 passed\'); sys.exit(0)"',
                   '--agent', 'legacy-agent', purpose='legacy: base test-run (schema 1.0)')
    base_json = json.loads(base_out.stdout)
    legacy_id = base_json['receipt']['receipt_id']
    legacy_ref = base_json['path']
    legacy_original = receipt_assertions(CANDIDATE, legacy_root, legacy_ref)
    legacy_copy = copy_tree(legacy_root, tmp / 'legacy-b')
    legacy_moved = receipt_assertions(CANDIDATE, legacy_copy, legacy_ref)
    legacy = {
        'base_receipt_schema': base_json['receipt'].get('schema_version'),
        'base_receipt_repo_id': base_json['receipt'].get('repo_id'),
        'base_receipt_has_repo_identity': 'repo_identity' in base_json['receipt'],
        'original_path': legacy_original,
        'copied_path': legacy_moved,
        'assertions': {
            'original_valid': legacy_original['valid'],
            'original_legacy_flag': legacy_original['legacy_path_bound'],
            'original_kind': (legacy_original['identity_result'] or {}).get('kind'),
            'copied_rejected': not legacy_moved['valid'],
            'copied_mentions_legacy': any('legacy' in p for p in legacy_moved['problems']),
        },
    }
    (HERE / 'legacy.json').write_text(json.dumps(legacy, ensure_ascii=False, indent=2),
                                      encoding='utf-8')

    # ---------------------------------------------------------------- tamper
    tamper_repo = tmp / 'tamper'
    head_t = make_repo(tamper_repo, REMOTE_A, message='tamper base')
    t_out = cli(CANDIDATE, tamper_repo, 'test-run', '--command',
                f'"{PYTHON}" -c "print(\'ok\')"', '--agent', 'reviewer',
                purpose='tamper: test-run')
    t_payload = json.loads(t_out.stdout)
    t_receipt_id = t_payload['receipt']['receipt_id']
    t_ref = t_payload['path']
    receipt_file = tamper_repo / '.project-memory' / 'receipts' / f'{t_receipt_id}.json'
    payload = json.loads(receipt_file.read_text(encoding='utf-8'))
    payload['repo_identity'] = dict(payload['repo_identity'], remote='evil.example/x')
    body = {k: v for k, v in payload.items() if k != 'content_sha256'}
    payload['content_sha256'] = sha256_bytes(
        json.dumps(body, sort_keys=True, ensure_ascii=False,
                   separators=(',', ':')).encode('utf-8'))
    receipt_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tampered = receipt_assertions(CANDIDATE, tamper_repo, t_ref)
    tamper = {
        'result': tampered,
        'assertions': {
            'rejected': not tampered['valid'],
            'mentions_identity_field': any('repo_identity.remote' in p
                                           for p in tampered['problems']),
        },
    }
    (HERE / 'tamper.json').write_text(json.dumps(tamper, ensure_ascii=False, indent=2),
                                      encoding='utf-8')

    summary.update({'cross_path_assertions': cross_path['assertions'],
                    'cross_repo_assertions': cross_repo['assertions'],
                    'legacy_assertions': legacy['assertions'],
                    'tamper_assertions': tamper['assertions']})
    (HERE / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                       encoding='utf-8')
    print(json.dumps(summary['cross_path_assertions']))
    print(json.dumps(summary['cross_repo_assertions']))
    print(json.dumps(summary['legacy_assertions']))
    print(json.dumps(summary['tamper_assertions']))
    print('WORKDIR=' + str(tmp))


if __name__ == '__main__':
    main()
