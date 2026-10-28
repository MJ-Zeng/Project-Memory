"""B2: a valid verification signature must not wrap a forged execution receipt.

Content integrity (``receipt_integrity_valid``) only proves a receipt is
internally consistent with its snapshot, log and commit.  It does not prove the
execution happened under a protected launcher.  These tests pin the new gate:

* a handwritten receipt, even with a valid verification signature, is rejected;
* a receipt that merely claims ``execution_provenance.trusted=true`` is rejected;
* a signed execution attestation (or a signed human exception) is required;
* swapping the receipt, editing provenance, changing the commit or recomputing
  the receipt hash all fail.

The tests use a test-time RSA key and patch ``authority.load_anchor`` so the
cryptographic path is exercised without production keys.  Production code is
not relaxed; without a protected anchor every execution record stays untrusted.
"""
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project_memory import authority, execution, trusted_exec
from project_memory.common import PMError, git_sha
from project_memory.coordination import (_verification_ok, add_goal_evidence,
                                         create_goal, evaluate_goal, finish_run,
                                         load_goal, start_run, verify_run)
from project_memory.execution import run_command, verify_receipt

CRITERION = '模块通过测试'


class B2ExecutionProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openssl = shutil.which('openssl')
        if not cls.openssl:
            raise unittest.SkipTest('找不到 openssl；B2 签名测试需要测试期签名者')
        cls.keydir = tempfile.TemporaryDirectory()
        work = Path(cls.keydir.name)
        cls.key = work / 'test-key.pem'
        public = work / 'test-key.pub.pem'
        subprocess.run([cls.openssl, 'genpkey', '-algorithm', 'RSA',
                        '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(cls.key)],
                       check=True, capture_output=True)
        subprocess.run([cls.openssl, 'pkey', '-in', str(cls.key), '-pubout',
                        '-out', str(public)], check=True, capture_output=True)
        cls.anchor = {
            'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
            'anchor_id': 'b2-test-anchor', 'issuer': 'b2-test-signer',
            'algorithm': 'rsa-sha256',
            'public_key_pem': public.read_text(encoding='utf-8'),
        }

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'b2@example.invalid')
        self.git('config', 'user.name', 'B2')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_auth.py').write_text(
            'def test_ok():\n    assert True\n', encoding='utf-8')
        self.git('add', 'README.md', 'tests/test_auth.py')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)
        patcher = mock.patch('project_memory.authority.load_anchor',
                             return_value=(dict(self.anchor), 'ok'))
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------ fixtures

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def sign(self, record, payload_builder, name):
        payload = payload_builder(record)
        work = Path(self.tmp.name)
        payload_file = work / f'{name}.payload'
        signature_file = work / f'{name}.sig'
        payload_file.write_bytes(payload)
        subprocess.run([self.openssl, 'dgst', '-sha256', '-sign', str(self.key),
                        '-out', str(signature_file), str(payload_file)],
                       check=True, capture_output=True)
        record['authority'] = {
            'status': 'trusted', 'anchor_id': self.anchor['anchor_id'],
            'issuer': self.anchor['issuer'], 'algorithm': 'rsa-sha256',
            'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'signature_b64': base64.b64encode(signature_file.read_bytes()).decode('ascii'),
        }
        return record

    def make_receipt(self):
        return run_command(
            self.repo, [sys.executable, '-c',
                        "import sys; print('1 passed'); sys.exit(0)"],
            self.base, executed_by='test-harness')

    def _rewrite_receipt(self, out):
        path = self.repo / out['path']
        out['receipt']['content_sha256'] = execution._canonical_receipt_digest(out['receipt'])
        path.write_text(json.dumps(out['receipt'], ensure_ascii=False, indent=2),
                        encoding='utf-8')

    def attach_signed_attestation(self, out, name='ATT-1'):
        ref = f'.project-memory/attestations/{name}.json'
        out['receipt']['execution_attestation_path'] = ref
        self._rewrite_receipt(out)
        receipt = out['receipt']
        record = {
            'schema_version': '1.0', 'kind': 'execution_attestation',
            'attestation_id': name,
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
        self.sign(record, authority.execution_record_payload, name)
        path = self.repo / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return out, record

    def attach_signed_exception(self, out, *, criterion='C1', goal='G-1',
                                signed=True, name='EXC-1'):
        ref = f'.project-memory/exceptions/{name}.json'
        out['receipt']['execution_exception_path'] = ref
        self._rewrite_receipt(out)
        receipt = out['receipt']
        record = {
            'schema_version': '1.0', 'kind': 'execution_exception',
            'exception_id': name, 'goal_id': goal, 'criterion_ids': [criterion],
            'receipt_id': receipt['receipt_id'],
            'receipt_sha256': receipt['content_sha256'],
            'commit_sha': receipt['commit_sha'],
            'reason': '该本地执行无法 attestation，由人类为本次试点承担来源责任',
            'scope': 'one-off B2 fixture execution',
            'issued_by': 'human@example.invalid',
            'created_at': '2026-01-01T00:00:00Z',
        }
        if signed:
            self.sign(record, authority.execution_record_payload, name)
        else:
            record['authority'] = authority.untrusted_envelope('agent wrote this exception')
        path = self.repo / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return out, record

    def mapping(self, out, goal='G-1', task='325', criterion='C1'):
        receipt = out['receipt']
        return {'criteria': [{
            'criterion_id': criterion, 'goal_id': goal, 'task_id': task,
            'criterion_description': CRITERION, 'target_repository': str(self.repo),
            'target_commit_sha': self.base, 'evidence_id': 'EV-1',
            'evidence_source': 'test', 'evidence_command': receipt['command'],
            'evidence_log': out['log'], 'evidence_exit_code': receipt['exit_code'],
            'evidence_receipt': out['path'], 'execution_status': 'passed',
            'coverage_claim': '覆盖对应标准', 'coverage_review_status': 'confirmed',
            'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}

    def prepare_verification(self, out, goal='G-1', task='325', criterion='C1'):
        create_goal(self.repo, goal, goal + ' title', 'background', 'outcome',
                    'owner', [CRITERION])
        start_run(self.repo, goal, task, 'run-target', 'dev-agent', 'qodercn',
                  'auto', base_sha=self.base, role='executor')
        finish_run(self.repo, task, 'run-target', ['implemented'], ['verify'],
                   head_sha=self.base,
                   tests=[{'command': out['receipt']['command'],
                           'exit_code': 0, 'log': out['log']}])
        start_run(self.repo, goal, task, 'run-verifier', 'verifier-agent',
                  'qodercn', 'verifier-model', base_sha=self.base, role='verifier')
        result = verify_run(self.repo, 'run-target', 'run-verifier', 'acceptance',
                            'pass', 'locally_observed', test_receipt=out['path'],
                            criterion_evidence=self.mapping(
                                out, goal=goal, task=task, criterion=criterion))
        self.assertIsNotNone(result['verification'])
        return result['verification']

    def signed_verified(self, record, *, goal_sha=None):
        record = json.loads(json.dumps(record))
        record['status'] = 'VERIFIED'
        record['verified'] = True
        record['mapping_status'] = 'complete'
        for entry in record.get('criterion_evidence', []):
            entry['evidence_matched'] = True
        if goal_sha is not None:
            record['goal_criteria_sha256'] = goal_sha
        record.pop('authority', None)
        self.sign(record, authority.verification_payload, record['verification_id'])
        path = self.repo / '.project-memory/verifications' / str(record['task']) \
            / f"{record['verification_id']}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return record

    def assert_rejected(self, record, trust='untrusted'):
        evidence = {'kind': 'verification', 'ref': record['verification_id']}
        ok, reason, actual = _verification_ok(self.repo, evidence, record['goal_id'], 'C1')
        self.assertFalse(ok, reason)
        self.assertEqual(actual, trust, reason)
        with self.assertRaises(PMError):
            add_goal_evidence(self.repo, record['goal_id'], 'C1', 'verification',
                              record['verification_id'])
        self.assertFalse(evaluate_goal(self.repo, record['goal_id'])['satisfied'])
        return reason

    # ------------------------------------------------------------ AC-1 / AC-4

    def test_handwritten_untrusted_receipt_with_valid_signature_is_rejected(self):
        out = self.make_receipt()
        record = self.signed_verified(self.prepare_verification(out))
        self.assertFalse(out['receipt']['execution_provenance']['trusted'])
        reason = self.assert_rejected(record)
        self.assertIn('执行来源不可信', reason)
        self.assertIn('人类例外缺失', reason)

    def test_local_untrusted_receipt_is_rejected_by_default(self):
        out = self.make_receipt()
        self.assertEqual(out['receipt']['trust'], 'local_untrusted')
        checked = verify_receipt(self.repo, out['path'])
        self.assertTrue(checked['valid'])
        self.assertEqual(checked['provenance']['kind'], 'local_untrusted')
        self.assertFalse(checked['provenance']['trusted'])
        reason = self.assert_rejected(
            self.signed_verified(self.prepare_verification(out)))
        self.assertIn('人类例外缺失', reason)

    # ------------------------------------------------------------ AC-2

    def test_claimed_trusted_boolean_without_attestation_is_rejected(self):
        out = self.make_receipt()
        out['receipt']['execution_provenance'] = {
            'kind': 'local_untrusted', 'trusted': True,
            'reason': 'agent wrote trusted=true by hand',
        }
        self._rewrite_receipt(out)
        checked = verify_receipt(self.repo, out['path'])
        self.assertTrue(checked['valid'], checked['problems'])
        # The parser does not believe the boolean, but the test still matters:
        # the forged field must not be what the gate consults.
        self.assertFalse(checked['provenance']['trusted'])
        reason = self.assert_rejected(
            self.signed_verified(self.prepare_verification(out)))
        self.assertIn('人类例外缺失', reason)

    def test_self_written_launcher_attestation_is_not_execution_proof(self):
        out = self.make_receipt()
        receipt = out['receipt']
        attest_ref = f'.project-memory/attest/{receipt["receipt_id"]}/attest.json'
        receipt['isolation'] = {'mode': trusted_exec.MODE,
                                'snapshot_wsl': '/tmp/snapshot'}
        receipt['execution_provenance'] = {
            'kind': 'trusted_launcher', 'launcher': 'project_memory.trusted_exec',
            'attested': True, 'trusted': True,
        }
        receipt['attestation_path'] = attest_ref
        self._rewrite_receipt(out)
        launcher_attestation = {
            'ok': True, 'mode': trusted_exec.MODE,
            'receipt_id': receipt['receipt_id'], 'snapshot': '/tmp/snapshot',
            'command_sha256': hashlib.sha256(
                receipt['command'].encode('utf-8')).hexdigest(),
        }
        path = self.repo / attest_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(launcher_attestation), encoding='utf-8')
        checked = verify_receipt(self.repo, out['path'])
        self.assertTrue(checked['valid'], checked['problems'])
        self.assertEqual(checked['provenance']['kind'], 'trusted_launcher_attested')
        self.assertFalse(checked['provenance']['trusted'])
        reason = self.assert_rejected(
            self.signed_verified(self.prepare_verification(out)))
        self.assertIn('人类例外缺失', reason)

    # ------------------------------------------------------------ AC-3

    def test_signed_attestation_is_accepted_and_goal_evidence_succeeds(self):
        out, _ = self.attach_signed_attestation(self.make_receipt())
        record = self.signed_verified(self.prepare_verification(out))
        evidence = {'kind': 'verification', 'ref': record['verification_id']}
        ok, reason, trust = _verification_ok(self.repo, evidence, 'G-1', 'C1')
        self.assertTrue(ok, reason)
        self.assertEqual(trust, 'evidence_matched')
        added = add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                                  record['verification_id'])
        self.assertEqual(added['evidence']['kind'], 'verification')

    def test_signed_attestation_satisfies_bound_criterion(self):
        out, _ = self.attach_signed_attestation(self.make_receipt())
        record = self.prepare_verification(out)
        goal_path = self.repo / '.project-memory/goals/G-1.json'
        goal = json.loads(goal_path.read_text(encoding='utf-8'))
        goal['success_criteria'][0].setdefault('evidence', []).append(
            {'kind': 'verification', 'ref': record['verification_id'], 'note': ''})
        goal_path.write_text(json.dumps(goal, ensure_ascii=False, indent=2),
                             encoding='utf-8')
        goal_sha = authority.canonical_digest(
            load_goal(self.repo, 'G-1')['success_criteria'])
        self.signed_verified(record, goal_sha=goal_sha)
        evaluation = evaluate_goal(self.repo, 'G-1')
        self.assertTrue(evaluation['satisfied'])
        self.assertEqual(evaluation['recommendation'], 'achieved')

    # ------------------------------------------------------------ AC-4 (exception)

    def test_signed_human_exception_allows_local_execution(self):
        out, _ = self.attach_signed_exception(self.make_receipt())
        record = self.signed_verified(self.prepare_verification(out))
        evidence = {'kind': 'verification', 'ref': record['verification_id']}
        ok, reason, trust = _verification_ok(self.repo, evidence, 'G-1', 'C1')
        self.assertTrue(ok, reason)
        self.assertEqual(trust, 'evidence_matched')

    def test_unsigned_exception_is_rejected(self):
        out, _ = self.attach_signed_exception(self.make_receipt(), signed=False)
        reason = self.assert_rejected(
            self.signed_verified(self.prepare_verification(out)))
        self.assertIn('人类例外缺失', reason)
        self.assertIn('签名未通过', reason)

    def test_exception_out_of_scope_is_rejected(self):
        out, _ = self.attach_signed_exception(self.make_receipt(), criterion='C9')
        reason = self.assert_rejected(
            self.signed_verified(self.prepare_verification(out)))
        self.assertIn('范围不覆盖', reason)

    # ------------------------------------------------------------ AC-5

    def test_swapping_the_receipt_is_rejected(self):
        out, _ = self.attach_signed_attestation(self.make_receipt())
        record = self.signed_verified(self.prepare_verification(out))
        other = self.make_receipt()
        (self.repo / out['path']).write_text(
            json.dumps(other['receipt'], ensure_ascii=False, indent=2), encoding='utf-8')
        reason = self.assert_rejected(record, trust='invalid')
        self.assertTrue('内容不完整' in reason or '不一致' in reason, reason)

    def test_provenance_edit_with_recomputed_hash_is_rejected(self):
        out, _ = self.attach_signed_attestation(self.make_receipt())
        record = self.signed_verified(self.prepare_verification(out))
        out['receipt']['execution_provenance'] = {'kind': 'local_untrusted',
                                                  'trusted': True, 'reason': 'edited'}
        self._rewrite_receipt(out)
        reason = self.assert_rejected(record)
        self.assertIn('不一致', reason)

    def test_attestation_commit_edit_breaks_signature(self):
        out, attestation = self.attach_signed_attestation(self.make_receipt())
        record = self.signed_verified(self.prepare_verification(out))
        attestation['commit_sha'] = '1' * 40
        path = self.repo / out['receipt']['execution_attestation_path']
        path.write_text(json.dumps(attestation, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        reason = self.assert_rejected(record)
        self.assertIn('签名未通过', reason)

    def test_attestation_from_another_receipt_is_rejected(self):
        out_a, _ = self.attach_signed_attestation(self.make_receipt(), name='ATT-A')
        record = self.signed_verified(self.prepare_verification(out_a))
        out_b = self.make_receipt()
        # Move B's signed attestation onto A: its bindings name B, not A.
        out_b, attestation_b = self.attach_signed_attestation(out_b, name='ATT-B')
        (self.repo / out_a['receipt']['execution_attestation_path']).write_text(
            json.dumps(attestation_b, ensure_ascii=False, indent=2), encoding='utf-8')
        reason = self.assert_rejected(record)
        self.assertIn('不一致', reason)


if __name__ == '__main__':
    unittest.main()
