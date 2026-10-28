"""PM-03 independent driver for B0.1 (F-2, F-3, prior ACs).

Runs against the candidate package via --candidate; every repository used here
is created in a fresh temporary directory by this script.  It never writes to
the review checkout, the candidate worktree or the signed fixture.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

CRITERION = '模块通过测试'
REMOTE_A = 'https://github.com/pilot-org/repo-a'
REMOTE_B = 'https://github.com/pilot-org/repo-b'


def git(repo, *args, check=True):
    proc = subprocess.run(['git', '-C', str(repo), *args],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace')
    if check and proc.returncode != 0:
        raise RuntimeError(f'git {args} failed ({proc.returncode}): '
                           f'{proc.stdout}\n{proc.stderr}')
    return proc


def setup_repo(path, remote=None):
    path.mkdir(parents=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.email', 'b01@example.invalid')
    git(path, 'config', 'user.name', 'B01')
    (path / 'README.md').write_text('b01\n', encoding='utf-8')
    (path / 'tests').mkdir()
    (path / 'tests/test_smoke.py').write_text(
        'def test_ok():\n    assert True\n', encoding='utf-8')
    git(path, 'add', 'README.md', 'tests/test_smoke.py')
    git(path, 'commit', '-qm', 'base')
    if remote:
        git(path, 'remote', 'add', 'origin', remote)
    return git(path, 'rev-parse', 'HEAD').stdout.strip()


def case(name, expected, fn):
    try:
        actual = fn()
        error = None
    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
        actual = None
        error = f'{type(exc).__name__}: {exc}'
    return {'case': name, 'expected': expected, 'actual': actual,
            'error': error, 'ok': error is None and actual == expected}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()

    candidate = Path(args.candidate).resolve()
    sys.path.insert(0, str(candidate))
    from project_memory import execution
    from project_memory.coordination import (create_goal, finish_run,
                                             start_run, verify_run,
                                             _repo_binding, _repo_matches,
                                             _verification_current)
    from project_memory.execution import run_command, verify_receipt

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    root = Path(tempfile.mkdtemp(prefix='pm03-b01-'))
    ctx = {'candidate': str(candidate), 'started_at': started,
           'python': sys.version, 'temp_root': str(root),
           'repo_binding': f'{_repo_binding.__module__}.{_repo_binding.__name__}'}

    # ---------------------------------------------------------------- repos
    repo_a = root / 'path-a'
    base = setup_repo(repo_a, REMOTE_A)
    create_goal(repo_a, 'G-1', 'G-1 title', 'background', 'outcome',
                'owner', [CRITERION])
    receipt_out = run_command(
        repo_a, [sys.executable, '-c',
                 "import sys; print('1 passed'); sys.exit(0)"],
        base, executed_by='dev-agent')
    start_run(repo_a, 'G-1', '325', 'run-target', 'dev-agent', 'qodercn',
              'executor-model', base_sha=base, role='executor')
    finish_run(repo_a, '325', 'run-target', ['implemented'], ['verify'],
               head_sha=base,
               tests=[{'command': receipt_out['receipt']['command'],
                       'exit_code': 0, 'log': receipt_out['log']}])

    repo_b = root / 'path-b'
    shutil.copytree(repo_a, repo_b)
    repo_c = root / 'path-c'
    shutil.copytree(repo_a, repo_c)
    git(repo_c, 'remote', 'set-url', 'origin', REMOTE_B)
    repo_d = root / 'other-root'
    setup_repo(repo_d, REMOTE_A)  # same remote, different root commit
    repo_e = root / 'elsewhere' / 'path-b'  # same basename as repo_b
    setup_repo(repo_e, REMOTE_B)

    identity_a = execution.repo_identity(repo_a)
    identity_b = execution.repo_identity(repo_b)
    identity_c = execution.repo_identity(repo_c)
    identity_d = execution.repo_identity(repo_d)
    identity_e = execution.repo_identity(repo_e)
    ctx.update({
        'identity_a': identity_a, 'identity_b': identity_b,
        'identity_c': identity_c, 'identity_d': identity_d,
        'identity_e': identity_e,
        'base': base,
    })

    # ------------------------------------------- F-2: end-to-end in copy B
    start_run(repo_b, 'G-1', '325', 'run-verifier', 'verifier-agent',
              'qodercn', 'verifier-model', base_sha=base, role='verifier')
    mapping = {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-1', 'task_id': '325',
        'criterion_description': CRITERION,
        'target_repository': str(repo_a),  # original checkout, not B
        'target_commit_sha': base,
        'evidence_id': 'EV-1', 'evidence_source': 'test',
        'evidence_command': receipt_out['receipt']['command'],
        'evidence_log': receipt_out['log'],
        'evidence_exit_code': 0,
        'evidence_receipt': receipt_out['path'],
        'execution_status': 'passed', 'coverage_claim': '覆盖对应标准',
        'coverage_review_status': 'confirmed',
        'independent_verifier': 'verifier-agent',
        'verification_result': 'pass'}]}
    f2_cross = {'temp_root': str(root), 'mapping_used': str(repo_a),
                'cases': []}
    try:
        result = verify_run(repo_b, 'run-target', 'run-verifier', 'acceptance',
                            'pass', 'locally_observed',
                            test_receipt=receipt_out['path'],
                            criterion_evidence=mapping)
        verification = result['verification']
        f2_cross['verify_run_ok'] = True
        f2_cross['verification_id'] = verification.get('verification_id')
        f2_cross['record_target_repository'] = (
            verification.get('criterion_evidence') or [{}])[0].get(
                'target_repository')
        f2_cross['verification_current_in_b'] = _verification_current(
            repo_b, verification)
        receipt_check = verify_receipt(repo_b, receipt_out['path'])
        f2_cross['receipt_in_b'] = {
            'valid': receipt_check['valid'],
            'problems': receipt_check['problems'],
            'portable': receipt_check.get('identity', {}).get('portable'),
            'legacy_path_bound': receipt_check.get('legacy_path_bound'),
        }
        f2_cross['receipt_in_a'] = {
            'valid': verify_receipt(repo_a, receipt_out['path'])['valid'],
        }
    except Exception as exc:  # noqa: BLE001
        f2_cross['verify_run_ok'] = False
        f2_cross['error'] = f'{type(exc).__name__}: {exc}'
        f2_cross['traceback'] = traceback.format_exc()

    # ------------------------------------------------ F-2: binding matrix
    accept = [
        ('identity id', identity_b['id'], 'identity',
         lambda: _repo_binding(repo_b, identity_b['id'])),
        ('canonical remote', identity_b['remote'], 'identity',
         lambda: _repo_binding(repo_b, identity_b['remote'])),
        ('current absolute path', str(repo_b), 'path',
         lambda: _repo_binding(repo_b, str(repo_b))),
        ('other checkout same identity', str(repo_a), 'identity',
         lambda: _repo_binding(repo_b, str(repo_a))),
        ('uppercase identity id', identity_b['id'].upper(), 'identity',
         lambda: _repo_binding(repo_b, identity_b['id'].upper())),
        ('_repo_matches other checkout', str(repo_a), True,
         lambda: _repo_matches(repo_b, str(repo_a))),
    ]
    reject = [
        ('different remote (copy C)', str(repo_c), None,
         lambda: _repo_binding(repo_b, str(repo_c))),
        ('different root, same remote (D)', str(repo_d), None,
         lambda: _repo_binding(repo_b, str(repo_d))),
        ('same directory name, other repo (E)', str(repo_e), None,
         lambda: _repo_binding(repo_b, str(repo_e))),
        ('bare directory name', repo_b.name, None,
         lambda: _repo_binding(repo_b, repo_b.name)),
        ('subdirectory of current repo', str(repo_b / 'tests'), None,
         lambda: _repo_binding(repo_b, str(repo_b / 'tests'))),
        ('nonexistent absolute path', str(repo_b / 'missing'), None,
         lambda: _repo_binding(repo_b, str(repo_b / 'missing'))),
        ('file inside current repo', str(repo_b / 'README.md'), None,
         lambda: _repo_binding(repo_b, str(repo_b / 'README.md'))),
        ('relative path', '..' + '/' + repo_b.name, None,
         lambda: _repo_binding(repo_b, '..' + '/' + repo_b.name)),
        ('identity id of different repo (C)', identity_c['id'], None,
         lambda: _repo_binding(repo_b, identity_c['id'])),
        ('_repo_matches bare name', repo_b.name, False,
         lambda: _repo_matches(repo_b, repo_b.name)),
    ]
    f2_matrix = {'temp_root': str(root), 'accept': [], 'reject': []}
    for name, value, expected, fn in accept:
        item = case(name, expected, fn)
        item['declared'] = value
        f2_matrix['accept'].append(item)
    for name, value, expected, fn in reject:
        item = case(name, expected, fn)
        item['declared'] = value
        f2_matrix['reject'].append(item)

    # ------------------------------- F-2 negative end-to-end mapping in B
    start_run(repo_b, 'G-1', '325', 'run-verifier-neg', 'verifier-agent',
              'qodercn', 'verifier-model', base_sha=base, role='verifier')
    bad_mapping = json.loads(json.dumps(mapping))
    bad_mapping['criteria'][0]['target_repository'] = str(repo_c)
    neg_e2e = {'expected': 'PMError containing 不是当前仓库'}
    try:
        verify_run(repo_b, 'run-target', 'run-verifier-neg', 'acceptance',
                   'pass', 'locally_observed',
                   test_receipt=receipt_out['path'],
                   criterion_evidence=bad_mapping)
        neg_e2e['raised'] = False
        neg_e2e['message'] = ''
    except Exception as exc:  # noqa: BLE001
        neg_e2e['raised'] = True
        neg_e2e['type'] = type(exc).__name__
        neg_e2e['message'] = str(exc)
    neg_e2e['ok'] = (neg_e2e['raised'] and neg_e2e.get('type') == 'PMError'
                     and '不是当前仓库' in neg_e2e['message'])

    f2_negative = {
        'temp_root': str(root),
        'binding_reject_cases': f2_matrix['reject'],
        'end_to_end_different_repository': neg_e2e,
    }

    # ------------------------------------------------------ F-3: identity
    repo_r = root / 'identity-repo'
    setup_repo(repo_r, REMOTE_A)
    variants = [
        ('https', REMOTE_A),
        ('https trailing .git/', REMOTE_A + '.git/'),
        ('ssh default port 22', 'ssh://git@github.com:22/pilot-org/repo-a'),
        ('scp form', 'git@github.com:pilot-org/repo-a'),
        ('ssh 22 with .git', 'ssh://git@github.com:22/pilot-org/repo-a.git'),
        ('ssh other user', 'ssh://other@github.com:22/pilot-org/repo-a'),
        ('https with user', 'https://user@github.com/pilot-org/repo-a'),
        ('https with :22 (observation)', 'https://github.com:22/pilot-org/repo-a'),
        ('ipv6 no port', 'ssh://git@[2001:db8::1]/team/repo'),
        ('ipv6 :22', 'ssh://git@[2001:db8::1]:22/team/repo'),
        ('ipv6 :2222', 'ssh://git@[2001:db8::1]:2222/team/repo'),
        ('non-default port 2222', 'ssh://git@github.com:2222/pilot-org/repo-a'),
    ]
    f3 = {'temp_root': str(root), 'cases': [], 'identities': {}}
    for label, url in variants:
        git(repo_r, 'remote', 'set-url', 'origin', url)
        f3['identities'][label] = execution.repo_identity(repo_r)
    baseline_id = f3['identities']['https']['id']
    ipv6_id = f3['identities']['ipv6 no port']['id']
    expected = {
        'https': baseline_id,
        'https trailing .git/': baseline_id,
        'ssh default port 22': baseline_id,
        'scp form': baseline_id,
        'ssh 22 with .git': baseline_id,
        'ssh other user': baseline_id,
        'https with user': baseline_id,
        'https with :22 (observation)': baseline_id,
        'ipv6 no port': ipv6_id,
        'ipv6 :22': ipv6_id,
        'ipv6 :2222': 'DIFFERENT_FROM_IPV6',
        'non-default port 2222': 'DIFFERENT_FROM_BASELINE',
    }
    for label, url in variants:
        identity = f3['identities'][label]
        want = expected[label]
        if want == 'DIFFERENT_FROM_IPV6':
            ok = identity['id'] != ipv6_id
        elif want == 'DIFFERENT_FROM_BASELINE':
            ok = identity['id'] != baseline_id
        else:
            ok = identity['id'] == want
        f3['cases'].append({
            'case': label, 'remote': url,
            'canonical_remote': identity['remote'],
            'kind': identity['kind'], 'id': identity['id'],
            'same_as_baseline': identity['id'] == baseline_id,
            'expected': ('same_id' if want not in
                         ('DIFFERENT_FROM_IPV6', 'DIFFERENT_FROM_BASELINE')
                         else want),
            'ok': ok,
        })
    f3['distinct'] = {
        'ssh_22_vs_https_same': f3['identities']['ssh default port 22']['id'] == baseline_id,
        'scp_vs_https_same': f3['identities']['scp form']['id'] == baseline_id,
        'port_2222_differs': f3['identities']['non-default port 2222']['id'] != baseline_id,
        'ipv6_22_vs_no_port_same': f3['identities']['ipv6 :22']['id'] == ipv6_id,
        'ipv6_2222_differs': f3['identities']['ipv6 :2222']['id'] != ipv6_id,
        'path_not_in_identity': str(repo_r) not in json.dumps(f3['identities']),
    }
    f3['ok'] = all(c['ok'] for c in f3['cases']) and all(f3['distinct'].values())

    # ---------------------------------------------------- prior AC checks
    prior = {'temp_root': str(root), 'cases': []}
    receipt_in_b = verify_receipt(repo_b, receipt_out['path'])
    prior['cases'].append({
        'case': 'AC-1 cross-path receipt in copy B',
        'ok': receipt_in_b['valid'] and receipt_in_b['identity']['portable'],
        'detail': {'valid': receipt_in_b['valid'],
                   'portable': receipt_in_b['identity']['portable'],
                   'problems': receipt_in_b['problems']}})
    receipt_in_c = verify_receipt(repo_c, receipt_out['path'])
    prior['cases'].append({
        'case': 'AC-2 different remote rejects receipt',
        'ok': (not receipt_in_c['valid']) and any(
            '仓库' in p for p in receipt_in_c['problems']),
        'detail': {'valid': receipt_in_c['valid'],
                   'problems': receipt_in_c['problems']}})

    # tamper repo_identity.remote on a fresh copy (before the legacy downgrade)
    repo_b3 = root / 'path-b-tamper'
    shutil.copytree(repo_a, repo_b3)
    tamper_path = repo_b3 / receipt_out['path']
    tampered = json.loads(tamper_path.read_text(encoding='utf-8'))
    tampered['repo_identity']['remote'] = 'github.com/pilot-org/repo-b'
    tampered['content_sha256'] = execution._canonical_receipt_digest(tampered)
    tamper_path.write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2), encoding='utf-8')
    tamper = verify_receipt(repo_b3, receipt_out['path'])
    prior['cases'].append({
        'case': 'identity field tamper rejected',
        'ok': (not tamper['valid']) and any(
            'repo_identity.remote' in p for p in tamper['problems']),
        'detail': {'valid': tamper['valid'], 'problems': tamper['problems']}})

    # legacy 1.0 downgrade on repo A, then copy to B2
    legacy_path = repo_a / receipt_out['path']
    legacy_receipt = json.loads(legacy_path.read_text(encoding='utf-8'))
    legacy_receipt['schema_version'] = '1.0'
    legacy_receipt.pop('repo_identity', None)
    legacy_receipt['repo_id'] = execution._legacy_repo_id(repo_a)
    legacy_receipt['content_sha256'] = execution._canonical_receipt_digest(
        legacy_receipt)
    legacy_path.write_text(
        json.dumps(legacy_receipt, ensure_ascii=False, indent=2),
        encoding='utf-8')
    repo_b2 = root / 'path-b-legacy'
    shutil.copytree(repo_a, repo_b2)
    legacy_at_a = verify_receipt(repo_a, receipt_out['path'])
    legacy_at_b2 = verify_receipt(repo_b2, receipt_out['path'])
    prior['cases'].append({
        'case': 'AC-4 legacy 1.0 valid at original path, flagged',
        'ok': (legacy_at_a['valid'] and legacy_at_a['legacy_path_bound']
               and legacy_at_a['identity']['kind'] == 'legacy_path_bound'),
        'detail': {'valid': legacy_at_a['valid'],
                   'legacy_path_bound': legacy_at_a['legacy_path_bound'],
                   'kind': legacy_at_a['identity']['kind'],
                   'problems': legacy_at_a['problems']}})
    prior['cases'].append({
        'case': 'AC-4 legacy 1.0 rejected after copy',
        'ok': (not legacy_at_b2['valid']) and any(
            'legacy' in p for p in legacy_at_b2['problems']),
        'detail': {'valid': legacy_at_b2['valid'],
                   'problems': legacy_at_b2['problems']}})

    # ------------------------------------------ prev-candidate control data
    prior['prev_control'] = {
        'note': 'See match_control.py invoked with --package .pilot/prev.',
        'repo_b': str(repo_b), 'repo_a': str(repo_a),
        'bare_name': repo_b.name,
    }

    outputs = {
        'f2_cross_path.json': {'context': ctx, 'result': f2_cross},
        'f2_binding_matrix.json': f2_matrix,
        'f2_negative.json': f2_negative,
        'f3_identity.json': f3,
        'prior_acs.json': prior,
    }
    summary = {'ok': True, 'files': {}}
    for name, payload in outputs.items():
        path = out_dir / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        summary['files'][name] = str(path)
    checks = (([f2_cross.get('verify_run_ok'),
                f2_cross.get('verification_current_in_b'),
                f2_cross.get('receipt_in_b', {}).get('valid')]
               + [c['ok'] for c in f2_matrix['accept']]
               + [c['ok'] for c in f2_matrix['reject']]
               + [neg_e2e['ok'], f3['ok']]
               + [c['ok'] for c in prior['cases']]))
    summary['ok'] = all(bool(x) for x in checks)
    summary['checks_total'] = len(checks)
    summary['checks_failed'] = [
        i for i, value in enumerate(checks) if not value]
    (out_dir / 'summary.json').write_text(
        json.dumps({'context': ctx, 'summary': summary}, ensure_ascii=False,
                   indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
