"""FINAL review E2E: init -> goal create -> evaluate -> checkpoint-request ->
test-key attach -> audit verify, plus one tampered-record rejection and one
unsigned/foreign-key checkpoint rejection.

Runs the real library and CLI code paths against a throwaway temp repo.  The
trust anchor is a *test* RSA key: this Windows host cannot satisfy the
same-user-ownership protection check, so ``authority.load_anchor`` is patched
to return the test anchor document (the same technique the B4 suite uses).
No production anchor, no production key, no network.

Usage: python e2e_run.py <worktree-root> <out-dir>
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT))

from project_memory import authority, cli, execution, trusted_exec  # noqa: E402
from project_memory.common import PMError, git_sha  # noqa: E402
from project_memory.coordination import (add_goal_evidence,  # noqa: E402
                                         attach_audit_checkpoint, audit_head,
                                         audit_verify, create_goal,
                                         evaluate_goal, finish_run, goal_show,
                                         load_goal, start_run, transition_goal,
                                         verify_run, write_audit_checkpoint_request)
from project_memory.execution import run_command  # noqa: E402

OPENSSL = os.environ.get('OPENSSL_EXE') or 'openssl'
GOAL = 'G-E2E'
CRITERION = '模块通过测试'
APPROVER = 'lead@example.com'


def emit(name, **data):
    record = {'step': name, **data}
    print(json.dumps(record, ensure_ascii=False))
    STEPS.append(record)
    return record


STEPS = []
WORK = Path(tempfile.mkdtemp(prefix='final-e2e-'))
REPO = WORK / 'repo'
REPO.mkdir()


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], check=True,
                          capture_output=True, text=True, encoding='utf-8')


def cli_env():
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT)
    env['PYTHONUTF8'] = '1'
    env.pop('PROJECT_MEMORY_TRUST_ANCHOR', None)
    return env


def cli_sub(argv, timeout=120):
    proc = subprocess.run([sys.executable, '-m', 'project_memory', *argv,
                           '--repo', str(REPO)], cwd=str(REPO), env=cli_env(),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=timeout)
    return proc


def cli_inproc(argv, anchor):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch('project_memory.authority.load_anchor',
                    return_value=(dict(anchor), 'ok')):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([*argv, '--repo', str(REPO)])
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------- test keys
KEYDIR = WORK / 'keys'
KEYDIR.mkdir()
KEY = KEYDIR / 'test-key.pem'
PUB = KEYDIR / 'test-key.pub.pem'
OTHER_KEY = KEYDIR / 'other-key.pem'
subprocess.run([OPENSSL, 'genpkey', '-algorithm', 'RSA',
                '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(KEY)],
               check=True, capture_output=True)
subprocess.run([OPENSSL, 'pkey', '-in', str(KEY), '-pubout', '-out', str(PUB)],
               check=True, capture_output=True)
subprocess.run([OPENSSL, 'genpkey', '-algorithm', 'RSA',
                '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(OTHER_KEY)],
               check=True, capture_output=True)
ANCHOR = {
    'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
    'anchor_id': 'final-review-test-anchor', 'issuer': 'final-review-test-signer',
    'algorithm': 'rsa-sha256',
    'public_key_pem': PUB.read_text(encoding='utf-8'),
}


def sign_bytes(payload, key, name):
    payload_file = WORK / f'{name}.payload'
    signature_file = WORK / f'{name}.sig'
    payload_file.write_bytes(payload)
    subprocess.run([OPENSSL, 'dgst', '-sha256', '-sign', str(key),
                    '-out', str(signature_file), str(payload_file)],
                   check=True, capture_output=True)
    return signature_file


def sign_record(record, payload_builder, name):
    payload = payload_builder(record)
    signature = sign_bytes(payload, KEY, name)
    record['authority'] = {
        'status': 'trusted', 'anchor_id': ANCHOR['anchor_id'],
        'issuer': ANCHOR['issuer'], 'algorithm': 'rsa-sha256',
        'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
        'signature_b64': base64.b64encode(signature.read_bytes()).decode('ascii'),
    }
    return record


# ---------------------------------------------------------------- repo setup
git('init', '-q')
git('config', 'user.email', 'final@example.invalid')
git('config', 'user.name', 'FINAL')
(REPO / 'README.md').write_text('hello\n', encoding='utf-8')
(REPO / 'tests').mkdir()
(REPO / 'tests/test_auth.py').write_text('def test_ok():\n    assert True\n',
                                         encoding='utf-8')
git('add', 'README.md', 'tests/test_auth.py')
git('commit', '-qm', 'base')
BASE = git_sha(REPO)

# 1. CLI init (real subprocess, no anchor involved)
proc = cli_sub(['init', '--install', 'none', '--profile', 'overlay'])
emit('cli-init', argv=['init', '--install', 'none', '--profile', 'overlay'],
     exit_code=proc.returncode, created=(REPO / '.project-memory/config.json').is_file(),
     stderr=proc.stderr.strip()[:400])

# 2. CLI goal create (real subprocess)
proc = cli_sub(['goal', 'create', '--id', GOAL, '--title', 'E2E goal',
                '--outcome', 'checkpoint chain verifies', '--owner', 'owner@example.com',
                '--criterion', CRITERION])
emit('cli-goal-create', exit_code=proc.returncode,
     goal_file=(REPO / f'.project-memory/goals/{GOAL}.json').is_file(),
     stderr=proc.stderr.strip()[:400])

# 3. CLI evaluate with no evidence -> unsatisfied, exit 2
proc = cli_sub(['goal', 'evaluate', '--id', GOAL])
emit('cli-goal-evaluate-empty', exit_code=proc.returncode,
     satisfied=json.loads(proc.stdout)['satisfied'] if proc.stdout.strip() else None,
     stderr=proc.stderr.strip()[:400])

# 4. Real receipt + signed execution attestation (test anchor)
out = run_command(REPO, [sys.executable, '-c',
                         "import sys; print('1 passed'); sys.exit(0)"],
                  BASE, executed_by='final-review', mode='local')
ref = '.project-memory/attestations/ATT-E2E.json'
out['receipt']['execution_attestation_path'] = ref
receipt_path = REPO / out['path']
out['receipt']['content_sha256'] = execution._canonical_receipt_digest(out['receipt'])
receipt_path.write_text(json.dumps(out['receipt'], ensure_ascii=False, indent=2),
                        encoding='utf-8')
receipt = out['receipt']
attestation = {
    'schema_version': '1.0', 'kind': 'execution_attestation',
    'attestation_id': 'ATT-E2E',
    'receipt_id': receipt['receipt_id'],
    'receipt_sha256': receipt['content_sha256'],
    'commit_sha': receipt['commit_sha'],
    'tree_sha': receipt['tree_sha'],
    'snapshot_id': receipt['snapshot_id'],
    'snapshot_sha256': receipt['snapshot_sha256'],
    'command_sha256': hashlib.sha256(receipt['command'].encode('utf-8')).hexdigest(),
    'launcher': 'project_memory.trusted_exec',
    'launcher_mode': trusted_exec.MODE,
    'isolation': {'mode': trusted_exec.MODE, 'uid': 0, 'pid_ns_levels': 1,
                  'env_count': 5, 'network': 'isolated'},
    'created_at': '2026-10-29T00:00:00Z',
}
sign_record(attestation, authority.execution_record_payload, 'ATT-E2E')
attest_path = REPO / ref
attest_path.parent.mkdir(parents=True, exist_ok=True)
attest_path.write_text(json.dumps(attestation, ensure_ascii=False, indent=2),
                       encoding='utf-8')
emit('receipt-and-attestation', receipt_path=out['path'], log=out['log'],
     exit_code=receipt['exit_code'], attestation=ref)

# 5. Verification record signed by the test anchor
mapping = {'criteria': [{
    'criterion_id': 'C1', 'goal_id': GOAL, 'task_id': 'E2E',
    'criterion_description': CRITERION, 'target_repository': str(REPO),
    'target_commit_sha': BASE, 'evidence_id': 'EV-1',
    'evidence_source': 'test', 'evidence_command': receipt['command'],
    'evidence_log': out['log'], 'evidence_exit_code': receipt['exit_code'],
    'evidence_receipt': out['path'], 'execution_status': 'passed',
    'coverage_claim': '覆盖对应标准', 'coverage_review_status': 'confirmed',
    'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}
start_run(REPO, GOAL, 'E2E', 'run-target', 'dev-agent', 'qodercn', 'auto',
          base_sha=BASE, role='executor')
finish_run(REPO, 'E2E', 'run-target', ['implemented'], ['verify'], head_sha=BASE,
           tests=[{'command': receipt['command'], 'exit_code': 0, 'log': out['log']}])
start_run(REPO, GOAL, 'E2E', 'run-verifier', 'verifier-agent', 'qodercn',
          'verifier-model', base_sha=BASE, role='verifier')
result = verify_run(REPO, 'run-target', 'run-verifier', 'acceptance', 'pass',
                    'locally_observed', test_receipt=out['path'],
                    criterion_evidence=mapping)
record = json.loads(json.dumps(result['verification']))
record['status'] = 'VERIFIED'
record['verified'] = True
record['mapping_status'] = 'complete'
for entry in record.get('criterion_evidence', []):
    entry['evidence_matched'] = True
record.pop('authority', None)
sign_record(record, authority.verification_payload, record['verification_id'])
verification_path = (REPO / '.project-memory/verifications/E2E'
                     / f"{record['verification_id']}.json")
verification_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                             encoding='utf-8')
with mock.patch('project_memory.authority.load_anchor',
                return_value=(dict(ANCHOR), 'ok')):
    add_goal_evidence(REPO, GOAL, 'C1', 'verification', record['verification_id'])
    evaluation = evaluate_goal(REPO, GOAL)
emit('verified-and-satisfied', verification=str(verification_path.relative_to(REPO)),
     satisfied=evaluation['satisfied'],
     evaluation_status=evaluation.get('evaluation_status'))

# 6. CLI evaluate with evidence (in-process, test anchor)
code, stdout, stderr = cli_inproc(['goal', 'evaluate', '--id', GOAL], ANCHOR)
emit('cli-goal-evaluate-satisfied', exit_code=code,
     satisfied=json.loads(stdout)['satisfied'], stderr=stderr.strip()[:300])

# 7. CLI transitions to evaluating / achieved
for target in ('approved', 'active', 'evaluating'):
    code, stdout, stderr = cli_inproc(
        ['goal', 'transition', '--id', GOAL, '--to', target,
         '--approved-by', APPROVER], ANCHOR)
    emit(f'cli-transition-{target}', exit_code=code, stderr=stderr.strip()[:300])

code, stdout, stderr = cli_inproc(
    ['goal', 'transition', '--id', GOAL, '--to', 'achieved',
     '--approved-by', APPROVER], ANCHOR)
payload = json.loads(stdout) if stdout.strip() else {}
emit('cli-transition-achieved', exit_code=code,
     status=load_goal(REPO, GOAL)['status'],
     checkpoint_request=payload.get('checkpoint_request'), stderr=stderr.strip()[:300])

# 8. CLI checkpoint-request
code, stdout, stderr = cli_inproc(
    ['audit', 'checkpoint-request', '--goal', GOAL, '--approved-by', APPROVER], ANCHOR)
request_path = REPO / '.project-memory/audit/head.request.json'
request = json.loads(request_path.read_text(encoding='utf-8'))
emit('cli-checkpoint-request', exit_code=code, request_exists=request_path.is_file(),
     request_goal=request.get('goal_id'), request_status=request.get('status'),
     request_chain_length=request.get('chain_length'), stderr=stderr.strip()[:300])

# 9. Fail-closed attach checks (before the legitimate one)
head_path = REPO / '.project-memory/audit/head.json'
request_sig = sign_bytes(request_path.read_bytes(), KEY, 'CKPT')
with mock.patch('project_memory.authority.load_anchor',
                return_value=(None, '未配置受保护的信任锚')):
    try:
        attach_audit_checkpoint(REPO, request_sig)
        unconfigured = 'ATTACHED (unexpected)'
    except PMError as exc:
        unconfigured = str(exc)
emit('attach-unconfigured-anchor', result=unconfigured, head_exists=head_path.exists())

wrong_sig = sign_bytes(request_path.read_bytes(), OTHER_KEY, 'CKPT-WRONG')
try:
    with mock.patch('project_memory.authority.load_anchor',
                    return_value=(dict(ANCHOR), 'ok')):
        attach_audit_checkpoint(REPO, wrong_sig)
    wrong_key = 'ATTACHED (unexpected)'
except PMError as exc:
    wrong_key = str(exc)
emit('attach-foreign-key', result=wrong_key, head_exists=head_path.exists())

# 10. Legitimate attach with the test key
with mock.patch('project_memory.authority.load_anchor',
                return_value=(dict(ANCHOR), 'ok')):
    attached = attach_audit_checkpoint(REPO, request_sig)
report = None
with mock.patch('project_memory.authority.load_anchor',
                return_value=(dict(ANCHOR), 'ok')):
    report = audit_verify(REPO)
checkpoint = report.get('checkpoint') or {}
emit('attach-legit-and-verify', trusted=attached.get('trusted'),
     status=report['status'], valid=report['valid'],
     authoritative=report['authoritative'],
     head=report['head'], checkpoint_chain_head=checkpoint.get('chain_head'),
     checkpoint_goal=checkpoint.get('goal_id'), checkpoint_status=checkpoint.get('status'),
     checkpoint_chain_length=checkpoint.get('chain_length'))

with mock.patch('project_memory.authority.load_anchor',
                return_value=(dict(ANCHOR), 'ok')):
    shown = goal_show(REPO, GOAL)
emit('goal-show-achieved', effective_status=shown['effective_status'],
     status_trusted=shown['status_trusted'], status_problems=shown['status_problems'],
     status_authority=shown['status_authority'])

# 11. CLI audit verify with and without the anchor
code, stdout, stderr = cli_inproc(['audit', 'verify'], ANCHOR)
inproc_report = json.loads(stdout)
emit('cli-audit-verify-test-anchor', exit_code=code, status=inproc_report['status'],
     authoritative=inproc_report['authoritative'])

proc = cli_sub(['audit', 'verify'])
sub_report = json.loads(proc.stdout) if proc.stdout.strip() else {}
emit('cli-audit-verify-no-anchor', exit_code=proc.returncode,
     status=sub_report.get('status'), valid=sub_report.get('valid'),
     problems=sub_report.get('problems'))

# 12. Tamper: rewrite one entry and rebuild the whole chain consistently
audit_path = REPO / '.project-memory/audit/verification_attempts.jsonl'
ledger_backup = audit_path.read_bytes()
head_backup = head_path.read_bytes()
entries = [json.loads(line) for line in
           ledger_backup.decode('utf-8').splitlines() if line.strip()]
entries[0]['outcome'] = 'edited'
previous = '0' * 64
for index, entry in enumerate(entries, 1):
    entry.pop('entry_hash', None)
    entry['seq'] = index
    entry['prev_hash'] = previous
    entry['entry_hash'] = authority.canonical_digest(entry)
    previous = entry['entry_hash']
audit_path.write_text(''.join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
                              for entry in entries), encoding='utf-8')
with mock.patch('project_memory.authority.load_anchor',
                return_value=(dict(ANCHOR), 'ok')):
    tampered = audit_verify(REPO)
    tampered_eval = evaluate_goal(REPO, GOAL)
emit('tamper-rebuilt-chain', valid=tampered['valid'], problems=tampered['problems'],
     effective_status=tampered_eval['effective_status'],
     status_trusted=tampered_eval['status_trusted'])
audit_path.write_bytes(ledger_backup)

# 13. Unsigned checkpoint: drop the authority block from head.json
head_record = json.loads(head_backup.decode('utf-8'))
unsigned = dict(head_record)
unsigned.pop('authority', None)
head_path.write_text(json.dumps(unsigned, ensure_ascii=False, indent=2), encoding='utf-8')
with mock.patch('project_memory.authority.load_anchor',
                return_value=(dict(ANCHOR), 'ok')):
    unsigned_report = audit_verify(REPO)
    unsigned_eval = evaluate_goal(REPO, GOAL)
emit('unsigned-checkpoint', valid=unsigned_report['valid'],
     authoritative=unsigned_report['authoritative'],
     problems=unsigned_report['problems'],
     effective_status=unsigned_eval['effective_status'],
     status_trusted=unsigned_eval['status_trusted'])

# 14. Restore and confirm the legitimate state still verifies
head_path.write_bytes(head_backup)
with mock.patch('project_memory.authority.load_anchor',
                return_value=(dict(ANCHOR), 'ok')):
    restored = audit_verify(REPO)
    restored_eval = evaluate_goal(REPO, GOAL)
emit('restored-authoritative', status=restored['status'],
     authoritative=restored['authoritative'],
     effective_status=restored_eval['effective_status'],
     status_trusted=restored_eval['status_trusted'])

summary = {
    'worktree': str(ROOT), 'temp_repo': str(REPO), 'base_commit': BASE,
    'anchor': {'anchor_id': ANCHOR['anchor_id'], 'issuer': ANCHOR['issuer'],
               'algorithm': ANCHOR['algorithm'],
               'note': 'test-only RSA key generated for this run; load_anchor patched'},
    'steps': STEPS,
}
(OUT / 'e2e-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding='utf-8')
print(f'SUMMARY_WRITTEN {OUT / "e2e-summary.json"}')
