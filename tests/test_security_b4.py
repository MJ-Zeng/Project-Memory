"""B4: the execution audit ledger and Goal status must be verifiable.

These tests pin the B4 contract:

* a hand-edited ``status: achieved`` is never trusted;
* deleting, rewriting or rebuilding the audit JSONL is detected;
* an achieved transition needs a checkpoint signed by the protected anchor;
* an Agent cannot produce a valid checkpoint (no key, no signing code path);
* empty/missing audit fails closed;
* a legitimate transition + audit + signed checkpoint verifies.

The tests use a test-time RSA key and patch ``authority.load_anchor`` so the
cryptographic path runs without production keys.  Production code is not
relaxed: without a protected anchor every checkpoint stays untrusted.
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
from project_memory.common import PMError, git_sha, sha256_file
from project_memory.coordination import (_audit_attempt, add_goal_evidence,
                                         attach_audit_checkpoint, audit_head,
                                         audit_migrate, audit_verify, create_goal,
                                         evaluate_goal, finish_run, goal_show,
                                         load_goal, start_run, transition_goal,
                                         verify_run)
from project_memory.execution import run_command

CRITERION = '模块通过测试'
GOAL = 'G-B4'


class B4IntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openssl = shutil.which('openssl')
        if not cls.openssl:
            raise unittest.SkipTest('找不到 openssl；B4 签名测试需要测试期签名者')
        cls.keydir = tempfile.TemporaryDirectory()
        work = Path(cls.keydir.name)
        cls.key = work / 'test-key.pem'
        cls.public = work / 'test-key.pub.pem'
        subprocess.run([cls.openssl, 'genpkey', '-algorithm', 'RSA',
                        '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(cls.key)],
                       check=True, capture_output=True)
        subprocess.run([cls.openssl, 'pkey', '-in', str(cls.key), '-pubout',
                        '-out', str(cls.public)], check=True, capture_output=True)
        cls.other_key = work / 'other-key.pem'
        subprocess.run([cls.openssl, 'genpkey', '-algorithm', 'RSA',
                        '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(cls.other_key)],
                       check=True, capture_output=True)
        cls.anchor = {
            'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
            'anchor_id': 'b4-test-anchor', 'issuer': 'b4-test-signer',
            'algorithm': 'rsa-sha256',
            'public_key_pem': cls.public.read_text(encoding='utf-8'),
        }

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'b4@example.invalid')
        self.git('config', 'user.name', 'B4')
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
        self.audit_path = self.repo / '.project-memory/audit/verification_attempts.jsonl'

    # ------------------------------------------------------------ helpers

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

    def sign_bytes(self, payload, name, key=None):
        work = Path(self.tmp.name)
        payload_file = work / f'{name}.payload'
        signature_file = work / f'{name}.sig'
        payload_file.write_bytes(payload)
        subprocess.run([self.openssl, 'dgst', '-sha256', '-sign',
                        str(key or self.key), '-out', str(signature_file),
                        str(payload_file)], check=True, capture_output=True)
        return signature_file

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

    def mapping(self, out, goal=GOAL, task='B4', criterion='C1'):
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

    def signed_verified(self, record):
        record = json.loads(json.dumps(record))
        record['status'] = 'VERIFIED'
        record['verified'] = True
        record['mapping_status'] = 'complete'
        for entry in record.get('criterion_evidence', []):
            entry['evidence_matched'] = True
        record.pop('authority', None)
        self.sign(record, authority.verification_payload, record['verification_id'])
        path = self.repo / '.project-memory/verifications' / str(record['task']) \
            / f"{record['verification_id']}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return record

    def prepare_verification(self, out, goal=GOAL, task='B4', criterion='C1'):
        create_goal(self.repo, goal, goal + ' title', 'background', 'outcome',
                    'owner@example.com', [CRITERION])
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

    def verified_goal(self, goal=GOAL, task='B4', criterion='C1'):
        out = self.make_receipt()
        self.attach_signed_attestation(out)
        record = self.signed_verified(
            self.prepare_verification(out, goal=goal, task=task, criterion=criterion))
        add_goal_evidence(self.repo, goal, criterion, 'verification',
                          record['verification_id'])
        self.assertTrue(evaluate_goal(self.repo, goal)['satisfied'])
        return record

    def achieve(self, goal=GOAL):
        self.verified_goal(goal=goal)
        transition_goal(self.repo, goal, 'approved', approved_by='lead@example.com')
        transition_goal(self.repo, goal, 'active')
        transition_goal(self.repo, goal, 'evaluating')
        result = transition_goal(self.repo, goal, 'achieved',
                                 approved_by='lead@example.com')
        self.assertIn('checkpoint_request', result)
        self.assertNotIn('error', result['checkpoint_request'])
        return result

    def attach_checkpoint(self, key=None, name='CKPT'):
        request = self.repo / '.project-memory/audit/head.request.json'
        self.assertTrue(request.is_file())
        signature = self.sign_bytes(request.read_bytes(), name, key=key)
        return attach_audit_checkpoint(self.repo, signature)

    def audit_entries(self):
        return [json.loads(line) for line in
                self.audit_path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def write_entries(self, entries):
        self.audit_path.write_text(
            ''.join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
                    for entry in entries), encoding='utf-8')

    # ------------------------------------------------------------ AC-1

    def test_hand_edited_achieved_is_not_trusted(self):
        out = self.make_receipt()
        self.attach_signed_attestation(out)
        self.signed_verified(self.prepare_verification(out))
        path = self.repo / f'.project-memory/goals/{GOAL}.json'
        goal = json.loads(path.read_text(encoding='utf-8'))
        goal['status'] = 'achieved'
        path.write_text(json.dumps(goal, ensure_ascii=False), encoding='utf-8')

        shown = goal_show(self.repo, GOAL)
        self.assertEqual(shown['raw_status'], 'achieved')
        self.assertNotEqual(shown['effective_status'], 'achieved')
        self.assertIs(shown['status_trusted'], False)
        self.assertIn('status_history_mismatch', shown['status_problems'])
        self.assertIn('checkpoint_missing', shown['status_problems'])

        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertFalse(evaluation['satisfied'])
        self.assertNotEqual(evaluation['effective_status'], 'achieved')
        self.assertFalse(evaluation['recorded_status_consistent'])

    def test_hand_edited_achieved_with_real_evidence_still_untrusted(self):
        # Even when the criteria are genuinely satisfied, a raw status edit is
        # not an achieved transition: no audit transition entry, no checkpoint.
        self.verified_goal()
        path = self.repo / f'.project-memory/goals/{GOAL}.json'
        goal = json.loads(path.read_text(encoding='utf-8'))
        goal['status'] = 'achieved'
        path.write_text(json.dumps(goal, ensure_ascii=False), encoding='utf-8')
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertTrue(evaluation['satisfied'])
        self.assertIs(evaluation['status_trusted'], False)
        self.assertEqual(evaluation['effective_status'], 'achieved_unverified')
        self.assertIn('checkpoint_missing', evaluation['status_problems'])

    # ------------------------------------------------------------ AC-2

    def test_deleted_audit_row_is_detected(self):
        for index in range(3):
            _audit_attempt(self.repo, outcome='recorded', seq_hint=index)
        self.assertEqual(audit_verify(self.repo)['status'], 'valid_unanchored')
        entries = self.audit_entries()
        self.write_entries([entries[0], entries[2]])
        report = audit_verify(self.repo)
        self.assertFalse(report['valid'])
        self.assertIn('audit_chain_verification', report['kind'])
        self.assertTrue(any('seq_mismatch_at:2' == p or 'prev_hash_mismatch_at:2' == p
                            for p in report['problems']), report['problems'])

    # ------------------------------------------------------------ AC-3

    def test_rewritten_audit_row_is_detected(self):
        for index in range(3):
            _audit_attempt(self.repo, outcome='recorded', seq_hint=index)
        entries = self.audit_entries()
        entries[1]['outcome'] = 'verified'
        self.write_entries(entries)
        report = audit_verify(self.repo)
        self.assertFalse(report['valid'])
        self.assertIn('entry_hash_mismatch_at:2', report['problems'])

        # Recompute the edited row's hash but leave the next link untouched.
        entries = self.audit_entries()
        entries[1] = {key: value for key, value in entries[1].items()
                      if key != 'entry_hash'}
        entries[1]['entry_hash'] = authority.canonical_digest(entries[1])
        self.write_entries(entries)
        report = audit_verify(self.repo)
        self.assertFalse(report['valid'])
        self.assertIn('prev_hash_mismatch_at:3', report['problems'])

    # ------------------------------------------------------------ AC-4

    def test_rebuilt_selfconsistent_chain_without_new_checkpoint_is_detected(self):
        self.achieve()
        self.attach_checkpoint()
        self.assertTrue(audit_verify(self.repo)['authoritative'])
        # Rewrite one field and recompute every hash so the chain is internally
        # consistent again.  The signed checkpoint still binds the old head.
        entries = self.audit_entries()
        entries[0]['outcome'] = 'edited'
        previous = '0' * 64
        for index, entry in enumerate(entries, 1):
            entry.pop('entry_hash', None)
            entry['seq'] = index
            entry['prev_hash'] = previous
            entry['entry_hash'] = authority.canonical_digest(entry)
            previous = entry['entry_hash']
        self.write_entries(entries)
        report = audit_verify(self.repo)
        self.assertFalse(report['valid'])
        self.assertIn('checkpoint_chain_mismatch', report['problems'])
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertIs(evaluation['status_trusted'], False)
        self.assertEqual(evaluation['effective_status'], 'achieved_unverified')

    # ------------------------------------------------------------ AC-5

    def test_legitimate_transition_audit_and_checkpoint_verify(self):
        self.achieve()
        result = self.attach_checkpoint()
        self.assertTrue(result['trusted'])
        report = audit_verify(self.repo)
        self.assertEqual(report['status'], 'valid')
        self.assertTrue(report['authoritative'])
        self.assertEqual(report['checkpoint']['goal_id'], GOAL)
        self.assertEqual(report['checkpoint']['status'], 'achieved')
        self.assertEqual(report['head'],
                         report['checkpoint']['chain_head'])
        shown = goal_show(self.repo, GOAL)
        self.assertEqual(shown['effective_status'], 'achieved')
        self.assertIs(shown['status_trusted'], True)
        self.assertEqual(shown['status_problems'], [])
        self.assertEqual(shown['status_authority'], 'anchor_signed_checkpoint')
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertTrue(evaluation['satisfied'])
        self.assertEqual(evaluation['recommendation'], 'achieved')

    def test_prefix_anchor_survives_a_later_audit_append(self):
        self.achieve()
        self.attach_checkpoint()
        _audit_attempt(self.repo, outcome='rejected', reason='later_attempt')
        report = audit_verify(self.repo)
        self.assertTrue(report['valid'])
        self.assertTrue(report['authoritative'])
        self.assertEqual(evaluate_goal(self.repo, GOAL)['effective_status'], 'achieved')

    # ------------------------------------------------------------ AC-6

    def test_agent_cannot_attach_a_checkpoint(self):
        self.achieve()
        head = self.repo / '.project-memory/audit/head.json'
        # No signature file at all.
        with self.assertRaises(PMError):
            attach_audit_checkpoint(self.repo, self.repo / 'missing.sig')
        # Signed by a key the anchor does not trust.
        with self.assertRaises(PMError) as ctx:
            self.attach_checkpoint(key=self.other_key, name='WRONG')
        self.assertIn('签名无效', str(ctx.exception))
        self.assertFalse(head.exists())
        self.assertIs(evaluate_goal(self.repo, GOAL)['status_trusted'], False)

    def test_unconfigured_anchor_rejects_checkpoint(self):
        self.achieve()
        request = self.repo / '.project-memory/audit/head.request.json'
        signature = self.sign_bytes(request.read_bytes(), 'NOANCHOR')
        with mock.patch('project_memory.authority.load_anchor',
                        return_value=(None, '未配置受保护的信任锚')):
            with self.assertRaises(PMError) as ctx:
                attach_audit_checkpoint(self.repo, signature)
        self.assertIn('无法验证 checkpoint', str(ctx.exception))
        self.assertFalse((self.repo / '.project-memory/audit/head.json').exists())

    # ------------------------------------------------------------ AC-7

    def test_empty_and_missing_audit_fail_closed(self):
        self.achieve()
        self.attach_checkpoint()
        self.assertEqual(audit_verify(self.repo)['status'], 'valid')
        # Empty file.
        self.audit_path.write_text('', encoding='utf-8')
        report = audit_verify(self.repo)
        self.assertFalse(report['valid'])
        self.assertIn('audit_empty', report['problems'])
        self.assertIn('audit_empty', evaluate_goal(self.repo, GOAL)['status_problems'])
        # Missing directory.
        shutil.rmtree(self.repo / '.project-memory/audit')
        report = audit_verify(self.repo)
        self.assertFalse(report['valid'])
        self.assertIn('audit_missing', report['problems'])
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertIs(evaluation['status_trusted'], False)
        self.assertEqual(evaluation['effective_status'], 'achieved_unverified')

    def test_audit_head_reports_missing_ledger(self):
        report = audit_head(self.repo)
        self.assertEqual(report['status'], 'invalid')
        self.assertIn('audit_missing', report['problems'])

    # ------------------------------------------------------------ migration

    def test_legacy_audit_requires_migration(self):
        self.audit_path.parent.mkdir(parents=True)
        legacy = [
            {'schema_version': '1.2', 'kind': 'verification_attempt',
             'timestamp': '2026-01-01T00:00:00Z', 'outcome': 'recorded', 'n': 0},
            {'schema_version': '1.2', 'kind': 'verification_attempt',
             'timestamp': '2026-01-01T00:00:01Z', 'outcome': 'rejected', 'n': 1},
        ]
        self.write_entries(legacy)
        report = audit_verify(self.repo)
        self.assertFalse(report['valid'])
        self.assertIn('legacy_entries_without_chain', report['problems'])
        migrated = audit_migrate(self.repo)
        self.assertTrue(migrated['changed'])
        self.assertEqual(migrated['entries'], 2)
        self.assertTrue((self.repo / '.project-memory/audit/migration.json').is_file())
        self.assertTrue(
            (self.repo / '.project-memory/audit/verification_attempts.pre-chain.jsonl').is_file())
        report = audit_verify(self.repo)
        self.assertEqual(report['status'], 'valid_unanchored')
        self.assertFalse(report['authoritative'])
        # Appending after migration keeps the chain valid.
        _audit_attempt(self.repo, outcome='recorded', reason='after_migration')
        self.assertEqual(audit_verify(self.repo)['status'], 'valid_unanchored')

    # ------------------------------------------------------------ checkpoint binding

    def test_checkpoint_for_another_goal_is_not_trusted(self):
        other = 'G-OTHER'
        self.verified_goal(goal=other, task='B4B')
        transition_goal(self.repo, other, 'approved', approved_by='lead@example.com')
        transition_goal(self.repo, other, 'active')
        transition_goal(self.repo, other, 'evaluating')
        transition_goal(self.repo, other, 'achieved', approved_by='lead@example.com')
        self.attach_checkpoint(name='OTHER')
        # The signed checkpoint names G-OTHER; G-B4 has no achieved claim.
        path = self.repo / f'.project-memory/goals/{GOAL}.json'
        create_goal(self.repo, GOAL, 't', '', 'o', 'owner@example.com', [CRITERION])
        goal = json.loads(path.read_text(encoding='utf-8'))
        goal['status'] = 'achieved'
        path.write_text(json.dumps(goal, ensure_ascii=False), encoding='utf-8')
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertIs(evaluation['status_trusted'], False)
        self.assertIn('checkpoint_goal_mismatch', evaluation['status_problems'])

    def test_tampered_checkpoint_signature_is_rejected(self):
        self.achieve()
        self.attach_checkpoint()
        head = self.repo / '.project-memory/audit/head.json'
        record = json.loads(head.read_text(encoding='utf-8'))
        record['at'] = '2026-01-01T00:00:00Z'
        head.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        report = audit_verify(self.repo)
        self.assertFalse(report['authoritative'])
        self.assertIn('checkpoint_untrusted', report['problems'])


if __name__ == '__main__':
    unittest.main()
