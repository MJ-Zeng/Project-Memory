"""B3: appending evidence must not invalidate a signed verification.

The verification record binds the *definition* of the criteria (id, statement,
required).  Evidence is append-only observation and is deliberately excluded
from that binding.  Legacy records that stored a digest over the whole
``success_criteria`` list remain usable while definitions are unchanged,
including after evidence was appended to a signature over ``evidence=[]``.

As in B2, these tests use a test-time RSA key and patch
``authority.load_anchor``.  Production code is not relaxed.
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
from project_memory.coordination import (_criteria_definition_digest,
                                         _verification_current, _verification_ok,
                                         add_goal_evidence, create_goal,
                                         evaluate_goal, finish_run, load_goal,
                                         start_run, verify_run)

CRITERION = '模块通过测试'


class B3CriteriaDigestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openssl = shutil.which('openssl')
        if not cls.openssl:
            raise unittest.SkipTest('找不到 openssl；B3 签名测试需要测试期签名者')
        cls.keydir = tempfile.TemporaryDirectory()
        work = Path(cls.keydir.name)
        cls.key = work / 'b3-test-key.pem'
        public = work / 'b3-test-key.pub.pem'
        subprocess.run([cls.openssl, 'genpkey', '-algorithm', 'RSA',
                        '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(cls.key)],
                       check=True, capture_output=True)
        subprocess.run([cls.openssl, 'pkey', '-in', str(cls.key), '-pubout',
                        '-out', str(public)], check=True, capture_output=True)
        cls.anchor = {
            'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
            'anchor_id': 'b3-test-anchor', 'issuer': 'b3-test-signer',
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
        self.git('config', 'user.email', 'b3@example.invalid')
        self.git('config', 'user.name', 'B3')
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
        return execution.run_command(
            self.repo, [sys.executable, '-c',
                        "import sys; print('1 passed'); sys.exit(0)"],
            self.base, executed_by='test-harness')

    def _rewrite_receipt(self, out):
        path = self.repo / out['path']
        out['receipt']['content_sha256'] = execution._canonical_receipt_digest(out['receipt'])
        path.write_text(json.dumps(out['receipt'], ensure_ascii=False, indent=2),
                        encoding='utf-8')

    def attach_signed_attestation(self, out, name='ATT-B3'):
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
        return out

    def mapping(self, out, goal='G-1', task='325',
                criteria=(('C1', CRITERION),)):
        receipt = out['receipt']
        entries = []
        for index, (criterion, statement) in enumerate(criteria, 1):
            entries.append({
                'criterion_id': criterion, 'goal_id': goal, 'task_id': task,
                'criterion_description': statement,
                'target_repository': str(self.repo),
                'target_commit_sha': self.base, 'evidence_id': f'EV-{index}',
                'evidence_source': 'test', 'evidence_command': receipt['command'],
                'evidence_log': out['log'], 'evidence_exit_code': receipt['exit_code'],
                'evidence_receipt': out['path'], 'execution_status': 'passed',
                'coverage_claim': '覆盖对应标准', 'coverage_review_status': 'confirmed',
                'independent_verifier': 'verifier-agent', 'verification_result': 'pass'})
        return {'criteria': entries}

    def prepare_verification(self, out, goal='G-1', task='325',
                             criteria=(('C1', CRITERION),)):
        create_goal(self.repo, goal, goal + ' title', 'background', 'outcome',
                    'owner', [statement for _, statement in criteria])
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
                                out, goal=goal, task=task, criteria=criteria))
        self.assertIsNotNone(result['verification'])
        return result['verification']

    def record_path(self, record):
        return (self.repo / '.project-memory/verifications' / str(record['task'])
                / f"{record['verification_id']}.json")

    def signed_verified(self, record):
        record = json.loads(json.dumps(record))
        record['status'] = 'VERIFIED'
        record['verified'] = True
        record['mapping_status'] = 'complete'
        for entry in record.get('criterion_evidence', []):
            entry['evidence_matched'] = True
        record.pop('authority', None)
        self.sign(record, authority.verification_payload, record['verification_id'])
        self.record_path(record).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return record

    def accepted_record(self, **kwargs):
        out = self.attach_signed_attestation(self.make_receipt())
        return self.signed_verified(self.prepare_verification(out, **kwargs))

    def rewrite_goal(self, mutate):
        path = self.repo / '.project-memory/goals/G-1.json'
        goal = json.loads(path.read_text(encoding='utf-8'))
        mutate(goal)
        path.write_text(json.dumps(goal, ensure_ascii=False, indent=2), encoding='utf-8')

    # ------------------------------------------------------------ AC-1 / AC-2

    def test_new_record_satisfies_after_evidence_and_bytes_unchanged(self):
        record = self.accepted_record()
        path = self.record_path(record)
        before = path.read_bytes()
        added = add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                                  record['verification_id'])
        self.assertEqual(added['criterion'], 'C1')
        self.assertEqual(path.read_bytes(), before)
        stored = json.loads(path.read_text(encoding='utf-8'))
        self.assertTrue(authority.verification_authority(self.repo, stored)['trusted'])
        self.assertTrue(_verification_current(self.repo, stored))
        evaluation = evaluate_goal(self.repo, 'G-1')
        self.assertTrue(evaluation['satisfied'], evaluation)
        self.assertEqual(evaluation['recommendation'], 'achieved')

    def test_new_record_binds_definitions_not_evidence(self):
        record = self.accepted_record()
        goal = load_goal(self.repo, 'G-1')
        self.assertEqual(record['goal_criteria_sha256'],
                         _criteria_definition_digest(goal['success_criteria']))
        self.assertEqual(record['goal_criteria_legacy_sha256'],
                         authority.canonical_digest(goal['success_criteria']))
        self.assertNotEqual(record['goal_criteria_sha256'],
                            record['goal_criteria_legacy_sha256'])
        add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                          record['verification_id'])
        after = load_goal(self.repo, 'G-1')
        self.assertEqual(record['goal_criteria_sha256'],
                         _criteria_definition_digest(after['success_criteria']))

    # ------------------------------------------------------------ AC-3

    def test_legacy_full_digest_record_survives_evidence_append(self):
        out = self.attach_signed_attestation(self.make_receipt())
        record = json.loads(json.dumps(self.prepare_verification(out)))
        legacy_digest = authority.canonical_digest(
            load_goal(self.repo, 'G-1')['success_criteria'])
        record['goal_criteria_sha256'] = legacy_digest
        record.pop('goal_criteria_legacy_sha256', None)
        record = self.signed_verified(record)
        add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                          record['verification_id'])
        self.assertTrue(_verification_current(self.repo, record))
        evaluation = evaluate_goal(self.repo, 'G-1')
        self.assertTrue(evaluation['satisfied'], evaluation)

    # ------------------------------------------------------------ AC-4

    def assert_definition_change_invalidates(self, mutate, expect_message=False):
        record = self.accepted_record()
        add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                          record['verification_id'])
        self.rewrite_goal(mutate)
        self.assertFalse(_verification_current(self.repo, record))
        ok, reason, trust = _verification_ok(
            self.repo, {'kind': 'verification', 'ref': record['verification_id']},
            'G-1', 'C1')
        self.assertFalse(ok)
        self.assertEqual(trust, 'unconfirmed')
        if expect_message:
            self.assertIn('判据定义已变化', reason)
        self.assertFalse(evaluate_goal(self.repo, 'G-1')['satisfied'])

    def test_statement_change_invalidates(self):
        self.assert_definition_change_invalidates(
            lambda goal: goal['success_criteria'][0].__setitem__('statement', '被替换的标准'),
            expect_message=True)

    def test_required_change_invalidates(self):
        # Keep a second required criterion so evaluate does not become
        # trivially satisfied when C1 stops being required.
        out = self.attach_signed_attestation(self.make_receipt())
        record = self.signed_verified(self.prepare_verification(
            out, criteria=(('C1', CRITERION), ('C2', '第二标准'))))
        add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                          record['verification_id'])
        add_goal_evidence(self.repo, 'G-1', 'C2', 'verification',
                          record['verification_id'])
        self.assertTrue(evaluate_goal(self.repo, 'G-1')['satisfied'])
        self.rewrite_goal(
            lambda goal: goal['success_criteria'][0].__setitem__('required', False))
        self.assertFalse(_verification_current(self.repo, record))
        ok, reason, trust = _verification_ok(
            self.repo, {'kind': 'verification', 'ref': record['verification_id']},
            'G-1', 'C1')
        self.assertFalse(ok)
        self.assertEqual(trust, 'unconfirmed')
        self.assertIn('判据定义已变化', reason)
        self.assertFalse(evaluate_goal(self.repo, 'G-1')['satisfied'])

    def test_criterion_id_change_invalidates(self):
        self.assert_definition_change_invalidates(
            lambda goal: goal['success_criteria'][0].__setitem__('id', 'C2'),
            expect_message=True)

    # ------------------------------------------------------------ AC-5

    def test_replacing_evidence_keeps_new_record_current(self):
        record = self.accepted_record()
        add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                          record['verification_id'])
        self.rewrite_goal(lambda goal: goal['success_criteria'][0]['evidence'][0]
                          .__setitem__('note', 'edited evidence note'))
        self.assertTrue(_verification_current(self.repo, record))
        self.assertTrue(evaluate_goal(self.repo, 'G-1')['satisfied'])

    def test_appending_a_second_evidence_item_keeps_new_record_current(self):
        record = self.accepted_record()
        add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                          record['verification_id'])
        add_goal_evidence(self.repo, 'G-1', 'C1', 'commit', self.base)
        self.assertTrue(_verification_current(self.repo, record))
        self.assertTrue(evaluate_goal(self.repo, 'G-1')['satisfied'])

    # ------------------------------------------------------------ AC-6

    def test_handwritten_untrusted_receipt_is_still_rejected(self):
        record = self.signed_verified(self.prepare_verification(self.make_receipt()))
        with self.assertRaises(PMError) as ctx:
            add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                              record['verification_id'])
        self.assertIn('执行来源不可信', str(ctx.exception))
        self.assertFalse(evaluate_goal(self.repo, 'G-1')['satisfied'])

    def test_claimed_trusted_boolean_is_still_rejected(self):
        out = self.make_receipt()
        out['receipt']['execution_provenance'] = {
            'kind': 'local_untrusted', 'trusted': True,
            'reason': 'agent wrote trusted=true by hand',
        }
        self._rewrite_receipt(out)
        record = self.signed_verified(self.prepare_verification(out))
        with self.assertRaises(PMError) as ctx:
            add_goal_evidence(self.repo, 'G-1', 'C1', 'verification',
                              record['verification_id'])
        self.assertIn('执行来源不可信', str(ctx.exception))
        self.assertFalse(evaluate_goal(self.repo, 'G-1')['satisfied'])


if __name__ == '__main__':
    unittest.main()
