"""B0.1 remediation probe: observed behaviour of F-2, F-3 and AC-1(b).

Builds throwaway repositories under a temp directory, drives the public
coordination API, and writes one JSON document with what was observed.  It does
not assert a verdict and never touches a production key or trust anchor.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REMOTE_A = 'https://github.com/pilot-org/repo-a'
REMOTE_OTHER = 'https://github.com/pilot-org/repo-other'
CRITERION = '模块通过测试'
TASK = '325'


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(repo), *args], check=True,
                            capture_output=True, text=True, encoding='utf-8')
    return result.stdout.strip()


def build_repo(path: Path, remote: str | None, marker: str) -> str:
    path.mkdir(parents=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.email', 'b0@example.invalid')
    git(path, 'config', 'user.name', 'B0')
    (path / 'README.md').write_text(f'{marker}\n', encoding='utf-8')
    (path / 'tests').mkdir()
    (path / 'tests' / 'test_smoke.py').write_text(
        'def test_ok():\n    assert True\n', encoding='utf-8')
    git(path, 'add', 'README.md', 'tests/test_smoke.py')
    git(path, 'commit', '-qm', 'base')
    if remote:
        git(path, 'remote', 'add', 'origin', remote)
    return git(path, 'rev-parse', 'HEAD')


def prepare(repo: Path, base: str) -> dict:
    from project_memory.coordination import (create_goal, finish_run, start_run,
                                             verify_run)
    from project_memory.execution import run_command

    create_goal(repo, 'G-1', 'G-1 title', 'background', 'outcome', 'owner',
                [CRITERION])
    out = run_command(repo, [sys.executable, '-c',
                             "import sys; print('1 passed'); sys.exit(0)"],
                      base, executed_by='dev-agent')
    start_run(repo, 'G-1', TASK, 'run-target', 'dev-agent', 'qodercn',
              'executor-model', base_sha=base, role='executor')
    finish_run(repo, TASK, 'run-target', ['implemented'], ['verify'],
               head_sha=base,
               tests=[{'command': out['receipt']['command'], 'exit_code': 0,
                       'log': out['log']}])
    start_run(repo, 'G-1', TASK, 'run-verifier', 'verifier-agent', 'qodercn',
              'verifier-model', base_sha=base, role='verifier')
    return {'receipt': out, 'verify_run': verify_run}


def mapping_for(out: dict, base: str, repository: str) -> dict:
    return {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-1', 'task_id': TASK,
        'criterion_description': CRITERION,
        'target_repository': repository, 'target_commit_sha': base,
        'evidence_id': 'EV-1', 'evidence_source': 'test',
        'evidence_command': out['receipt']['command'],
        'evidence_log': out['log'], 'evidence_exit_code': 0,
        'evidence_receipt': out['path'],
        'execution_status': 'passed', 'coverage_claim': '覆盖对应标准',
        'coverage_review_status': 'confirmed',
        'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}


def verify_at(repo: Path, prepared: dict, base: str, repository: str) -> dict:
    verify_run = prepared['verify_run']
    return verify_run(repo, 'run-target', 'run-verifier', 'acceptance', 'pass',
                      'locally_observed',
                      test_receipt=prepared['receipt']['path'],
                      criterion_evidence=mapping_for(prepared['receipt'], base,
                                                     repository))


def outcome(call) -> dict:
    from project_memory.common import PMError
    try:
        result = call()
    except PMError as exc:
        return {'ok': False, 'error': str(exc)}
    return {'ok': True, 'status': result.get('status'),
            'mapping_status': (result.get('mapping') or {}).get('status'),
            'verification_id': (result.get('verification') or {}).get('verification_id')}


def signed_record_probe(work: Path, repo_a: Path, repo_b: Path, base: str) -> dict:
    from project_memory import authority

    openssl = shutil.which('openssl')
    if not openssl:
        return {'ran': False, 'reason': 'openssl 不在 PATH'}
    signing = work / 'signing'
    signing.mkdir()
    key = signing / 'test-key.pem'
    pub = signing / 'test-key.pub.pem'
    subprocess.run([openssl, 'genpkey', '-algorithm', 'RSA',
                    '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(key)],
                   check=True, capture_output=True)
    subprocess.run([openssl, 'pkey', '-in', str(key), '-pubout',
                    '-out', str(pub)], check=True, capture_output=True)
    record = {
        'schema_version': '1.1', 'kind': 'verification_record',
        'verification_id': 'VER-signed-fixture', 'task': TASK, 'goal_id': 'G-1',
        'target_head_sha': base, 'verdict': 'pass', 'status': 'VERIFIED',
        'mapping_status': 'complete',
        'criterion_evidence': [{'criterion_id': 'C1', 'goal_id': 'G-1',
                                'target_commit_sha': base,
                                'evidence_matched': True}],
    }
    payload_file = signing / 'payload.bin'
    payload_file.write_bytes(authority.verification_payload(record))
    signature_file = signing / 'signature.bin'
    subprocess.run([openssl, 'dgst', '-sha256', '-sign', str(key),
                    '-out', str(signature_file), str(payload_file)],
                   check=True, capture_output=True)
    record['authority'] = {
        'status': 'trusted', 'anchor_id': 'test-anchor',
        'issuer': 'test-signer', 'algorithm': 'rsa-sha256',
        'signed_payload_sha256': authority.verification_digest(record),
        'signature_b64': base64.b64encode(signature_file.read_bytes()).decode('ascii'),
    }
    relative = Path('.project-memory/verifications/325/VER-signed-fixture.json')
    for repo in (repo_a, repo_b):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                          encoding='utf-8')
    anchor = {'algorithm': 'rsa-sha256',
              'public_key_pem': pub.read_text(encoding='utf-8')}
    checks = {}
    for label, repo in (('A', repo_a), ('B', repo_b)):
        loaded = json.loads((repo / relative).read_text(encoding='utf-8'))
        payload = authority.verification_payload(loaded)
        ok, detail = authority._verify_signature(
            anchor, payload, loaded['authority']['signature_b64'], 'rsa-sha256')
        checks[label] = {'signature_valid': ok, 'detail': detail,
                         'payload_sha256': authority.verification_digest(loaded)}
    return {'ran': True, 'kind': 'test key, not a trust anchor',
            'checks': checks,
            'payload_identical': (checks['A']['payload_sha256']
                                  == checks['B']['payload_sha256'])}


def anchor_protection_probe(work: Path, repo: Path) -> dict:
    from project_memory import authority

    anchor_path = work / 'test-anchor.json'
    anchor_path.write_text(json.dumps({
        'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
        'anchor_id': 'test-anchor', 'issuer': 'test-signer',
        'algorithm': 'rsa-sha256', 'public_key_pem': 'unused-in-this-check',
    }), encoding='utf-8')
    os.chmod(anchor_path, 0o444)
    writable = os.access(anchor_path, os.W_OK)
    previous = os.environ.get(authority.ANCHOR_ENV)
    os.environ[authority.ANCHOR_ENV] = str(anchor_path)
    try:
        anchor, reason = authority.load_anchor(repo)
    finally:
        if previous is None:
            os.environ.pop(authority.ANCHOR_ENV, None)
        else:
            os.environ[authority.ANCHOR_ENV] = previous
        os.chmod(anchor_path, 0o644)
    return {'anchor_accepted': anchor is not None, 'reason': reason,
            'writable_while_0444': writable}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.code_root).resolve()))
    work = Path(args.work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    from project_memory import execution

    base = build_repo(work / 'path-a', REMOTE_A, 'path a content')
    repo_a = work / 'path-a'
    prepared = prepare(repo_a, base)
    copy_b = work / 'path-b'
    shutil.copytree(repo_a, copy_b)
    identity = execution.repo_identity(repo_a)
    report = {
        'run': 'B0.1 remediation probe',
        'base_sha': base,
        'identity': identity,
        'identity_A_equals_B': execution.repo_id(repo_a) == execution.repo_id(copy_b),
        'identity_contains_path': str(work) in json.dumps(identity),
        'scenarios': {},
    }

    report['scenarios']['F2_cross_path_absolute_mapping'] = outcome(
        lambda: verify_at(copy_b, prepared, base, str(repo_a)))

    copy_b2 = work / 'path-b2'
    shutil.copytree(repo_a, copy_b2)
    report['scenarios']['F2_cross_path_identity_id'] = outcome(
        lambda: verify_at(copy_b2, prepared, base, identity['id']))

    copy_b3 = work / 'path-b3'
    shutil.copytree(repo_a, copy_b3)
    report['scenarios']['F2_cross_path_canonical_remote'] = outcome(
        lambda: verify_at(copy_b3, prepared, base, identity['remote']))

    other = work / 'other-repo'
    other_base = build_repo(other, REMOTE_OTHER, 'other content')
    report['scenarios']['F2_cross_repo_absolute_path'] = {
        **outcome(lambda: verify_at(repo_a, prepared, base, str(other))),
        'other_identity_id': execution.repo_id(other),
        'other_base_sha': other_base,
    }
    report['scenarios']['F2_bare_directory_name'] = outcome(
        lambda: verify_at(repo_a, prepared, base, 'path-a'))

    same_name = work / 'elsewhere' / 'path-a'
    build_repo(same_name, None, 'same name, different history')
    report['scenarios']['F2_same_name_other_repo'] = {
        **outcome(lambda: verify_at(repo_a, prepared, base, str(same_name))),
        'identity_id': execution.repo_id(same_name),
    }

    # Legacy 1.0 receipt: valid at the original path, rejected across paths.
    legacy_a = work / 'legacy-a'
    shutil.copytree(repo_a, legacy_a)
    receipt_path = legacy_a / prepared['receipt']['path']
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    receipt['schema_version'] = '1.0'
    receipt.pop('repo_identity', None)
    receipt['repo_id'] = execution._legacy_repo_id(legacy_a)
    receipt['content_sha256'] = execution._canonical_receipt_digest(receipt)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2),
                            encoding='utf-8')
    legacy_b = work / 'legacy-b'
    shutil.copytree(legacy_a, legacy_b)
    from project_memory.execution import verify_receipt
    original = verify_receipt(legacy_a, prepared['receipt']['path'])
    moved = verify_receipt(legacy_b, prepared['receipt']['path'])
    report['scenarios']['legacy_receipt'] = {
        'original_path_valid': original['valid'],
        'original_path_legacy': original['legacy_path_bound'],
        'original_portable': original['identity']['portable'],
        'copied_path_valid': moved['valid'],
        'copied_path_problems': moved['problems'],
    }

    canonical = execution._canonical_remote
    report['scenarios']['F3_remote_normalisation'] = {
        'ssh_default_port': canonical('ssh://git@github.com:22/pilot-org/repo-a.git'),
        'scp_form': canonical('git@github.com:pilot-org/repo-a.git'),
        'https_form': canonical(REMOTE_A),
        'ssh_non_default_port': canonical('ssh://git@github.com:2222/pilot-org/repo-a.git'),
    }

    report['scenarios']['AC1b_signed_record'] = signed_record_probe(
        work, repo_a, copy_b, base)
    report['scenarios']['AC1b_anchor_protection'] = anchor_protection_probe(
        work, repo_a)

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                              encoding='utf-8', newline='\n')
    print(json.dumps({k: report['scenarios'][k] for k in report['scenarios']},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
