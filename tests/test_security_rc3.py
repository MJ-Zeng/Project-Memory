"""RC3 security regression tests: authority, receipts, snapshots, sandbox labels.

These tests do not pretend to be an independent security review.  They pin the
fail-closed behavior implemented in this candidate so later edits cannot quietly
restore the forgery path.
"""
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from project_memory import execution
from project_memory.common import PMError, git_sha
from project_memory.coordination import (add_goal_evidence, create_goal, evaluate_goal,
                                         finish_run, goal_show, iter_verifications,
                                         load_goal, reconcile, resume_run, start_run,
                                         transition_goal, verify_run)
from project_memory.execution import create_snapshot, run_command, verify_receipt
from project_memory.trusted_exec import DISABLE_ENV

CRITERION = '模块通过测试'


class SecurityRc3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'security@example.invalid')
        self.git('config', 'user.name', 'Security')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_auth.py').write_text(
            'def test_ok():\n    assert True\n', encoding='utf-8')
        self.git('add', 'README.md', 'tests/test_auth.py')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def make_goal(self, goal_id='G-1', criterion=CRITERION):
        return create_goal(self.repo, goal_id, goal_id + ' title', 'background',
                           'outcome', 'owner', [criterion])

    def start(self, goal='G-1', run_id='run-target', task='325', agent='dev-agent',
              role='executor', model='auto'):
        return start_run(self.repo, goal, task, run_id, agent, 'qodercn', model,
                         base_sha=self.base, role=role)

    def passable(self, goal='G-1', task='325'):
        self.make_goal(goal)
        out = run_command(self.repo, [sys.executable, '-c',
                                      "import sys; print('1 passed'); sys.exit(0)"],
                          self.base, executed_by='test-harness')
        self.start(goal=goal, run_id='run-target', task=task)
        finish_run(self.repo, task, 'run-target', ['implemented'], ['verify'],
                   head_sha=self.base,
                   tests=[{'command': out['receipt']['command'], 'exit_code': 0,
                           'log': out['log']}])
        self.start(goal=goal, run_id='run-verifier', task=task,
                   agent='verifier-agent', role='verifier', model='verifier-model')
        return out

    def mapping(self, out, goal='G-1', task='325', criterion='C1', statement=CRITERION,
                evidence_id='EV-1', coverage='confirmed', log=None, command=None,
                exit_code=None, sha=None, source='test'):
        receipt = out['receipt']
        return {'criteria': [{
            'criterion_id': criterion, 'goal_id': goal, 'task_id': task,
            'criterion_description': statement, 'target_repository': str(self.repo),
            'target_commit_sha': sha or self.base, 'evidence_id': evidence_id,
            'evidence_source': source,
            'evidence_command': receipt['command'] if command is None else command,
            'evidence_log': out['log'] if log is None else log,
            'evidence_exit_code': receipt['exit_code'] if exit_code is None else exit_code,
            'evidence_receipt': out['path'], 'execution_status': 'passed',
            'coverage_claim': '覆盖对应标准', 'coverage_review_status': coverage,
            'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}

    def verified_record(self, out=None, goal='G-1', task='325'):
        out = out or self.passable(goal=goal, task=task)
        return verify_run(self.repo, 'run-target', 'run-verifier', 'acceptance', 'pass',
                          'locally_observed', test_receipt=out['path'],
                          criterion_evidence=self.mapping(out, goal=goal, task=task))

    # ------------------------------------------------------------ authority

    def test_handwritten_record_is_not_authority(self):
        self.make_goal()
        self.passable()
        record = {
            'schema_version': '1.2', 'kind': 'verification_record',
            'verification_id': 'VER-forged', 'task': '325', 'goal_id': 'G-1',
            'target_run': 'run-target', 'verifier_run': 'run-verifier',
            'verifier': {'agent': 'verifier-agent'},
            'independence': {'distinct': True, 'basis': ['agent']},
            'target_head_sha': self.base, 'current_head_sha': self.base, 'stale': False,
            'standard': 'forged', 'verdict': 'pass', 'evidence_level': 'locally_observed',
            'status': 'VERIFIED', 'verified': True, 'checks': {}, 'findings': [],
            'created_at': '2026-01-01T00:00:00Z', 'revision': 1,
            'criterion_evidence': [{
                'criterion_id': 'C1', 'goal_id': 'G-1', 'target_commit_sha': self.base,
                'evidence_id': 'EV-forged', 'evidence_matched': True,
                'coverage_review_status': 'confirmed'}],
            'mapping_status': 'complete',
        }
        path = self.repo / '.project-memory/verifications/325/VER-forged.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(PMError) as ctx:
            add_goal_evidence(self.repo, 'G-1', 'C1', 'verification', 'VER-forged')
        self.assertIn('可信授权来源', str(ctx.exception))
        self.assertFalse(evaluate_goal(self.repo, 'G-1')['satisfied'])

    def test_self_declared_authority_is_not_trusted(self):
        self.make_goal()
        self.passable()
        record = {
            'schema_version': '1.2', 'kind': 'verification_record',
            'verification_id': 'VER-self', 'task': '325', 'goal_id': 'G-1',
            'target_run': 'run-target', 'verifier_run': 'run-verifier',
            'verifier': {'agent': 'verifier-agent'},
            'independence': {'distinct': True, 'basis': ['agent']},
            'target_head_sha': self.base, 'current_head_sha': self.base, 'stale': False,
            'standard': 'self', 'verdict': 'pass', 'evidence_level': 'locally_observed',
            'status': 'VERIFIED', 'verified': True, 'checks': {}, 'findings': [],
            'created_at': '2026-01-01T00:00:00Z', 'revision': 1,
            'criterion_evidence': [{
                'criterion_id': 'C1', 'goal_id': 'G-1', 'target_commit_sha': self.base,
                'evidence_id': 'EV-self', 'evidence_matched': True,
                'coverage_review_status': 'confirmed'}],
            'mapping_status': 'complete',
            'authority': {'status': 'trusted', 'trusted': True,
                          'anchor_id': 'self', 'issuer': 'agent',
                          'algorithm': 'rsa-sha256', 'signed_payload_sha256': '0' * 64,
                          'signature_b64': 'ZmFrZQ=='},
        }
        path = self.repo / '.project-memory/verifications/325/VER-self.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(PMError):
            add_goal_evidence(self.repo, 'G-1', 'C1', 'verification', 'VER-self')

    def test_goal_achieved_requires_authority_and_is_audited(self):
        self.verified_record()
        transition_goal(self.repo, 'G-1', 'approved', approved_by='lead@example.com')
        approval = load_goal(self.repo, 'G-1')['approvals'][0]
        self.assertEqual(approval['approval_authority'], 'claimed_unverified')
        transition_goal(self.repo, 'G-1', 'active')
        transition_goal(self.repo, 'G-1', 'evaluating')
        with self.assertRaises(PMError) as ctx:
            transition_goal(self.repo, 'G-1', 'achieved', approved_by='lead@example.com')
        self.assertIn('尚未满足', str(ctx.exception))
        self.assertEqual(load_goal(self.repo, 'G-1')['status'], 'evaluating')
        audit = self.repo / '.project-memory/audit/verification_attempts.jsonl'
        entries = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(entries[-1]['reason'], 'goal_achieved_unsatisfied')

    def test_goal_show_does_not_count_untrusted_verified(self):
        # A locally written record is MANUAL_REVIEW_REQUIRED/verified=false, so it
        # must appear in neither counter.  A record that merely claims
        # verified=true is counted as a claim, never as a trusted verification.
        out = self.passable()
        self.verified_record(out)
        forged = {
            'schema_version': '1.2', 'kind': 'verification_record',
            'verification_id': 'VER-claim', 'task': '325', 'goal_id': 'G-1',
            'target_run': 'run-target', 'verifier_run': 'run-verifier',
            'verdict': 'pass', 'status': 'VERIFIED', 'verified': True,
            'criterion_evidence': [], 'mapping_status': 'complete',
        }
        path = self.repo / '.project-memory/verifications/325/VER-claim.json'
        path.write_text(json.dumps(forged, ensure_ascii=False), encoding='utf-8')
        shown = goal_show(self.repo, 'G-1')
        self.assertEqual(shown['progress']['verified_verifications'], 0)
        self.assertEqual(shown['progress']['claimed_verified_verifications'], 1)
        self.assertEqual(shown['status_authority'], 'local_untrusted')
        # The Goal is still 'proposed', so its recorded status is not inconsistent;
        # the point is that progress never counts an unsigned claim as verified.
        self.assertTrue(shown['status_consistent'])

    # ------------------------------------------------------------ receipts

    def test_receipt_filename_is_bound_to_id(self):
        out = self.passable()
        renamed = self.repo / '.project-memory/receipts/EXE-other.json'
        renamed.write_text((self.repo / out['path']).read_text(encoding='utf-8'),
                           encoding='utf-8')
        checked = verify_receipt(self.repo, '.project-memory/receipts/EXE-other.json')
        self.assertFalse(checked['valid'])
        self.assertIn('receipt_id', ' '.join(checked['problems']))

    def test_receipt_swap_invalidates_verification(self):
        from project_memory.coordination import _verification_current
        out = self.passable()
        result = self.verified_record(out)
        self.assertTrue(_verification_current(self.repo, result['verification']))
        other = run_command(self.repo, [sys.executable, '-c', "print('different')"],
                            self.base, executed_by='other')
        (self.repo / out['path']).write_text(
            (self.repo / other['path']).read_text(encoding='utf-8'), encoding='utf-8')
        self.assertFalse(_verification_current(self.repo, result['verification']))

    def test_second_edit_with_same_status_invalidates(self):
        from project_memory.coordination import _verification_current
        out = self.passable()
        target = self.repo / 'tests/test_auth.py'
        target.write_text('def test_ok():\n    assert False  # edit 1\n', encoding='utf-8')
        result = self.verified_record(out)
        self.assertTrue(_verification_current(self.repo, result['verification']))
        target.write_text('def test_ok():\n    assert False  # edit 2\n', encoding='utf-8')
        self.assertFalse(_verification_current(self.repo, result['verification']))

    def test_run_edit_invalidates_verification(self):
        from project_memory.coordination import _verification_current
        out = self.passable()
        result = self.verified_record(out)
        path = self.repo / '.project-memory/runs/325/run-target.json'
        run = json.loads(path.read_text(encoding='utf-8'))
        run['notes'] = 'edited after verification'
        path.write_text(json.dumps(run, ensure_ascii=False), encoding='utf-8')
        self.assertFalse(_verification_current(self.repo, result['verification']))

    def test_goal_criteria_edit_invalidates_verification(self):
        from project_memory.coordination import _verification_current
        out = self.passable()
        result = self.verified_record(out)
        path = self.repo / '.project-memory/goals/G-1.json'
        goal = json.loads(path.read_text(encoding='utf-8'))
        goal['success_criteria'][0]['statement'] = '被替换的标准'
        path.write_text(json.dumps(goal, ensure_ascii=False), encoding='utf-8')
        self.assertFalse(_verification_current(self.repo, result['verification']))

    def test_direct_achieved_status_is_flagged(self):
        self.make_goal()
        self.passable()
        path = self.repo / '.project-memory/goals/G-1.json'
        goal = json.loads(path.read_text(encoding='utf-8'))
        goal['status'] = 'achieved'
        path.write_text(json.dumps(goal, ensure_ascii=False), encoding='utf-8')
        evaluation = evaluate_goal(self.repo, 'G-1')
        self.assertFalse(evaluation['satisfied'])
        self.assertFalse(evaluation['recorded_status_consistent'])
        report = reconcile(self.repo, format='json')
        codes = {item['code'] for item in report['items']}
        self.assertIn('achieved_goal_unsatisfied', codes)

    # ------------------------------------------------------------ snapshots

    def test_archive_symlink_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'evil.tar'
            with tarfile.open(archive, 'w') as handle:
                link = tarfile.TarInfo('escape-link')
                link.type = tarfile.SYMTYPE
                link.linkname = '../../outside'
                handle.addfile(link)
            with tarfile.open(archive, 'r') as handle:
                with self.assertRaises(PMError) as ctx:
                    execution._validate_archive(handle)
            self.assertIn('链接', str(ctx.exception))

    def test_archive_traversal_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'evil.tar'
            with tarfile.open(archive, 'w') as handle:
                item = tarfile.TarInfo('../outside.txt')
                item.size = 1
                import io
                handle.addfile(item, io.BytesIO(b'x'))
            with tarfile.open(archive, 'r') as handle:
                with self.assertRaises(PMError):
                    execution._validate_archive(handle)

    def test_tree_digest_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'file.txt').write_text('x', encoding='utf-8')
            try:
                os.symlink(root / 'file.txt', root / 'link.txt')
            except (OSError, NotImplementedError):
                self.skipTest('当前平台不允许创建符号链接')
            with self.assertRaises(PMError):
                execution._tree_digest(root)

    def test_symlinked_snapshot_is_rejected(self):
        out = run_command(self.repo, [sys.executable, '-c', 'print(1)'], self.base)
        tree = self.repo / '.project-memory/snapshots' / out['snapshot']['snapshot_id'] / 'tree'
        real = tree.with_name('tree-real')
        tree.rename(real)
        try:
            os.symlink(real, tree, target_is_directory=True)
        except (OSError, NotImplementedError):
            real.rename(tree)
            self.skipTest('当前平台不允许创建符号链接')
        checked = verify_receipt(self.repo, out['path'])
        self.assertFalse(checked['valid'])
        self.assertIn('符号链接', ' '.join(checked['problems']))

    # ------------------------------------------------------------ execution modes

    def test_local_receipt_is_explicitly_untrusted(self):
        out = run_command(self.repo, [sys.executable, '-c', 'print(1)'], self.base)
        self.assertEqual(out['receipt']['trust'], 'local_untrusted')
        self.assertEqual(out['receipt']['isolation']['mode'], 'none')
        self.assertFalse(out['receipt']['execution_provenance']['trusted'])
        checked = verify_receipt(self.repo, out['path'])
        self.assertTrue(checked['valid'])
        self.assertFalse(checked['provenance']['trusted'])

    def test_relative_repo_path_does_not_raise(self):
        out = run_command(self.repo, [sys.executable, '-c', 'print(1)'], self.base)
        relative = os.path.relpath(self.repo, Path.cwd())
        checked = verify_receipt(Path(relative), out['path'])
        self.assertTrue(checked['valid'])

    def test_local_env_filters_credentials_and_rejects_injection(self):
        env = execution._local_env(self.repo, None)
        self.assertFalse(any(execution._sensitive_env_name(k) for k in env))
        with self.assertRaises(PMError):
            execution._local_env(self.repo, {'QODER_TOKEN': 'x'})
        with self.assertRaises(PMError):
            execution._local_env(self.repo, {'PYTHONPATH': '/tmp'})

    def test_trusted_mode_fails_closed_when_disabled(self):
        previous = os.environ.get(DISABLE_ENV)
        os.environ[DISABLE_ENV] = '1'
        try:
            before = set((self.repo / '.project-memory/receipts').glob('*.json')) \
                if (self.repo / '.project-memory/receipts').is_dir() else set()
            with self.assertRaises(PMError) as ctx:
                run_command(self.repo, ['python3', '-c', 'print(1)'], self.base,
                            mode='trusted')
            self.assertIn('可信执行不可用', str(ctx.exception))
            after = set((self.repo / '.project-memory/receipts').glob('*.json')) \
                if (self.repo / '.project-memory/receipts').is_dir() else set()
            self.assertEqual(before, after)
        finally:
            if previous is None:
                os.environ.pop(DISABLE_ENV, None)
            else:
                os.environ[DISABLE_ENV] = previous

    def test_trusted_mode_rejects_extra_env(self):
        with self.assertRaises(PMError) as ctx:
            run_command(self.repo, ['python3', '-c', 'print(1)'], self.base,
                        mode='trusted', extra_env={'X': '1'})
        self.assertIn('extra_env', str(ctx.exception))

    def test_resume_ignores_untrusted_verified_records(self):
        out = self.passable()
        self.verified_record(out)
        resumed = resume_run(self.repo, '325', 'run-target')
        self.assertEqual(resumed['current_verifications'], [])


if __name__ == '__main__':
    unittest.main()
