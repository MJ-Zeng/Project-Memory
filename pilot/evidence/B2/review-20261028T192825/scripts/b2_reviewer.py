"""PM-03 independent B2 reproduction.

Logic-level test double: a temporary RSA key and a patched
``authority.load_anchor`` stand in for anchor-a.  This is NOT an anchor-a E2E
run.  Every case drives the real gate (``_verification_ok`` +
``add_goal_evidence`` + ``evaluate_goal``) on the candidate code.

Usage: b2_reviewer.py <candidate_code> <work_dir> <out_json>
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
sys.path.insert(0, str(CODE))

from project_memory import authority, execution, trusted_exec  # noqa: E402
from project_memory.common import PMError, git_sha  # noqa: E402
from project_memory.coordination import (  # noqa: E402
    _verification_ok, add_goal_evidence, create_goal, evaluate_goal,
    finish_run, load_goal, start_run, verify_run)
from project_memory.execution import run_command, verify_receipt  # noqa: E402

CRITERION = '模块通过测试'
TASK = '325'
OPENSSL = shutil.which('openssl')
if not OPENSSL:
    raise SystemExit('openssl not found')

WORK.mkdir(parents=True, exist_ok=True)
KEY_DIR = Path(tempfile.mkdtemp(prefix='b2-keys-', dir=str(WORK)))
KEY = KEY_DIR / 'review-key.pem'
PUB = KEY_DIR / 'review-key.pub.pem'
KEY2 = KEY_DIR / 'wrong-key.pem'


def run(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, **kw)


run(OPENSSL, 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
    '-out', str(KEY))
run(OPENSSL, 'pkey', '-in', str(KEY), '-pubout', '-out', str(PUB))
run(OPENSSL, 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
    '-out', str(KEY2))

ANCHOR = {
    'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
    'anchor_id': 'b2-review-anchor', 'issuer': 'B2 reviewer test signer',
    'algorithm': 'rsa-sha256',
    'public_key_pem': PUB.read_text(encoding='utf-8'),
}
REAL_LOAD_ANCHOR = authority.load_anchor


def fake_load_anchor(repo):
    return dict(ANCHOR), 'test double: temporary reviewer anchor'


authority.load_anchor = fake_load_anchor

case_counter = 0
CASES: list[dict] = []


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign(record, payload_builder, name, key=KEY):
    payload = payload_builder(record)
    body = WORK / f'{name}.payload'
    sig = WORK / f'{name}.sig'
    body.write_bytes(payload)
    run(OPENSSL, 'dgst', '-sha256', '-sign', str(key), '-out', str(sig), str(body))
    return {'status': 'trusted', 'anchor_id': ANCHOR['anchor_id'],
            'issuer': ANCHOR['issuer'], 'algorithm': 'rsa-sha256',
            'signed_payload_sha256': sha(payload),
            'signature_b64': base64.b64encode(sig.read_bytes()).decode('ascii')}


def make_repo(tag):
    global case_counter
    case_counter += 1
    repo = WORK / f'case{case_counter:02d}-{tag}'
    repo.mkdir()
    git = lambda *a: run('git', '-C', str(repo), *a)  # noqa: E731
    git('init', '-q')
    git('config', 'user.email', 'reviewer@example.invalid')
    git('config', 'user.name', 'PM-03 Reviewer')
    (repo / 'README.md').write_text('hello\n', encoding='utf-8')
    (repo / 'tests').mkdir()
    (repo / 'tests/check.py').write_text('print("check-ok")\n', encoding='utf-8')
    git('add', 'README.md', 'tests/check.py')
    git('commit', '-qm', 'base')
    return repo, git_sha(repo)


def rewrite_receipt(repo, out):
    out['receipt']['content_sha256'] = execution._canonical_receipt_digest(out['receipt'])
    (repo / out['path']).write_text(
        json.dumps(out['receipt'], ensure_ascii=False, indent=2), encoding='utf-8')


def attach_attestation(repo, out, name='ATT-1', *, omit=(), key=KEY):
    ref = f'.project-memory/attestations/{name}.json'
    out['receipt']['execution_attestation_path'] = ref
    rewrite_receipt(repo, out)
    receipt = out['receipt']
    record = {
        'schema_version': '1.0', 'kind': 'execution_attestation',
        'attestation_id': name, 'receipt_id': receipt['receipt_id'],
        'receipt_sha256': receipt['content_sha256'],
        'commit_sha': receipt['commit_sha'], 'tree_sha': receipt['tree_sha'],
        'snapshot_id': receipt['snapshot_id'],
        'snapshot_sha256': receipt['snapshot_sha256'],
        'command_sha256': sha(receipt['command'].encode('utf-8')),
        'launcher': 'project_memory.trusted_exec',
        'launcher_mode': trusted_exec.MODE,
        'isolation': {'mode': trusted_exec.MODE, 'uid': 0, 'pid_ns_levels': 1,
                      'env_count': 5, 'network': 'isolated'},
        'created_at': '2026-01-01T00:00:00Z',
    }
    for field in omit:
        record.pop(field, None)
    record['authority'] = sign(record, authority.execution_record_payload, name, key)
    path = repo / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def attach_exception(repo, out, name='EXC-1', *, criterion='C1', goal='G-1',
                     key=KEY, signed=True, overrides=None, ref_override=None):
    ref = ref_override or f'.project-memory/exceptions/{name}.json'
    out['receipt']['execution_exception_path'] = ref
    rewrite_receipt(repo, out)
    receipt = out['receipt']
    record = {
        'schema_version': '1.0', 'kind': 'execution_exception',
        'exception_id': name, 'goal_id': goal, 'criterion_ids': [criterion],
        'receipt_id': receipt['receipt_id'],
        'receipt_sha256': receipt['content_sha256'],
        'commit_sha': receipt['commit_sha'],
        'reason': 'the local execution cannot be attested; human owns provenance',
        'scope': 'one-off B2 review reproduction',
        'issued_by': 'human@example.invalid',
        'created_at': '2026-01-01T00:00:00Z',
    }
    if overrides:
        record.update(overrides)
    if signed:
        record['authority'] = sign(record, authority.execution_record_payload, name, key)
    else:
        record['authority'] = authority.untrusted_envelope('agent wrote this exception')
    path = repo / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def build(tag, *, attestation=None, exception=None, receipt_edit=None,
          attestation_edit=None, exception_edit=None):
    repo, base = make_repo(tag)
    out = run_command(repo, [sys.executable, '-c', "import sys; print('ok'); sys.exit(0)"],
                      base, executed_by='pm03-reviewer')
    if receipt_edit:
        receipt_edit(repo, out)
    if attestation is not None:
        if attestation == 'signed':
            attach_attestation(repo, out)
        elif attestation == 'signed-omit-snapshot':
            attach_attestation(repo, out, omit=('snapshot_id',))
        elif attestation == 'wrong-key':
            attach_attestation(repo, out, key=KEY2)
        elif attestation == 'tamper-isolation':
            rec = attach_attestation(repo, out)
            rec['isolation']['uid'] = 1
            (repo / out['receipt']['execution_attestation_path']).write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
        elif attestation == 'tamper-receipt-sha':
            rec = attach_attestation(repo, out)
            rec['receipt_sha256'] = '0' * 64
            (repo / out['receipt']['execution_attestation_path']).write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
        elif attestation == 'unsigned':
            ref = '.project-memory/attestations/ATT-x.json'
            out['receipt']['execution_attestation_path'] = ref
            rewrite_receipt(repo, out)
            rec = {
                'schema_version': '1.0', 'kind': 'execution_attestation',
                'attestation_id': 'ATT-x', 'receipt_id': out['receipt']['receipt_id'],
                'receipt_sha256': out['receipt']['content_sha256'],
                'commit_sha': out['receipt']['commit_sha'],
                'tree_sha': out['receipt']['tree_sha'],
                'snapshot_id': out['receipt']['snapshot_id'],
                'snapshot_sha256': out['receipt']['snapshot_sha256'],
                'command_sha256': sha(out['receipt']['command'].encode('utf-8')),
                'launcher': 'project_memory.trusted_exec',
                'launcher_mode': trusted_exec.MODE,
                'isolation': {'uid': 0, 'pid_ns_levels': 1, 'env_count': 1},
                'authority': {'status': 'trusted', 'anchor_id': ANCHOR['anchor_id'],
                              'issuer': ANCHOR['issuer'], 'algorithm': 'rsa-sha256',
                              'signed_payload_sha256': '0' * 64,
                              'signature_b64': base64.b64encode(b'forged').decode('ascii')},
            }
            path = repo / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
        elif attestation == 'missing-file':
            out['receipt']['execution_attestation_path'] = \
                '.project-memory/attestations/absent.json'
            rewrite_receipt(repo, out)
        elif attestation == 'outside-meta':
            outside = WORK / 'outside-attestation.json'
            rec = {'schema_version': '1.0', 'kind': 'execution_attestation'}
            rec['authority'] = sign(rec, authority.execution_record_payload, 'outside')
            outside.write_text(json.dumps(rec), encoding='utf-8')
            out['receipt']['execution_attestation_path'] = str(outside)
            rewrite_receipt(repo, out)
        elif attestation == 'legacy-self-written':
            receipt = out['receipt']
            receipt['isolation'] = {'mode': trusted_exec.MODE,
                                    'snapshot_wsl': '/tmp/snapshot'}
            receipt['execution_provenance'] = {
                'kind': 'trusted_launcher', 'launcher': 'project_memory.trusted_exec',
                'attested': True, 'trusted': True}
            receipt['attestation_path'] = '.project-memory/attest/attest.json'
            rewrite_receipt(repo, out)
            legacy = {
                'ok': True, 'mode': trusted_exec.MODE,
                'receipt_id': receipt['receipt_id'], 'snapshot': '/tmp/snapshot',
                'command_sha256': sha(receipt['command'].encode('utf-8')),
            }
            path = repo / receipt['attestation_path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(legacy), encoding='utf-8')
        elif attestation == 'sha256-mismatch':
            rec = attach_attestation(repo, out)
            out['receipt']['execution_attestation_sha256'] = '0' * 64
            rewrite_receipt(repo, out)
            rec['receipt_sha256'] = out['receipt']['content_sha256']
            rec['authority'] = sign(rec, authority.execution_record_payload, 'ATT-sha')
            (repo / out['receipt']['execution_attestation_path']).write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
    if exception is not None:
        if exception == 'signed':
            attach_exception(repo, out)
        elif exception == 'unsigned':
            attach_exception(repo, out, signed=False)
        elif exception == 'wrong-key':
            attach_exception(repo, out, key=KEY2)
        elif exception == 'wrong-goal':
            attach_exception(repo, out, goal='G-OTHER')
        elif exception == 'wrong-criterion':
            attach_exception(repo, out, criterion='C9')
        elif exception == 'missing-issued-by':
            attach_exception(repo, out, overrides={'issued_by': ''})
        elif exception == 'missing-reason':
            attach_exception(repo, out, overrides={'reason': ''})
    if attestation_edit:
        attestation_edit(repo, out)
    if exception_edit:
        exception_edit(repo, out)
    return repo, base, out


def mapping(repo, base, out):
    receipt = out['receipt']
    return {'criteria': [{
        'criterion_id': 'C1', 'goal_id': 'G-1', 'task_id': TASK,
        'criterion_description': CRITERION, 'target_repository': str(repo),
        'target_commit_sha': base, 'evidence_id': 'EV-1',
        'evidence_source': 'test', 'evidence_command': receipt['command'],
        'evidence_log': out['log'], 'evidence_exit_code': receipt['exit_code'],
        'evidence_receipt': out['path'], 'execution_status': 'passed',
        'coverage_claim': 'covers the criterion', 'coverage_review_status': 'confirmed',
        'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}


def signed_verification(repo, base, out, name, *, goal_digest=None):
    create_goal(repo, 'G-1', 'B2 review', 'background', 'outcome', 'owner', [CRITERION])
    start_run(repo, 'G-1', TASK, 'run-target', 'dev-agent', 'qodercn', 'auto',
              base_sha=base, role='executor')
    finish_run(repo, TASK, 'run-target', ['done'], ['verify'], head_sha=base,
               tests=[{'command': out['receipt']['command'],
                       'exit_code': out['receipt']['exit_code'], 'log': out['log']}])
    start_run(repo, 'G-1', TASK, 'run-verifier', 'verifier-agent', 'qodercn',
              'verifier-model', base_sha=base, role='verifier')
    result = verify_run(repo, 'run-target', 'run-verifier', 'acceptance', 'pass',
                        'locally_observed', test_receipt=out['path'],
                        criterion_evidence=mapping(repo, base, out))
    record = json.loads(json.dumps(result['verification']))
    record['status'] = 'VERIFIED'
    record['verified'] = True
    record['mapping_status'] = 'complete'
    for entry in record.get('criterion_evidence') or []:
        entry['evidence_matched'] = True
    if goal_digest is not None:
        record['goal_criteria_sha256'] = goal_digest
    record.pop('authority', None)
    record['authority'] = sign(record, authority.verification_payload, name)
    path = repo / '.project-memory/verifications' / str(record['task']) \
        / f"{record['verification_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def run_case(name, expected, repo, record):
    evidence = {'kind': 'verification', 'ref': record['verification_id']}
    ok, reason, trust = _verification_ok(repo, evidence, 'G-1', 'C1')
    rejected = False
    try:
        add_goal_evidence(repo, 'G-1', 'C1', 'verification', record['verification_id'])
        accepted = True
    except PMError:
        accepted = False
        rejected = True
    evaluation = evaluate_goal(repo, 'G-1')
    result = {'name': name, 'expected': expected, 'ok': ok, 'trust': trust,
              'reason': reason, 'add_goal_evidence': 'accepted' if accepted else 'rejected',
              'evaluate_satisfied': evaluation['satisfied'],
              'evaluate_status': evaluation['evaluation_status']}
    if expected == 'reject':
        result['pass'] = (not ok) and rejected and (not evaluation['satisfied'])
    else:
        result['pass'] = ok and accepted and evaluation['satisfied']
    CASES.append(result)
    return result


# ---------------------------------------------------------------- AC-1 / AC-4
repo, base, out = build('handwritten-untrusted')


def mark_handwritten(repo, out):
    out['receipt']['execution_provenance'] = {
        'kind': 'local_untrusted', 'trusted': False, 'reason': 'written by hand'}
    out['receipt']['executed_by'] = 'handwritten'
    rewrite_receipt(repo, out)


mark_handwritten(repo, out)
rec = signed_verification(repo, base, out, 'VER-forged-untrusted')
run_case('AC-1 handwritten receipt (trusted=false), valid verification signature',
         'reject', repo, rec)

repo, base, out = build('local-untrusted')
rec = signed_verification(repo, base, out, 'VER-local-untrusted')
run_case('AC-4 local untrusted receipt, valid signature, no exception', 'reject', repo, rec)

# ---------------------------------------------------------------- AC-2
repo, base, out = build('claimed-trusted')


def claim_trusted(repo, out):
    out['receipt']['execution_provenance'] = {
        'kind': 'local_untrusted', 'trusted': True, 'reason': 'claimed trusted=true'}
    rewrite_receipt(repo, out)


claim_trusted(repo, out)
checked = verify_receipt(repo, out['path'])
rec = signed_verification(repo, base, out, 'VER-claimed-trusted')
run_case('AC-2 receipt claims trusted=true, no attestation', 'reject', repo, rec)
CASES[-1]['receipt_integrity_valid'] = checked['valid']
CASES[-1]['parser_provenance_trusted'] = checked['provenance']['trusted']

repo, base, out = build('self-written-attestation', attestation='legacy-self-written')
checked = verify_receipt(repo, out['path'])
rec = signed_verification(repo, base, out, 'VER-self-written-attestation')
run_case('self-written launcher attestation (legacy attestation_path, unsigned)',
         'reject', repo, rec)
CASES[-1]['receipt_integrity_valid'] = checked['valid']
CASES[-1]['parser_provenance_trusted'] = checked['provenance']['trusted']

repo, base, out = build('unsigned-exec-attestation', attestation='unsigned')
rec = signed_verification(repo, base, out, 'VER-unsigned-attestation')
run_case('AC-3b execution_attestation_path with forged envelope', 'reject', repo, rec)

# ---------------------------------------------------------------- AC-3
repo, base, out = build('genuine-attestation', attestation='signed')


def bind_and_resign(repo, record):
    goal = load_goal(repo, 'G-1')
    digest = authority.canonical_digest(goal['success_criteria'])
    record['goal_criteria_sha256'] = digest
    record.pop('authority', None)
    record['authority'] = sign(record, authority.verification_payload, 'VER-genuine')
    path = repo / '.project-memory/verifications' / str(record['task']) \
        / f"{record['verification_id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')


rec = signed_verification(repo, base, out, 'VER-genuine')
_ok, _reason, _trust = _verification_ok(repo, {'kind': 'verification',
                                               'ref': rec['verification_id']}, 'G-1', 'C1')
if _ok:
    add_goal_evidence(repo, 'G-1', 'C1', 'verification', rec['verification_id'])
    bind_and_resign(repo, rec)
result = run_case('AC-3 signed attestation bound to receipt/commit is accepted',
                  'accept', repo, rec)

# replay boundary: same attestation, same receipt, same commit
ok_again, reason_again, trust_again = _verification_ok(
    repo, {'kind': 'verification', 'ref': rec['verification_id']}, 'G-1', 'C1')
CASES.append({'name': 'replay same attestation to same receipt/commit',
              'expected': 'accept_by_design', 'ok': ok_again, 'trust': trust_again,
              'reason': reason_again, 'pass': ok_again})

# ---------------------------------------------------------------- AC-4 exception
repo, base, out = build('signed-exception', exception='signed')
rec = signed_verification(repo, base, out, 'VER-exception')
_ok, _reason, _trust = _verification_ok(repo, {'kind': 'verification',
                                               'ref': rec['verification_id']}, 'G-1', 'C1')
if _ok:
    add_goal_evidence(repo, 'G-1', 'C1', 'verification', rec['verification_id'])
    bind_and_resign(repo, rec)
run_case('AC-4 signed human exception covers local execution', 'accept', repo, rec)

repo, base, out = build('unsigned-exception', exception='unsigned')
rec = signed_verification(repo, base, out, 'VER-exception-unsigned')
run_case('exception without a signature', 'reject', repo, rec)

repo, base, out = build('wrong-key-exception', exception='wrong-key')
rec = signed_verification(repo, base, out, 'VER-exception-wrong-key')
run_case('exception signed by a non-anchor key', 'reject', repo, rec)

repo, base, out = build('wrong-goal-exception', exception='wrong-goal')
rec = signed_verification(repo, base, out, 'VER-exception-wrong-goal')
run_case('exception bound to another goal', 'reject', repo, rec)

repo, base, out = build('wrong-criterion-exception', exception='wrong-criterion')
rec = signed_verification(repo, base, out, 'VER-exception-wrong-criterion')
run_case('exception does not cover the criterion', 'reject', repo, rec)

repo, base, out = build('missing-issued-by-exception', exception='missing-issued-by')
rec = signed_verification(repo, base, out, 'VER-exception-missing-issued-by')
run_case('exception missing issued_by', 'reject', repo, rec)

repo, base, out = build('missing-reason-exception', exception='missing-reason')
rec = signed_verification(repo, base, out, 'VER-exception-missing-reason')
run_case('exception missing reason', 'reject', repo, rec)

# ---------------------------------------------------------------- AC-5 bypass matrix
repo, base, out_a = build('swap-receipt', attestation='signed')
rec = signed_verification(repo, base, out_a, 'VER-swap-receipt')
out_b = run_command(repo, [sys.executable, '-c', "print('other')"], base,
                    executed_by='pm03-reviewer')
(repo / out_a['path']).write_text(json.dumps(out_b['receipt'], ensure_ascii=False,
                                             indent=2), encoding='utf-8')
run_case('swap the receipt under a signed verification', 'reject', repo, rec)

repo, base, out = build('move-attestation')


def move_attestation(repo, out):
    rec_a = attach_attestation(repo, out, name='ATT-A')
    repo_b, base_b = make_repo('move-attestation-b')
    out_b = run_command(repo_b, [sys.executable, '-c', "print('b')"], base_b,
                        executed_by='pm03-reviewer')
    rec_b = attach_attestation(repo_b, out_b, name='ATT-B')
    (repo / out['receipt']['execution_attestation_path']).write_text(
        json.dumps(rec_b, ensure_ascii=False, indent=2), encoding='utf-8')
    return rec_a


move_attestation(repo, out)
rec = signed_verification(repo, base, out, 'VER-move-attestation')
run_case('move another receipt\'s attestation onto this receipt', 'reject', repo, rec)

repo, base, out = build('provenance-edit', attestation='signed')


def edit_provenance(repo, out):
    out['receipt']['execution_provenance'] = {
        'kind': 'local_untrusted', 'trusted': True, 'reason': 'edited after signing'}
    rewrite_receipt(repo, out)


edit_provenance(repo, out)
rec = signed_verification(repo, base, out, 'VER-provenance-edit')
run_case('edit provenance and recompute receipt content hash', 'reject', repo, rec)

repo, base, out = build('tamper-isolation', attestation='tamper-isolation')
rec = signed_verification(repo, base, out, 'VER-tamper-isolation')
run_case('tamper attestation.isolation.uid after signing', 'reject', repo, rec)

repo, base, out = build('tamper-receipt-sha', attestation='tamper-receipt-sha')
rec = signed_verification(repo, base, out, 'VER-tamper-receipt-sha')
run_case('tamper attestation.receipt_sha256 after signing', 'reject', repo, rec)

repo, base, out = build('wrong-key-attestation', attestation='wrong-key')
rec = signed_verification(repo, base, out, 'VER-wrong-key-attestation')
run_case('attestation signed by a non-anchor key', 'reject', repo, rec)

repo, base, out = build('omit-snapshot', attestation='signed-omit-snapshot')
rec = signed_verification(repo, base, out, 'VER-omit-snapshot')
run_case('signed attestation missing snapshot_id', 'reject', repo, rec)

repo, base, out = build('sha256-mismatch', attestation='sha256-mismatch')
rec = signed_verification(repo, base, out, 'VER-sha256-mismatch')
run_case('receipt execution_attestation_sha256 mismatch', 'reject', repo, rec)

repo, base, out = build('missing-attestation-file', attestation='missing-file')
rec = signed_verification(repo, base, out, 'VER-missing-attestation-file')
run_case('receipt points at a missing attestation file', 'reject', repo, rec)

repo, base, out = build('outside-meta', attestation='outside-meta')
rec = signed_verification(repo, base, out, 'VER-outside-meta')
run_case('attestation path outside .project-memory', 'reject', repo, rec)

repo, base, out = build('change-commit', attestation='signed')
rec = signed_verification(repo, base, out, 'VER-change-commit')
run('git', '-C', str(repo), 'commit', '--allow-empty', '-qm', 'second')
second = git_sha(repo)
out['receipt']['commit_sha'] = second
rewrite_receipt(repo, out)
run_case('change the receipt commit after attestation', 'reject', repo, rec)

repo, base, out = build('claimed-trusted-with-broken-attestation',
                        attestation='tamper-isolation')
out['receipt']['execution_provenance'] = {'kind': 'local_untrusted', 'trusted': True}
rewrite_receipt(repo, out)
rec = signed_verification(repo, base, out, 'VER-claimed-trusted-broken-attestation')
run_case('claimed trusted=true with a broken signed attestation', 'reject', repo, rec)

# ---------------------------------------------------------------- anchor protection
authority.load_anchor = REAL_LOAD_ANCHOR
agent_anchor = WORK / 'agent-owned-anchor.json'
agent_anchor.write_text(json.dumps(ANCHOR), encoding='utf-8')
os.chmod(agent_anchor, 0o666)
old_env = os.environ.get('PROJECT_MEMORY_TRUST_ANCHOR')
os.environ['PROJECT_MEMORY_TRUST_ANCHOR'] = str(agent_anchor)
repo, base, out = build('agent-owned-anchor', attestation='signed')
rec = signed_verification(repo, base, out, 'VER-agent-owned-anchor')
evidence = {'kind': 'verification', 'ref': rec['verification_id']}
ok, reason, trust = _verification_ok(repo, evidence, 'G-1', 'C1')
CASES.append({'name': 'agent-owned anchor (env override) must not authenticate',
              'expected': 'reject', 'ok': ok, 'trust': trust, 'reason': reason,
              'pass': (not ok) and trust == 'untrusted'})
if old_env is None:
    os.environ.pop('PROJECT_MEMORY_TRUST_ANCHOR', None)
else:
    os.environ['PROJECT_MEMORY_TRUST_ANCHOR'] = old_env
authority.load_anchor = fake_load_anchor

# ---------------------------------------------------------------- B1 regression
payload = authority.verification_payload({'kind': 'verification_record', 'x': 1})
body = work = WORK / 'b1-payload.bin'
body.write_bytes(payload)
sig_file = WORK / 'b1-payload.sig'
run(OPENSSL, 'dgst', '-sha256', '-sign', str(KEY), '-out', str(sig_file), str(body))
sig_b64 = base64.b64encode(sig_file.read_bytes()).decode('ascii')
before = authority._verify_signature(ANCHOR, payload, sig_b64, 'rsa-sha256')
fakebin = WORK / 'fakebin'
fakebin.mkdir(exist_ok=True)
for name, body_text in (('openssl', '#!/bin/sh\nexit 0\n'),
                        ('openssl-ok', '#!/bin/sh\necho "Verified OK"\nexit 0\n')):
    (fakebin / name).write_text(body_text, encoding='utf-8')
    os.chmod(fakebin / name, 0o755)
old_path = os.environ.get('PATH', '')
old_osl = os.environ.get('PROJECT_MEMORY_OPENSSL')
os.environ['PATH'] = str(fakebin) + os.pathsep + old_path
os.environ['PROJECT_MEMORY_OPENSSL'] = str(fakebin / 'openssl')
after = authority._verify_signature(ANCHOR, payload, sig_b64, 'rsa-sha256')
tampered = authority._verify_signature(ANCHOR, payload + b' ', sig_b64, 'rsa-sha256')
os.environ['PATH'] = old_path
if old_osl is None:
    os.environ.pop('PROJECT_MEMORY_OPENSSL', None)
else:
    os.environ['PROJECT_MEMORY_OPENSSL'] = old_osl
CASES.append({
    'name': 'B1: PATH/PROJECT_MEMORY_OPENSSL cannot change the in-process verifier',
    'expected': 'valid accepted, invalid rejected',
    'valid_before': before, 'valid_after_path_substitution': after,
    'tampered_rejected': (not tampered[0]),
    'pass': before[0] and after[0] and not tampered[0]})

summary = {
    'candidate': str(CODE), 'anchor': 'temporary reviewer RSA key (patched load_anchor)',
    'anchor_a_e2e': 'NOT VERIFIED',
    'cases': CASES,
    'total': len(CASES),
    'passed': sum(1 for c in CASES if c.get('pass')),
    'failed': [c['name'] for c in CASES if not c.get('pass')],
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

def pick(*needles):
    return [c for c in CASES if any(n in c['name'].lower() for n in needles)]

for name, cases in (
        ('forged_untrusted.json', pick('handwritten', 'local untrusted')),
        ('forged_claimed_trusted.json', pick('trusted=true', 'self-written')),
        ('self_written_attestation.json',
         pick('self-written', 'forged envelope', 'non-anchor key', 'tamper',
              'missing snapshot', 'outside .project-memory', 'missing attestation',
              'sha256 mismatch')),
        ('exception_cases.json', pick('exception'))):
    (OUT.parent / name).write_text(
        json.dumps({'anchor_a_e2e': 'NOT VERIFIED', 'cases': cases},
                   ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'total': summary['total'], 'passed': summary['passed'],
                  'failed': summary['failed']}, ensure_ascii=False, indent=2))
for c in CASES:
    print(f"{'PASS' if c.get('pass') else 'FAIL'} | {c['name']} | "
          f"ok={c.get('ok')} trust={c.get('trust')} eval={c.get('evaluate_satisfied')}")
