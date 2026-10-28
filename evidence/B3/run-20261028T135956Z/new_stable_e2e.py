"""B3 new-record CLI E2E with an ephemeral TEST anchor.

This script does NOT read or use /etc/pm-rc3-review/key-a.pem.  It generates a
throwaway RSA key and anchor under /tmp/b3-new-stable and signs the fixture with
that key, exactly like the unit-test path sanctioned by ADR-0003 §6.  The
result proves the new stable-digest flow end to end; it is not an anchor-a
signature and must not be described as one.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))

from project_memory import authority, execution, trusted_exec  # noqa: E402
from project_memory.common import git_sha  # noqa: E402
from project_memory.coordination import (add_goal_evidence, create_goal,  # noqa: E402
                                         evaluate_goal, finish_run, start_run,
                                         verify_run)

CRITERION = '模块通过测试'
root = Path('/tmp/b3-new-stable')
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)
repo = root / 'repo'
repo.mkdir()
key = root / 'test-key.pem'
pub = root / 'test-key.pub.pem'
anchor_path = root / 'test-anchor.json'
subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
subprocess.run(['git', '-C', str(repo), 'config', 'user.email', 'b3@example.invalid'], check=True)
subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'B3'], check=True)
(repo / 'README.md').write_text('hello\n', encoding='utf-8')
(repo / 'tests').mkdir()
(repo / 'tests/test_auth.py').write_text('def test_ok():\n    assert True\n', encoding='utf-8')
subprocess.run(['git', '-C', str(repo), 'add', 'README.md', 'tests/test_auth.py'], check=True)
subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'base'], check=True)
base = git_sha(repo)
openssl = shutil.which('openssl')
if not openssl:
    raise SystemExit('openssl missing')
subprocess.run([openssl, 'genpkey', '-algorithm', 'RSA',
                '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(key)],
               check=True, capture_output=True)
subprocess.run([openssl, 'pkey', '-in', str(key), '-pubout', '-out', str(pub)],
               check=True, capture_output=True)
anchor = {
    'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
    'anchor_id': 'b3-ephemeral-test-anchor', 'issuer': 'b3-ephemeral-test-signer',
    'algorithm': 'rsa-sha256', 'public_key_pem': pub.read_text(encoding='utf-8'),
}
anchor_path.write_text(json.dumps(anchor, ensure_ascii=False, indent=2), encoding='utf-8')
os.environ['PROJECT_MEMORY_TRUST_ANCHOR'] = str(anchor_path)


def sign(record, payload_builder, name):
    payload = payload_builder(record)
    payload_file = root / f'{name}.payload'
    signature_file = root / f'{name}.sig'
    payload_file.write_bytes(payload)
    subprocess.run([openssl, 'dgst', '-sha256', '-sign', str(key),
                    '-out', str(signature_file), str(payload_file)],
                   check=True, capture_output=True)
    record['authority'] = {
        'status': 'trusted', 'anchor_id': anchor['anchor_id'],
        'issuer': anchor['issuer'], 'algorithm': 'rsa-sha256',
        'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
        'signature_b64': __import__('base64').b64encode(
            signature_file.read_bytes()).decode('ascii'),
    }
    return record


out = execution.run_command(
    repo, [sys.executable, '-c', "import sys; print('1 passed'); sys.exit(0)"],
    base, executed_by='b3-test-harness')
receipt = out['receipt']
att_ref = '.project-memory/attestations/ATT-B3.json'
receipt['execution_attestation_path'] = att_ref
receipt['content_sha256'] = execution._canonical_receipt_digest(receipt)
(repo / out['path']).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
attestation = {
    'schema_version': '1.0', 'kind': 'execution_attestation',
    'attestation_id': 'ATT-B3',
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
    'created_at': '2026-01-01T00:00:00Z',
}
sign(attestation, authority.execution_record_payload, 'ATT-B3')
att_path = repo / att_ref
att_path.parent.mkdir(parents=True, exist_ok=True)
att_path.write_text(json.dumps(attestation, ensure_ascii=False, indent=2), encoding='utf-8')

create_goal(repo, 'G-B3', 'B3 new record', 'background', 'outcome', 'owner', [CRITERION])
start_run(repo, 'G-B3', '325', 'run-target', 'dev-agent', 'qodercn', 'auto',
          base_sha=base, role='executor')
finish_run(repo, '325', 'run-target', ['implemented'], ['verify'], head_sha=base,
           tests=[{'command': receipt['command'], 'exit_code': 0, 'log': out['log']}])
start_run(repo, 'G-B3', '325', 'run-verifier', 'verifier-agent', 'qodercn',
          'verifier-model', base_sha=base, role='verifier')
mapping = {'criteria': [{
    'criterion_id': 'C1', 'goal_id': 'G-B3', 'task_id': '325',
    'criterion_description': CRITERION, 'target_repository': str(repo),
    'target_commit_sha': base, 'evidence_id': 'EV-1', 'evidence_source': 'test',
    'evidence_command': receipt['command'], 'evidence_log': out['log'],
    'evidence_exit_code': 0, 'evidence_receipt': out['path'],
    'execution_status': 'passed', 'coverage_claim': '覆盖对应标准',
    'coverage_review_status': 'confirmed', 'independent_verifier': 'verifier-agent',
    'verification_result': 'pass'}]}
result = verify_run(repo, 'run-target', 'run-verifier', 'acceptance', 'pass',
                    'locally_observed', test_receipt=out['path'],
                    criterion_evidence=mapping)
record = result['verification']
record['status'] = 'VERIFIED'
record['verified'] = True
record['mapping_status'] = 'complete'
for entry in record['criterion_evidence']:
    entry['evidence_matched'] = True
record.pop('authority', None)
sign(record, authority.verification_payload, record['verification_id'])
record_path = repo / '.project-memory/verifications/325' / f"{record['verification_id']}.json"
record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')

env = dict(os.environ, PYTHONPATH=str(WORKSPACE),
           PROJECT_MEMORY_TRUST_ANCHOR=str(anchor_path))
before = hashlib.sha256(record_path.read_bytes()).hexdigest()
evidence_cli = subprocess.run(
    [sys.executable, '-m', 'project_memory', 'goal', 'evidence', '--repo', '.',
     '--id', 'G-B3', '--criterion', 'C1', '--kind', 'verification',
     '--ref', record['verification_id']],
    cwd=repo, env=env, capture_output=True, text=True, encoding='utf-8')
after = hashlib.sha256(record_path.read_bytes()).hexdigest()
evaluate_cli = subprocess.run(
    [sys.executable, '-m', 'project_memory', 'goal', 'evaluate', '--repo', '.',
     '--id', 'G-B3'],
    cwd=repo, env=env, capture_output=True, text=True, encoding='utf-8')
evaluation = json.loads(evaluate_cli.stdout)
direct = evaluate_goal(repo, 'G-B3')
summary = {
    'anchor': 'ephemeral-test-anchor (NOT anchor-a)',
    'verification_id': record['verification_id'],
    'goal_criteria_sha256': record['goal_criteria_sha256'],
    'goal_criteria_legacy_sha256': record['goal_criteria_legacy_sha256'],
    'definition_digest_is_not_legacy': record['goal_criteria_sha256'] != record['goal_criteria_legacy_sha256'],
    'record_sha256_before_evidence': before,
    'record_sha256_after_evidence': after,
    'record_bytes_unchanged': before == after,
    'evidence_cli_exit': evidence_cli.returncode,
    'evidence_cli_stderr': evidence_cli.stderr.strip(),
    'evaluate_cli_exit': evaluate_cli.returncode,
    'evaluate_satisfied': evaluation['satisfied'],
    'evaluate_status': evaluation['evaluation_status'],
    'evaluate_recommendation': evaluation['recommendation'],
    'library_evaluate_satisfied': direct['satisfied'],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
(OUT / 'new-stable-e2e.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
