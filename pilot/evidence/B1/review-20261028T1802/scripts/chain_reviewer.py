"""PM-03 independent AC-7 chain: can a forged signature drive a Goal to achieved?

Runs as root, executes the CLI as uid 1000 against the root-owned anchor. Written
independently for the B1 review; it does not import PM-02's chain_probe.py.

Usage (as root): python3 chain_reviewer.py <CODE> <WORK> <OUT.json>
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

ANCHOR_DATA = json.loads(ANCHOR.read_text(encoding='utf-8'))
ANCHOR_ID = ANCHOR_DATA['anchor_id']
ISSUER = ANCHOR_DATA['issuer']
ALGORITHM = ANCHOR_DATA.get('algorithm', 'rsa-sha256')

steps: list[dict] = []


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def payload(record: dict) -> bytes:
    return canonical({k: v for k, v in record.items() if k != 'authority'})


def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


PATH_BASE = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
FAKEBIN: Path | None = None


def env_for(attack: bool = False) -> dict:
    path = PATH_BASE if not attack else f'{FAKEBIN}:{PATH_BASE}'
    return {
        'PATH': path,
        'HOME': str(WORK / 'home'), 'PYTHONPATH': str(CODE), 'PYTHONUTF8': '1',
        'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
        'PROJECT_MEMORY_TRUST_ANCHOR': str(ANCHOR),
    }


def cli(label: str, *args: str, repo: Path, attack: bool = False):
    proc = subprocess.run([sys.executable, '-m', 'project_memory', *args],
                          cwd=str(repo), capture_output=True, text=True, encoding='utf-8',
                          env=env_for(attack), user=AGENT_UID, group=AGENT_GID, extra_groups=[])
    steps.append({'label': label, 'argv': ['project-memory', *args],
                  'exit_code': proc.returncode, 'stdout': proc.stdout[-4000:],
                  'stderr': proc.stderr[-2000:]})
    return proc


def sh(*args: str, repo: Path) -> str:
    proc = subprocess.run(args, cwd=str(repo), capture_output=True, text=True,
                          encoding='utf-8', env=env_for(), user=AGENT_UID,
                          group=AGENT_GID, extra_groups=[])
    if proc.returncode != 0:
        raise RuntimeError(f'{args}: {proc.returncode}\n{proc.stdout}\n{proc.stderr}')
    return proc.stdout.strip()


def build_case() -> tuple[Path, str, dict]:
    case = Path(tempfile.mkdtemp(prefix='pm03-chain-', dir=str(WORK)))
    repo = case / 'repo'
    repo.mkdir()
    os.chown(case, AGENT_UID, AGENT_GID)
    os.chown(repo, AGENT_UID, AGENT_GID)
    (WORK / 'home').mkdir(parents=True, exist_ok=True)
    sh('git', 'init', '-q', repo=repo)
    sh('git', 'config', 'user.email', 'chain@example.invalid', repo=repo)
    sh('git', 'config', 'user.name', 'Chain', repo=repo)
    (repo / 'README.md').write_text('hello\n', encoding='utf-8')
    (repo / 'tests').mkdir()
    (repo / 'tests/check.py').write_text('print("check-ok")\n', encoding='utf-8')
    for p in (repo / 'README.md', repo / 'tests', repo / 'tests/check.py'):
        os.chown(p, AGENT_UID, AGENT_GID)
    sh('git', 'add', 'README.md', 'tests/check.py', repo=repo)
    sh('git', 'commit', '-qm', 'base', repo=repo)
    base = sh('git', 'rev-parse', 'HEAD', repo=repo)
    cli('goal_create', 'goal', 'create', '--repo', '.', '--id', 'G-CHAIN',
        '--title', 'chain', '--outcome', 'ship', '--owner', 'owner',
        '--criterion', 'criterion passes', repo=repo)
    cli('run_start', 'run', 'start', '--repo', '.', '--goal', 'G-CHAIN', '--task', '325',
        '--run-id', 'run-target', '--agent', 'dev', '--model-provider', 'qodercn',
        '--model-id', 'auto', '--base-sha', base, repo=repo)
    cli('run_finish', 'run', 'finish', '--repo', '.', '--task', '325', '--run-id', 'run-target',
        '--completed', 'x', '--remaining', 'y', '--head-sha', base, repo=repo)
    cli('ver_start', 'run', 'start', '--repo', '.', '--goal', 'G-CHAIN', '--task', '325',
        '--run-id', 'run-verifier', '--agent', 'verifier', '--model-provider', 'qodercn',
        '--model-id', 'verifier-model', '--base-sha', base, '--role', 'verifier', repo=repo)
    cli('ver_finish', 'run', 'finish', '--repo', '.', '--task', '325', '--run-id', 'run-verifier',
        '--completed', 'x', '--remaining', 'y', '--head-sha', base, repo=repo)
    test_proc = cli('test_run', 'test-run', '--repo', '.', '--commit', base,
                    '--command', 'python3 tests/check.py', '--agent', 'verifier', repo=repo)
    receipt = json.loads(test_proc.stdout)
    mapping = {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-CHAIN', 'task_id': '325',
        'criterion_description': 'criterion passes', 'target_repository': str(repo),
        'target_commit_sha': base, 'evidence_id': 'EV-1', 'evidence_source': 'test',
        'evidence_command': receipt['receipt']['command'],
        'evidence_log': receipt['log'], 'evidence_exit_code': receipt['receipt']['exit_code'],
        'evidence_receipt': receipt['path'], 'execution_status': 'passed',
        'coverage_claim': 'c', 'coverage_review_status': 'human_confirmed',
        'independent_verifier': 'verifier', 'verification_result': 'pass'}]}
    mapping_path = case / 'mapping.json'
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding='utf-8')
    os.chown(mapping_path, AGENT_UID, AGENT_GID)
    ver_proc = cli('verify', 'verify', '--repo', '.', '--target-run', 'run-target',
                   '--verifier-run', 'run-verifier', '--standard', 'criterion passes',
                   '--verdict', 'pass', '--evidence-level', 'locally_observed',
                   '--test-receipt', receipt['path'], '--criterion-evidence',
                   str(mapping_path), repo=repo)
    if ver_proc.returncode != 2:
        raise RuntimeError(f'verify did not produce a record: exit={ver_proc.returncode} '
                           f'err={ver_proc.stderr[-800:]}')
    ver_obj = json.loads(ver_proc.stdout)
    record = json.loads((repo / ver_obj['path']).read_text(encoding='utf-8'))
    return repo, base, record


def forge(record: dict, vid: str, goal_criteria: str | None) -> dict:
    rec = json.loads(json.dumps(record))
    rec['verification_id'] = vid
    rec['verified'] = True
    rec['status'] = 'VERIFIED'
    rec['mapping_status'] = 'complete'
    if goal_criteria is not None:
        rec['goal_criteria_sha256'] = goal_criteria
    for entry in rec.get('criterion_evidence') or []:
        entry['evidence_matched'] = True
    rec.pop('authority', None)
    body = payload(rec)
    rec['authority'] = {
        'status': 'trusted', 'issuer': ISSUER, 'anchor_id': ANCHOR_ID,
        'algorithm': ALGORITHM, 'signed_payload_sha256': sha_hex(body),
        'signature_b64': base64.b64encode(b'pm03-cannot-produce-this').decode('ascii'),
    }
    return rec


def write_record(repo: Path, rec: dict) -> None:
    path = repo / f'.project-memory/verifications/325/{rec["verification_id"]}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding='utf-8')
    os.chown(path, AGENT_UID, AGENT_GID)
    os.chown(path.parent, AGENT_UID, AGENT_GID)


def main() -> None:
    global FAKEBIN
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'home').mkdir(parents=True, exist_ok=True)
    os.chown(WORK, AGENT_UID, AGENT_GID)
    os.chown(WORK / 'home', AGENT_UID, AGENT_GID)
    # Agent-owned fake verifier that always exits 0 (the B1 attack vector).
    FAKEBIN = WORK / 'fakebin'
    FAKEBIN.mkdir(parents=True, exist_ok=True)
    fake = FAKEBIN / 'openssl'
    fake.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    os.chmod(FAKEBIN, 0o755)
    os.chmod(fake, 0o755)
    os.chown(FAKEBIN, AGENT_UID, AGENT_GID)
    os.chown(fake, AGENT_UID, AGENT_GID)

    repo, base, record0 = build_case()
    write_record(repo, forge(record0, 'VER-forged', None))
    ev = cli('goal_evidence_forged', 'goal', 'evidence', '--repo', '.', '--id', 'G-CHAIN',
             '--criterion', 'C1', '--kind', 'verification', '--ref', 'VER-forged',
             repo=repo, attack=True)
    summary = {'code': str(CODE), 'goal_evidence_exit': ev.returncode,
               'goal_evidence_accept': ev.returncode == 0,
               'goal_evidence_stderr': (ev.stderr or '').strip()[-300:]}

    # Re-bind the forged record to the current Goal criteria digest, then drive
    # the state machine exactly as an attacker would after a successful evidence
    # write.  This step runs regardless so the candidate's final status is
    # observable even when evidence is rejected.
    goal_path = repo / '.project-memory/goals/G-CHAIN.json'
    goal = json.loads(goal_path.read_text(encoding='utf-8'))
    digest = sha_hex(canonical(goal.get('success_criteria', [])))
    write_record(repo, forge(record0, 'VER-forged', digest))

    ev2 = cli('goal_evaluate', 'goal', 'evaluate', '--repo', '.', '--id', 'G-CHAIN',
              repo=repo, attack=True)
    summary['goal_evaluate_exit'] = ev2.returncode
    try:
        summary['goal_evaluate_satisfied'] = bool(json.loads(ev2.stdout).get('satisfied'))
    except Exception:
        summary['goal_evaluate_satisfied'] = None
    for target, label in (('approved', 'transition_approved'), ('active', 'transition_active'),
                          ('evaluating', 'transition_evaluating')):
        p = cli(label, 'goal', 'transition', '--repo', '.', '--id', 'G-CHAIN',
                '--to', target, *(['--approved-by', 'agent@example.invalid']
                                  if target == 'approved' else []), repo=repo, attack=True)
        summary[f'{label}_exit'] = p.returncode
    ach = cli('transition_achieved', 'goal', 'transition', '--repo', '.', '--id', 'G-CHAIN',
              '--to', 'achieved', '--approved-by', 'agent@example.invalid',
              repo=repo, attack=True)
    summary['transition_achieved_exit'] = ach.returncode
    final = json.loads(goal_path.read_text(encoding='utf-8'))
    summary['final_goal_status'] = final.get('status')
    summary['final_evidence_count'] = sum(
        len(c.get('evidence', [])) for c in final.get('success_criteria', []))
    summary['achieved'] = final.get('status') == 'achieved'

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'summary': summary, 'steps': steps},
                              ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
