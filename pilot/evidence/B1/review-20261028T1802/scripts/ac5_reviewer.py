"""PM-03 AC-5: a fake verifier that prints `Verified OK` and exits 0 must not be
trusted.  Runs the full CLI (`goal evidence`) with a forged signature, once with
the fake on PATH and once via PROJECT_MEMORY_OPENSSL.  Written independently for
the B1 review.

Usage (as root): python3 ac5_reviewer.py <CODE> <WORK> <OUT.json>
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CODE = Path(sys.argv[1]).resolve()
WORK = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
AGENT_UID, AGENT_GID = 1000, 1000
ANCHOR = Path('/etc/pm-rc3-review/anchor-a.json')
DATA = json.loads(ANCHOR.read_text(encoding='utf-8'))
PATH_BASE = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
FAKEBIN = WORK / 'fakebin-print'
FAKE = FAKEBIN / 'openssl'
FAKE_BODY = '#!/bin/sh\necho "Verified OK"\nexit 0\n'
steps: list[dict] = []


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def env_for(mode: str) -> dict:
    env = {'PATH': PATH_BASE, 'HOME': str(WORK / 'home'), 'PYTHONPATH': str(CODE),
           'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM': '1', 'PROJECT_MEMORY_TRUST_ANCHOR': str(ANCHOR)}
    if mode == 'path':
        env['PATH'] = f'{FAKEBIN}:{PATH_BASE}'
    elif mode == 'env':
        env['PROJECT_MEMORY_OPENSSL'] = str(FAKE)
    return env


def cli(label, *args, repo, mode):
    proc = subprocess.run([sys.executable, '-m', 'project_memory', *args],
                          cwd=str(repo), capture_output=True, text=True, encoding='utf-8',
                          env=env_for(mode), user=AGENT_UID, group=AGENT_GID, extra_groups=[])
    steps.append({'label': label, 'mode': mode, 'exit_code': proc.returncode,
                  'stdout': proc.stdout[-2000:], 'stderr': proc.stderr[-1000:]})
    return proc


def sh(*args, repo):
    proc = subprocess.run(args, cwd=str(repo), capture_output=True, text=True,
                          encoding='utf-8', env=env_for('clean'), user=AGENT_UID,
                          group=AGENT_GID, extra_groups=[])
    if proc.returncode != 0:
        raise RuntimeError(f'{args}: {proc.returncode}\n{proc.stdout}\n{proc.stderr}')
    return proc.stdout.strip()


def build_case() -> tuple[Path, dict]:
    case = Path(tempfile.mkdtemp(prefix='pm03-ac5-', dir=str(WORK)))
    repo = case / 'repo'
    repo.mkdir()
    os.chown(case, AGENT_UID, AGENT_GID)
    os.chown(repo, AGENT_UID, AGENT_GID)
    (WORK / 'home').mkdir(parents=True, exist_ok=True)
    sh('git', 'init', '-q', repo=repo)
    sh('git', 'config', 'user.email', 'ac5@example.invalid', repo=repo)
    sh('git', 'config', 'user.name', 'AC5', repo=repo)
    (repo / 'README.md').write_text('hello\n', encoding='utf-8')
    (repo / 'tests').mkdir()
    (repo / 'tests/check.py').write_text('print("check-ok")\n', encoding='utf-8')
    for p in (repo / 'README.md', repo / 'tests', repo / 'tests/check.py'):
        os.chown(p, AGENT_UID, AGENT_GID)
    sh('git', 'add', 'README.md', 'tests/check.py', repo=repo)
    sh('git', 'commit', '-qm', 'base', repo=repo)
    base = sh('git', 'rev-parse', 'HEAD', repo=repo)
    cli('goal_create', 'goal', 'create', '--repo', '.', '--id', 'G-AC5', '--title', 'x',
        '--outcome', 'ship', '--owner', 'owner', '--criterion', 'c', repo=repo, mode='clean')
    cli('run_start', 'run', 'start', '--repo', '.', '--goal', 'G-AC5', '--task', '325',
        '--run-id', 'run-target', '--agent', 'dev', '--model-provider', 'qodercn',
        '--model-id', 'auto', '--base-sha', base, repo=repo, mode='clean')
    cli('run_finish', 'run', 'finish', '--repo', '.', '--task', '325', '--run-id', 'run-target',
        '--completed', 'x', '--remaining', 'y', '--head-sha', base, repo=repo, mode='clean')
    cli('ver_start', 'run', 'start', '--repo', '.', '--goal', 'G-AC5', '--task', '325',
        '--run-id', 'run-verifier', '--agent', 'verifier', '--model-provider', 'qodercn',
        '--model-id', 'verifier-model', '--base-sha', base, '--role', 'verifier',
        repo=repo, mode='clean')
    cli('ver_finish', 'run', 'finish', '--repo', '.', '--task', '325', '--run-id', 'run-verifier',
        '--completed', 'x', '--remaining', 'y', '--head-sha', base, repo=repo, mode='clean')
    test_proc = cli('test_run', 'test-run', '--repo', '.', '--commit', base,
                    '--command', 'python3 tests/check.py', '--agent', 'verifier',
                    repo=repo, mode='clean')
    receipt = json.loads(test_proc.stdout)
    mapping = {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-AC5', 'task_id': '325',
        'criterion_description': 'c', 'target_repository': str(repo),
        'target_commit_sha': base, 'evidence_id': 'EV-1', 'evidence_source': 'test',
        'evidence_command': receipt['receipt']['command'],
        'evidence_log': receipt['log'], 'evidence_exit_code': receipt['receipt']['exit_code'],
        'evidence_receipt': receipt['path'], 'execution_status': 'passed',
        'coverage_claim': 'c', 'coverage_review_status': 'human_confirmed',
        'independent_verifier': 'verifier', 'verification_result': 'pass'}]}
    mapping_path = case / 'mapping.json'
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding='utf-8')
    os.chown(mapping_path, AGENT_UID, AGENT_GID)
    ver = cli('verify', 'verify', '--repo', '.', '--target-run', 'run-target',
              '--verifier-run', 'run-verifier', '--standard', 'c', '--verdict', 'pass',
              '--evidence-level', 'locally_observed', '--test-receipt', receipt['path'],
              '--criterion-evidence', str(mapping_path), repo=repo, mode='clean')
    if ver.returncode != 2:
        raise RuntimeError(f'verify failed: {ver.returncode} {ver.stderr[-500:]}')
    record = json.loads((repo / json.loads(ver.stdout)['path']).read_text(encoding='utf-8'))
    return repo, record


def write_forged(repo: Path, record: dict) -> None:
    rec = json.loads(json.dumps(record))
    rec['verification_id'] = 'VER-ac5'
    rec['verified'] = True
    rec['status'] = 'VERIFIED'
    rec['mapping_status'] = 'complete'
    for entry in rec.get('criterion_evidence') or []:
        entry['evidence_matched'] = True
    rec.pop('authority', None)
    body = canonical({k: v for k, v in rec.items() if k != 'authority'})
    rec['authority'] = {'status': 'trusted', 'issuer': DATA['issuer'],
                        'anchor_id': DATA['anchor_id'], 'algorithm': DATA.get('algorithm'),
                        'signed_payload_sha256': sha_hex(body),
                        'signature_b64': base64.b64encode(b'pm03-forged').decode('ascii')}
    path = repo / '.project-memory/verifications/325/VER-ac5.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding='utf-8')
    os.chown(path, AGENT_UID, AGENT_GID)
    os.chown(path.parent, AGENT_UID, AGENT_GID)


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'home').mkdir(parents=True, exist_ok=True)
    os.chown(WORK, AGENT_UID, AGENT_GID)
    os.chown(WORK / 'home', AGENT_UID, AGENT_GID)
    FAKEBIN.mkdir(parents=True, exist_ok=True)
    FAKE.write_text(FAKE_BODY, encoding='utf-8')
    os.chmod(FAKEBIN, 0o755)
    os.chmod(FAKE, 0o755)
    os.chown(FAKEBIN, AGENT_UID, AGENT_GID)
    os.chown(FAKE, AGENT_UID, AGENT_GID)
    fake_sha = hashlib.sha256(FAKE.read_bytes()).hexdigest()

    summary = {'code': str(CODE), 'fake_openssl_sha256': fake_sha,
               'fake_openssl_body': FAKE_BODY,
               'fake_openssl_output': subprocess.run([str(FAKE)], capture_output=True,
                                                     text=True).stdout.strip(),
               'code_sha256_at_runtime': hashlib.sha256(
                   (CODE / 'project_memory' / 'authority.py').read_bytes()).hexdigest()}
    for mode in ('path', 'env'):
        repo, record = build_case()
        write_forged(repo, record)
        proc = cli(f'attack_{mode}', 'goal', 'evidence', '--repo', '.', '--id', 'G-AC5',
                   '--criterion', 'C1', '--kind', 'verification', '--ref', 'VER-ac5',
                   repo=repo, mode=mode)
        summary[f'{mode}_exit'] = proc.returncode
        summary[f'{mode}_accepted'] = proc.returncode == 0
        summary[f'{mode}_stderr'] = (proc.stderr or '').strip()[-300:]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'summary': summary, 'steps': steps},
                              ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
