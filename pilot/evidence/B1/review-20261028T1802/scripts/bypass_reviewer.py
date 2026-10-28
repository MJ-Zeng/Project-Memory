"""PM-03 independent bypass probes for B1.

Runs as uid 1000 (agent). Uses one-time keys generated here, never /etc keys.

1. Cross-validate the candidate's RSA-2048 and ECDSA P-256 verifiers against
   signatures made by these fresh keys (accept real, reject tampered/wrong-key).
2. Attacker-owned anchor replay: build a self-consistent, correctly self-signed
   record and a matching anchor that the agent owns; the CLI must reject it.

Usage (as uid 1000): python3 bypass_reviewer.py <CODE> <WORK> <OUT.json>
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

CODE = Path(sys.argv[1]).resolve()
WORK = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(CODE))
from project_memory import authority  # noqa: E402

WORK.mkdir(parents=True, exist_ok=True)
summary = {'code': str(CODE)}


def run(*args, cwd=None, env=None):
    return subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, encoding='utf-8', env=env)


def keypair(name, kind):
    priv, pub = WORK / f'{name}.key', WORK / f'{name}.pub'
    if kind == 'rsa':
        run('openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
            'rsa_keygen_bits:2048', '-out', str(priv))
    else:
        run('openssl', 'ecparam', '-name', 'prime256v1', '-genkey', '-noout',
            '-out', str(priv))
    run('openssl', 'pkey', '-in', str(priv), '-pubout', '-out', str(pub))
    return priv, pub.read_text(encoding='utf-8')


def sign(priv, data):
    body = WORK / f'{priv.stem}.bin'
    sig = WORK / f'{priv.stem}.sig'
    body.write_bytes(data)
    run('openssl', 'dgst', '-sha256', '-sign', str(priv), '-out', str(sig), str(body))
    return base64.b64encode(sig.read_bytes()).decode('ascii')


RECORD = {'schema_version': '1.2', 'kind': 'verification_record',
          'goal_id': 'G-PM03', 'verdict': 'pass', 'status': 'VERIFIED',
          'criterion_evidence': [{'criterion_id': 'C1', 'evidence_matched': True,
                                  'target_commit_sha': '0' * 40}],
          'target_head_sha': '0' * 40, 'checks': {'tests': {'ok': True}}}
PAYLOAD = authority.verification_payload(RECORD)

# --- 1. Cross-validation with fresh keys -------------------------------------
cross = {}
for name, kind, algo in (('pm03-rsa', 'rsa', 'rsa-sha256'),
                         ('pm03-ec', 'ec', 'ecdsa-sha256')):
    priv, pem = keypair(name, kind)
    good = sign(priv, PAYLOAD)
    other_priv, other_pem = keypair(name + '-other', kind)
    cross[algo] = {
        'key_pem_sha256': hashlib.sha256(pem.encode()).hexdigest(),
        'valid_accepted': authority._verify_signature(
            {'public_key_pem': pem}, PAYLOAD, good, algo)[0],
        'tampered_rejected': not authority._verify_signature(
            {'public_key_pem': pem}, PAYLOAD + b' ', good, algo)[0],
        'wrong_key_rejected': not authority._verify_signature(
            {'public_key_pem': other_pem}, PAYLOAD, good, algo)[0],
        'garbage_rejected': not authority._verify_signature(
            {'public_key_pem': pem}, PAYLOAD,
            base64.b64encode(b'not-a-signature').decode('ascii'), algo)[0],
    }
summary['cross_validation'] = cross

# --- 2. Attacker-owned anchor replay -----------------------------------------
repo = WORK / 'repo'
repo.mkdir(parents=True, exist_ok=True)
run('git', 'init', '-q', cwd=repo)
run('git', 'config', 'user.email', 'pm03@example.invalid', cwd=repo)
run('git', 'config', 'user.name', 'PM03', cwd=repo)
(repo / 'README.md').write_text('x\n', encoding='utf-8')
run('git', 'add', 'README.md', cwd=repo)
run('git', 'commit', '-qm', 'base', cwd=repo)
env = dict(os.environ)
env.update({'PYTHONPATH': str(CODE), 'PYTHONUTF8': '1',
            'PYTHONDONTWRITEBYTECODE': '1', 'GIT_CONFIG_NOSYSTEM': '1'})
run(sys.executable, '-m', 'project_memory', 'goal', 'create', '--repo', '.',
    '--id', 'G-PM03', '--title', 'x', '--outcome', 'y', '--owner', 'o',
    '--criterion', 'c', cwd=repo, env=env)
run('git', '-C', str(repo), 'add', '-A')
run('git', '-C', str(repo), 'commit', '-qm', 'goal')

priv, pem = keypair('pm03-attacker', 'rsa')
signed = dict(RECORD)
signed['verification_id'] = 'VER-self'
signed.pop('authority', None)
body = authority.verification_payload(signed)
signed['authority'] = {
    'status': 'trusted', 'issuer': 'PM-03 Attacker <pm03@pilot.invalid>',
    'anchor_id': 'pm03-attacker-anchor', 'algorithm': 'rsa-sha256',
    'signed_payload_sha256': hashlib.sha256(body).hexdigest(),
    'signature_b64': sign(priv, body)}
record_path = repo / '.project-memory/verifications/1/VER-self.json'
record_path.parent.mkdir(parents=True, exist_ok=True)
record_path.write_text(json.dumps(signed, ensure_ascii=False, indent=1), encoding='utf-8')
anchor_path = WORK / 'attacker-anchor.json'
anchor_path.write_text(json.dumps({
    'kind': 'project_memory_trust_anchor', 'schema_version': '1.0',
    'anchor_id': 'pm03-attacker-anchor', 'issuer': 'PM-03 Attacker <pm03@pilot.invalid>',
    'algorithm': 'rsa-sha256', 'public_key_pem': pem}, ensure_ascii=False), encoding='utf-8')
os.chmod(anchor_path, 0o644)

env['PROJECT_MEMORY_TRUST_ANCHOR'] = str(anchor_path)
proc = subprocess.run([sys.executable, '-m', 'project_memory', 'goal', 'evidence',
                       '--repo', '.', '--id', 'G-PM03', '--criterion', 'C1',
                       '--kind', 'verification', '--ref', 'VER-self'],
                      cwd=str(repo), capture_output=True, text=True, encoding='utf-8', env=env)
summary['attacker_anchor'] = {
    'signature_is_cryptographically_valid': authority._verify_signature(
        {'public_key_pem': pem}, body, signed['authority']['signature_b64'],
        'rsa-sha256')[0],
    'anchor_owned_by_current_user': anchor_path.stat().st_uid == os.getuid(),
    'goal_evidence_exit': proc.returncode,
    'accepted': proc.returncode == 0,
    'stderr': (proc.stderr or '').strip()[-300:],
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
