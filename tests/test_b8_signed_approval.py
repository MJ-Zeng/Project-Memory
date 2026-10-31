"""B8: signed approval events (who approved, when, and for which commit).

An approval is a detached-signature record.  The approver identity comes from
the protected approval anchor's ``issuer``, never from a CLI flag, and the
approval only covers the ``commit_sha`` inside the signed payload.  A criterion
scope additionally binds a verification record by digest; rewriting that record
invalidates the approval.

The signing tests use a test-time RSA key (openssl) and patch
``authority.load_anchor`` so the cryptographic path runs without production
keys.  Without a configured ``PROJECT_MEMORY_APPROVAL_ANCHOR`` every record is
``unverified_approval``: it can be registered, but it never satisfies a goal.
"""
import base64
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openssl_support import require_openssl
from project_memory import authority
from project_memory.cli import main
from project_memory.common import PMError, git_sha
from project_memory.coordination import (add_goal_evidence, approval_authority,
                                         approval_list, attach_approval, create_goal,
                                         evaluate_goal, finish_run, reconcile,
                                         start_run, verify_run,
                                         write_approval_request, _approval_id,
                                         _approval_repository)
from project_memory.execution import repo_identity, run_command

GOAL = 'G-APPROVAL'
TASK = 'B8'
CRITERION = '签名审批后标准可被人工确认'
APPROVER = 'approver@example.invalid'


class _RepoFixture(unittest.TestCase):
    """A throwaway git repository with helpers shared by both test classes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'b8@example.invalid')
        self.git('config', 'user.name', 'B8')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        self.git('add', 'README.md')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def make_goal(self, criterion=CRITERION):
        return create_goal(self.repo, GOAL, 'B8 goal', 'background', 'outcome',
                           'owner@example.invalid', [criterion])

    def start(self, run_id, agent='dev-agent', model='auto', role='executor'):
        return start_run(self.repo, GOAL, TASK, run_id, agent, 'qodercn', model,
                         base_sha=self.base, role=role)

    def prepare_runs(self):
        self.make_goal()
        self.start('run-target')
        finish_run(self.repo, TASK, 'run-target', ['implemented'], ['verify'],
                   head_sha=self.base)
        self.start('run-verifier', agent='verifier-agent',
                   model='verifier-model', role='verifier')

    def goal_file(self):
        return self.repo / '.project-memory' / 'goals' / f'{GOAL}.json'

    def remove_evidence(self, kind):
        goal = json.loads(self.goal_file().read_text(encoding='utf-8'))
        removed = []
        for criterion in goal.get('success_criteria', []):
            kept = []
            for item in criterion.get('evidence', []):
                if item.get('kind') == kind:
                    removed.append(item)
                else:
                    kept.append(item)
            criterion['evidence'] = kept
        self.goal_file().write_text(json.dumps(goal, ensure_ascii=False, indent=2),
                                    encoding='utf-8')
        return removed

    def restore_evidence(self, items):
        goal = json.loads(self.goal_file().read_text(encoding='utf-8'))
        for criterion in goal.get('success_criteria', []):
            if criterion.get('id') == 'C1':
                criterion.setdefault('evidence', []).extend(items)
        self.goal_file().write_text(json.dumps(goal, ensure_ascii=False, indent=2),
                                    encoding='utf-8')

    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def out_dir(self):
        """A sibling directory outside the repo, like a real signer's workspace."""
        if not hasattr(self, '_out_dir'):
            self._out_dir = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, self._out_dir, ignore_errors=True)
        return self._out_dir


class B8StaticApprovalTest(_RepoFixture):
    """Paths that must work without openssl or a real key."""

    def static_verification(self):
        """A verification record whose mapping is already complete (externally confirmed)."""
        self.prepare_runs()
        identity = repo_identity(self.repo)
        verification = {
            'schema_version': '1.2', 'kind': 'verification_record',
            'verification_id': 'VER-static', 'task': TASK, 'goal_id': GOAL,
            'target_run': 'run-target', 'verifier_run': 'run-verifier',
            'target_head_sha': self.base, 'current_head_sha': self.base,
            'stale': False, 'standard': 'static fixture', 'verdict': 'pass',
            'evidence_level': 'locally_observed', 'trust_level': 'locally_observed',
            'status': 'MANUAL_REVIEW_REQUIRED', 'mapping_status': 'complete',
            'criterion_evidence': [{
                'criterion_id': 'C1', 'goal_id': GOAL, 'task_id': TASK,
                'criterion_description': CRITERION, 'target_repository': str(self.repo),
                'target_commit_sha': self.base, 'evidence_id': 'EV-static',
                'evidence_source': 'test', 'execution_status': 'passed',
                'coverage_review_status': 'confirmed', 'description_match': True,
                'evidence_matched': True, 'verification_result': 'pass',
            }],
            'verified': False, 'checks': {'tests': {}, 'ci': None, 'review': None},
            'findings': [], 'created_at': '2026-10-31T02:00:00Z', 'revision': 1,
            'repository': identity,
        }
        path = self.repo / '.project-memory' / 'verifications' / TASK / 'VER-static.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(verification, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        return verification, path

    def build_approval(self, verification, decision='approve', commit=None,
                       digest=None, goal_id=GOAL, criterion_id='C1', **overrides):
        record = {
            'schema_version': '1.0', 'kind': 'approval_event',
            'decision': decision, 'approver': APPROVER,
            'at': '2026-10-31T02:00:00Z',
            'repository': _approval_repository(self.repo),
            'commit_sha': commit or self.base,
            'scope': {
                'kind': 'criterion', 'goal_id': goal_id, 'criterion_id': criterion_id,
                'verification': {
                    'ref': f'verifications/{TASK}/VER-static.json',
                    'verification_id': verification['verification_id'],
                    'digest': digest or authority.verification_subject_digest(verification),
                    'target_head_sha': verification['target_head_sha'],
                    'evidence_id': 'EV-static',
                },
            },
            'statement': '静态夹具',
        }
        record.update(overrides)
        record['approval_id'] = _approval_id(record)
        return record

    def write_approval(self, record, name=None):
        path = (self.repo / '.project-memory' / 'approvals'
                / ((name or record['approval_id']) + '.json'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        return path

    def test_no_approval_anchor_registers_but_never_satisfies(self):
        verification, _ = self.static_verification()
        record = self.build_approval(verification)
        record['authority'] = {
            'status': 'signed', 'anchor_id': 'static', 'issuer': APPROVER,
            'algorithm': 'rsa-sha256', 'signed_payload_sha256': '0' * 64,
            'signature_b64': 'AA==',
        }
        path = self.write_approval(record)
        with mock.patch('project_memory.authority.load_anchor',
                        return_value=(None, '未配置 PROJECT_MEMORY_APPROVAL_ANCHOR')):
            result = add_goal_evidence(self.repo, GOAL, 'C1', 'approval', str(path))
            evaluation = evaluate_goal(self.repo, GOAL)
        self.assertTrue(result['evidence']['kind'] == 'approval')
        self.assertFalse(evaluation['satisfied'])
        approval = evaluation['approvals'][0]
        self.assertEqual(approval['state'], 'UNVERIFIED_APPROVAL')
        self.assertEqual(approval['authority_status'], 'unconfigured')
        self.assertFalse(approval['trusted'])
        self.assertFalse(approval['satisfies'])

    def test_self_declared_trusted_envelope_without_signature_is_untrusted(self):
        anchor = {
            'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
            'anchor_id': 'static', 'issuer': APPROVER, 'algorithm': 'rsa-sha256',
            'public_key_pem': '-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n',
        }
        record = {
            'schema_version': '1.0', 'kind': 'approval_event',
            'decision': 'approve', 'approver': APPROVER,
            'at': '2026-10-31T02:00:00Z',
            'repository': {'id': 'x'}, 'commit_sha': '0' * 40,
            'scope': {'kind': 'commit'},
            'authority': {'status': 'trusted', 'anchor_id': 'static',
                          'issuer': APPROVER, 'algorithm': 'rsa-sha256',
                          'signed_payload_sha256': '0' * 64,
                          'signature_b64': 'AA=='},
        }
        record['approval_id'] = _approval_id(record)
        with mock.patch('project_memory.authority.load_anchor',
                        return_value=(dict(anchor), 'ok')):
            verdict = approval_authority(self.repo, record)
        self.assertFalse(verdict['trusted'])
        self.assertEqual(verdict['status'], 'untrusted')

    def test_manual_evidence_and_declared_human_approved_stay_unverified(self):
        self.prepare_runs()
        add_goal_evidence(self.repo, GOAL, 'C1', 'manual',
                          'https://review.example.invalid/1',
                          approved_by='human-lead@example.invalid')
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertFalse(evaluation['satisfied'])
        states = {item.get('state') for item in evaluation['criteria'][0]['evidence']}
        self.assertIn('UNVERIFIED_APPROVAL', states)
        with self.assertRaises(PMError) as caught:
            verify_run(self.repo, 'run-target', 'run-verifier', 'B8', 'pass',
                       'human_approved')
        self.assertIn('human_approved', str(caught.exception))

    def test_absent_approvals_directory_adds_no_findings(self):
        self.prepare_runs()
        self.assertFalse((self.repo / '.project-memory' / 'approvals').exists())
        report = reconcile(self.repo)
        self.assertEqual([], [item for item in report['items']
                              if item['code'].startswith('approval_')])

    def test_reconcile_reports_orphan_approval(self):
        verification, _ = self.static_verification()
        record = self.build_approval(verification, goal_id='G-MISSING')
        self.write_approval(record)
        report = reconcile(self.repo)
        codes = {item['code'] for item in report['items']}
        self.assertIn('approval_orphan', codes)
        self.assertIn('approval_not_trusted', codes)


class B8SignedApprovalTest(_RepoFixture):
    """End-to-end signed approvals with a test-time RSA key."""

    @classmethod
    def setUpClass(cls):
        cls.openssl = require_openssl('B8 签名审批测试需要测试期签名者')
        cls.keydir = tempfile.TemporaryDirectory()
        work = Path(cls.keydir.name)
        cls.key = work / 'approver-key.pem'
        cls.other_key = work / 'other-key.pem'
        for key in (cls.key, cls.other_key):
            subprocess.run([cls.openssl, 'genpkey', '-algorithm', 'RSA',
                            '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(key)],
                           check=True, capture_output=True)
        public = work / 'approver-key.pub.pem'
        subprocess.run([cls.openssl, 'pkey', '-in', str(cls.key), '-pubout',
                        '-out', str(public)], check=True, capture_output=True)
        cls.anchor = {
            'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
            'anchor_id': 'b8-test-anchor', 'issuer': APPROVER,
            'algorithm': 'rsa-sha256',
            'public_key_pem': public.read_text(encoding='utf-8'),
        }
        cls.anchor_path = work / 'approver-anchor.json'
        cls.anchor_path.write_text(json.dumps(cls.anchor), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        super().setUp()

        def fake_anchor(repo, env_name=authority.ANCHOR_ENV):
            if env_name == authority.APPROVAL_ANCHOR_ENV:
                return {**self.anchor, 'path': str(self.anchor_path),
                        'protection': 'test'}, 'ok'
            return None, 'B8 测试未配置验证信任锚'

        patcher = mock.patch('project_memory.authority.load_anchor',
                             side_effect=fake_anchor)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------ fixtures

    def mapping(self, out):
        receipt = out['receipt']
        return {'criteria': [{
            'criterion_id': 'C1', 'goal_id': GOAL, 'task_id': TASK,
            'criterion_description': CRITERION,
            'target_repository': str(self.repo), 'target_commit_sha': self.base,
            'evidence_id': 'EV-1', 'evidence_source': 'test',
            'evidence_command': receipt['command'], 'evidence_log': out['log'],
            'evidence_exit_code': receipt['exit_code'],
            'evidence_receipt': out['path'], 'execution_status': 'passed',
            'coverage_claim': '该检查覆盖对应成功标准',
            'coverage_review_status': 'confirmed',
            'independent_verifier': 'verifier-agent', 'verification_result': 'pass',
        }]}

    def prepare_verification(self, confirm=True):
        self.make_goal()
        out = run_command(self.repo, [sys.executable, '-c',
                                      "import sys; print('1 passed'); sys.exit(0)"],
                          self.base, executed_by='b8-harness')
        self.start('run-target')
        finish_run(self.repo, TASK, 'run-target', ['implemented'], ['verify'],
                   head_sha=self.base,
                   tests=[{'command': out['receipt']['command'], 'exit_code': 0,
                           'log': out['log']}])
        self.start('run-verifier', agent='verifier-agent',
                   model='verifier-model', role='verifier')
        result = verify_run(self.repo, 'run-target', 'run-verifier', 'B8 acceptance',
                            'pass', 'locally_observed', test_receipt=out['path'],
                            criterion_evidence=self.mapping(out))
        self.assertIsNotNone(result['verification'])
        path = self.repo / result['path']
        record = json.loads(path.read_text(encoding='utf-8'))
        if confirm:
            # B8 binds an already-confirmed mapping; it never rewrites a
            # verification record itself.  Simulate the external confirmation.
            record['mapping_status'] = 'complete'
            for entry in record.get('criterion_evidence') or []:
                entry['evidence_matched'] = True
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                            encoding='utf-8')
        self.verification_ref = result['path']
        return record

    def request(self, decision='approve', approver=APPROVER, scope=True,
                commit=None):
        work = self.out_dir()
        kwargs = {}
        if scope:
            kwargs = {'goal_id': GOAL, 'criterion_id': 'C1',
                      'verification_ref': self.verification_ref}
        out = write_approval_request(self.repo, commit or self.base, approver,
                                     decision, '批准该验证记录',
                                     output=work / 'request.json', **kwargs)
        # Requests are signed outside the repo, so the reported path must stay usable.
        self.assertEqual(str((work / 'request.json').resolve()), out['path'])
        return out

    def sign(self, payload: bytes, name='sig', key=None):
        work = Path(self.tmp.name)
        payload_file = work / f'{name}.payload'
        signature_file = work / f'{name}.sig'
        payload_file.write_bytes(payload)
        subprocess.run([self.openssl, 'dgst', '-sha256', '-sign',
                        str(key or self.key), '-out', str(signature_file),
                        str(payload_file)], check=True, capture_output=True)
        return signature_file.read_bytes()

    def attach(self, request, name='sig', key=None, anchor=None):
        payload = authority.signed_record_payload(request['request'])
        signature_file = Path(self.tmp.name) / f'{name}.sig'
        signature_file.write_bytes(self.sign(payload, name, key))
        return attach_approval(self.repo, request['path'], signature_file,
                               anchor or self.anchor_path)

    def attach_valid(self):
        request = self.request()
        return request, self.attach(request)

    # ---------------------------------------------------------------- tests

    def test_signed_criterion_approval_satisfies_and_cli_verifies(self):
        self.prepare_verification()
        request, attached = self.attach_valid()
        self.assertTrue(attached['signature_valid'])
        self.assertTrue(attached['created'])
        path = self.repo / attached['path']
        code, output = self.run_cli(['approval', 'verify', '--repo', str(self.repo),
                                     '--record', str(path), '--commit', self.base,
                                     '--json'])
        self.assertEqual(0, code)
        self.assertTrue(json.loads(output)['verified'])
        code, output = self.run_cli(['goal', 'evidence', '--repo', str(self.repo),
                                     '--id', GOAL, '--criterion', 'C1',
                                     '--kind', 'approval', '--ref', attached['path']])
        self.assertEqual(0, code)
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertTrue(evaluation['satisfied'])
        self.assertEqual('satisfied', evaluation['criteria'][0]['status'])
        approval = evaluation['approvals'][0]
        self.assertEqual('human_approved', approval['state'])
        self.assertTrue(approval['trusted'])
        self.assertTrue(approval['satisfies'])
        self.assertEqual(APPROVER, approval['approver'])
        listed = approval_list(self.repo, commit_sha=self.base, goal_id=GOAL)
        self.assertEqual(1, len(listed['approvals']))
        self.assertTrue(listed['approvals'][0]['trusted'])
        self.assertEqual(attached['approval_id'], request['approval_id'])

    def test_tampering_any_signed_field_invalidates(self):
        self.prepare_verification()
        _request, attached = self.attach_valid()
        add_goal_evidence(self.repo, GOAL, 'C1', 'approval', attached['path'])
        self.assertTrue(evaluate_goal(self.repo, GOAL)['satisfied'])
        path = self.repo / attached['path']
        original = json.loads(path.read_text(encoding='utf-8'))

        def tamper(field, value):
            record = json.loads(json.dumps(original))
            if field == 'criterion_id':
                record['scope']['criterion_id'] = value
            elif field == 'digest':
                record['scope']['verification']['digest'] = value
            else:
                record[field] = value
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                            encoding='utf-8')
            self.assertFalse(approval_authority(self.repo, record)['trusted'])
            evaluation = evaluate_goal(self.repo, GOAL)
            self.assertFalse(evaluation['satisfied'], field)
            self.assertNotEqual('human_approved',
                                evaluation['approvals'][0]['state'], field)

        for field, value in (
                ('decision', 'reject'),
                ('commit_sha', '0' * 40),
                ('approver', 'attacker@example.invalid'),
                ('criterion_id', 'C9'),
                ('digest', '0' * 64)):
            tamper(field, value)

        codes = {item['code'] for item in reconcile(self.repo)['items']}
        self.assertIn('approval_subject_mismatch', codes)
        path.write_text(json.dumps(original, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        self.assertTrue(evaluate_goal(self.repo, GOAL)['satisfied'])

    def test_wrong_key_is_rejected_by_attach_and_untrusted_directly(self):
        self.prepare_verification()
        request = self.request()
        with self.assertRaises(PMError) as caught:
            self.attach(request, name='wrong', key=self.other_key)
        self.assertIn('签名', str(caught.exception))
        forged = dict(request['request'])
        payload = authority.signed_record_payload(forged)
        forged['authority'] = {
            'status': 'signed', 'anchor_id': self.anchor['anchor_id'],
            'issuer': APPROVER, 'algorithm': 'rsa-sha256',
            'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'signature_b64': base64.b64encode(
                self.sign(payload, 'forged', self.other_key)).decode('ascii'),
        }
        verdict = approval_authority(self.repo, forged)
        self.assertFalse(verdict['trusted'])
        self.assertEqual('untrusted', verdict['status'])

    def test_approver_must_match_anchor_issuer(self):
        self.prepare_verification()
        request = self.request(approver='other@example.invalid')
        with self.assertRaises(PMError) as caught:
            self.attach(request, name='mismatch')
        self.assertIn('issuer', str(caught.exception))
        record = dict(request['request'])
        payload = authority.signed_record_payload(record)
        record['authority'] = {
            'status': 'signed', 'anchor_id': self.anchor['anchor_id'],
            'issuer': APPROVER, 'algorithm': 'rsa-sha256',
            'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'signature_b64': base64.b64encode(self.sign(payload, 'mismatch')).decode('ascii'),
        }
        verdict = approval_authority(self.repo, record)
        self.assertFalse(verdict['trusted'])
        self.assertIn('issuer', verdict['reason'])

    def test_reject_decision_is_visible_but_never_satisfies(self):
        self.prepare_verification()
        request, attached = self.attach_valid_with('reject')
        self.assertEqual('reject', attached['approval']['decision'])
        add_goal_evidence(self.repo, GOAL, 'C1', 'approval', attached['path'])
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertFalse(evaluation['satisfied'])
        approval = evaluation['approvals'][0]
        self.assertEqual('human_rejected', approval['state'])
        self.assertEqual('reject', approval['decision'])
        codes = {item['code'] for item in reconcile(self.repo)['items']}
        self.assertIn('approval_rejected', codes)
        self.assertEqual(request['approval_id'], attached['approval_id'])

    def attach_valid_with(self, decision):
        request = self.request(decision=decision)
        return request, self.attach(request)

    def test_rewriting_verification_invalidates_digest(self):
        self.prepare_verification()
        _request, attached = self.attach_valid()
        add_goal_evidence(self.repo, GOAL, 'C1', 'approval', attached['path'])
        self.assertTrue(evaluate_goal(self.repo, GOAL)['satisfied'])
        path = self.repo / self.verification_ref
        record = json.loads(path.read_text(encoding='utf-8'))
        record['standard'] = 'rewritten after approval'
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertFalse(evaluation['satisfied'])
        self.assertIn('摘要', evaluation['approvals'][0]['reason'])

    def test_commit_advance_makes_approval_stale(self):
        self.prepare_verification()
        _request, attached = self.attach_valid()
        add_goal_evidence(self.repo, GOAL, 'C1', 'approval', attached['path'])
        self.assertTrue(evaluate_goal(self.repo, GOAL)['satisfied'])
        (self.repo / 'later.txt').write_text('later\n', encoding='utf-8')
        self.git('add', 'later.txt')
        self.git('commit', '-qm', 'later')
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertFalse(evaluation['satisfied'])
        self.assertIn('当前 HEAD', evaluation['approvals'][0]['reason'])
        codes = {item['code'] for item in reconcile(self.repo)['items']}
        self.assertIn('approval_stale_commit', codes)

    def test_commit_scope_verifies_but_does_not_join_goal(self):
        self.make_goal()
        request = self.request(scope=False)
        self.assertEqual('commit', request['request']['scope']['kind'])
        attached = self.attach(request)
        path = self.repo / attached['path']
        code, _ = self.run_cli(['approval', 'verify', '--repo', str(self.repo),
                                '--record', str(path), '--commit', self.base])
        self.assertEqual(0, code)
        code, _ = self.run_cli(['approval', 'verify', '--repo', str(self.repo),
                                '--record', str(path), '--commit', '0' * 40])
        self.assertEqual(2, code)
        with self.assertRaises(PMError) as caught:
            add_goal_evidence(self.repo, GOAL, 'C1', 'approval', attached['path'])
        self.assertIn('commit 范围', str(caught.exception))
        listed = approval_list(self.repo)['approvals']
        self.assertEqual('commit', listed[0]['scope'])
        self.assertTrue(listed[0]['trusted'])

    def test_negative_control_remove_and_restore(self):
        self.prepare_verification()
        _request, attached = self.attach_valid()
        add_goal_evidence(self.repo, GOAL, 'C1', 'approval', attached['path'])
        before = evaluate_goal(self.repo, GOAL)
        removed = self.remove_evidence('approval')
        middle = evaluate_goal(self.repo, GOAL)
        self.restore_evidence(removed)
        after = evaluate_goal(self.repo, GOAL)
        print(f"negative-control before: satisfied={before['satisfied']} "
              f"status={before['criteria'][0]['status']}")
        print(f"negative-control removed: satisfied={middle['satisfied']} "
              f"status={middle['criteria'][0]['status']}")
        print(f"negative-control restored: satisfied={after['satisfied']} "
              f"status={after['criteria'][0]['status']}")
        self.assertTrue(before['satisfied'])
        self.assertFalse(middle['satisfied'])
        self.assertNotEqual('satisfied', middle['criteria'][0]['status'])
        self.assertTrue(after['satisfied'])


if __name__ == '__main__':
    unittest.main()
