"""B0: portable repository identity for execution receipts.

Pins three behaviours:

* the same repository copied to another checkout path keeps the same identity,
  so a receipt and its verification record stay current there (AC-1);
* a repository with a different remote or a different root commit rejects the
  other repository's receipt (AC-2);
* schema 1.0 receipts stay usable at their original path only, and are labelled
  ``legacy_path_bound`` instead of passing silently across paths (AC-4).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from project_memory import execution
from project_memory.coordination import (create_goal, finish_run, start_run,
                                         verify_run, _verification_current)
from project_memory.execution import run_command, verify_receipt

CRITERION = '模块通过测试'
REMOTE_A = 'https://github.com/pilot-org/repo-a'
REMOTE_B = 'https://github.com/pilot-org/repo-b'


class RepoIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'path-a'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'b0@example.invalid')
        self.git('config', 'user.name', 'B0')
        (self.repo / 'README.md').write_text('b0\n', encoding='utf-8')
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_smoke.py').write_text(
            'def test_ok():\n    assert True\n', encoding='utf-8')
        self.git('add', 'README.md', 'tests/test_smoke.py')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def copy_to(self, name):
        target = self.root / name
        shutil.copytree(self.repo, target)
        return target

    def git_at(self, path, *args):
        return subprocess.run(['git', '-C', str(path), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def make_receipt(self):
        return run_command(self.repo, [sys.executable, '-c',
                                       "import sys; print('1 passed'); sys.exit(0)"],
                           self.base, executed_by='b0-test')

    # ------------------------------------------------------------ AC-1 / AC-3

    def test_identity_has_no_checkout_path(self):
        out = self.make_receipt()
        identity = execution.repo_identity(self.repo)
        self.assertEqual(identity['kind'], 'root-only')
        self.assertIsNone(identity['remote'])
        self.assertEqual(identity['root_commits'], [self.base])
        self.assertEqual(identity['id'], execution.repo_id(self.repo))
        self.assertNotIn(str(self.repo), json.dumps(identity))
        self.assertNotIn('path-a', json.dumps(identity))
        self.assertEqual(out['receipt']['repo_id'], identity['id'])
        self.assertEqual(out['receipt']['schema_version'], '1.1')
        self.assertEqual(out['receipt']['repo_identity']['kind'], 'root-only')

    def test_copied_repository_keeps_identity(self):
        out = self.make_receipt()
        other = self.copy_to('path-b')
        self.assertEqual(execution.repo_id(self.repo), execution.repo_id(other))
        checked = verify_receipt(other, out['path'])
        self.assertTrue(checked['valid'], checked['problems'])
        self.assertTrue(checked['identity']['portable'])
        self.assertFalse(checked['legacy_path_bound'])

    def test_relative_and_absolute_paths_agree(self):
        out = self.make_receipt()
        # verify_receipt resolves the repo, so a relative spelling must agree too.
        rel = Path(os.path.relpath(self.repo, Path.cwd()))
        self.assertTrue(verify_receipt(rel, out['path'])['valid'])
        self.assertTrue(verify_receipt(Path(self.repo), out['path'])['valid'])

    def test_remote_normalisation_ignores_scheme_and_user(self):
        self.git('remote', 'add', 'origin', REMOTE_A)
        identity_https = execution.repo_identity(self.repo)
        self.assertEqual(identity_https['kind'], 'remote+root')
        self.assertEqual(identity_https['remote'], 'github.com/pilot-org/repo-a')
        self.git('remote', 'set-url', 'origin', 'git@github.com:pilot-org/repo-a.git')
        self.assertEqual(execution.repo_id(self.repo), identity_https['id'])
        self.git('remote', 'set-url', 'origin', REMOTE_A + '.git/')
        self.assertEqual(execution.repo_id(self.repo), identity_https['id'])

    def test_local_path_remote_falls_back_to_root_only(self):
        self.git('remote', 'add', 'origin', str(self.root / 'upstream'))
        identity = execution.repo_identity(self.repo)
        self.assertEqual(identity['kind'], 'root-only')
        self.assertIsNone(identity['remote'])
        self.assertNotIn('upstream', json.dumps(identity))

    def test_verification_stays_current_after_copy(self):
        create_goal(self.repo, 'G-1', 'G-1 title', 'background', 'outcome',
                    'owner', [CRITERION])
        out = run_command(self.repo, [sys.executable, '-c',
                                      "import sys; print('1 passed'); sys.exit(0)"],
                          self.base, executed_by='dev-agent')
        start_run(self.repo, 'G-1', '325', 'run-target', 'dev-agent', 'qodercn',
                  'executor-model', base_sha=self.base, role='executor')
        finish_run(self.repo, '325', 'run-target', ['implemented'], ['verify'],
                   head_sha=self.base,
                   tests=[{'command': out['receipt']['command'], 'exit_code': 0,
                           'log': out['log']}])
        start_run(self.repo, 'G-1', '325', 'run-verifier', 'verifier-agent', 'qodercn',
                  'verifier-model', base_sha=self.base, role='verifier')
        mapping = {'criteria': [{
            'criterion_id': 'C1', 'goal_id': 'G-1', 'task_id': '325',
            'criterion_description': CRITERION,
            'target_repository': str(self.repo), 'target_commit_sha': self.base,
            'evidence_id': 'EV-1', 'evidence_source': 'test',
            'evidence_command': out['receipt']['command'], 'evidence_log': out['log'],
            'evidence_exit_code': 0, 'evidence_receipt': out['path'],
            'execution_status': 'passed', 'coverage_claim': '覆盖对应标准',
            'coverage_review_status': 'confirmed',
            'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}
        result = verify_run(self.repo, 'run-target', 'run-verifier', 'acceptance',
                            'pass', 'locally_observed', test_receipt=out['path'],
                            criterion_evidence=mapping)
        self.assertTrue(_verification_current(self.repo, result['verification']))

        other = self.copy_to('path-b')
        self.assertTrue(verify_receipt(other, out['path'])['valid'])
        self.assertTrue(_verification_current(other, result['verification']))

    # ------------------------------------------------------------ AC-2

    def test_different_root_commit_is_rejected(self):
        out = self.make_receipt()
        other = self.root / 'other-repo'
        other.mkdir()
        self.git_at(other, 'init', '-q')
        self.git_at(other, 'config', 'user.email', 'other@example.invalid')
        self.git_at(other, 'config', 'user.name', 'Other')
        (other / 'README.md').write_text('different history\n', encoding='utf-8')
        self.git_at(other, 'add', 'README.md')
        self.git_at(other, 'commit', '-qm', 'other base')
        target = other / out['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((self.repo / out['path']).read_text(encoding='utf-8'),
                          encoding='utf-8')
        checked = verify_receipt(other, out['path'])
        self.assertFalse(checked['valid'])
        self.assertTrue(any('仓库' in problem for problem in checked['problems']),
                        checked['problems'])

    def test_same_root_different_remote_is_rejected(self):
        self.git('remote', 'add', 'origin', REMOTE_A)
        out = self.make_receipt()
        other = self.copy_to('path-b')
        self.git_at(other, 'remote', 'set-url', 'origin', REMOTE_B)
        self.assertNotEqual(execution.repo_id(self.repo), execution.repo_id(other))
        checked = verify_receipt(other, out['path'])
        self.assertFalse(checked['valid'])
        self.assertTrue(any('仓库' in problem for problem in checked['problems']),
                        checked['problems'])

    def test_rewritten_identity_fields_are_rejected(self):
        self.git('remote', 'add', 'origin', REMOTE_A)
        out = self.make_receipt()
        path = self.repo / out['path']
        receipt = json.loads(path.read_text(encoding='utf-8'))
        receipt['repo_identity']['remote'] = 'github.com/pilot-org/repo-b'
        receipt['content_sha256'] = execution._canonical_receipt_digest(receipt)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        checked = verify_receipt(self.repo, out['path'])
        self.assertFalse(checked['valid'])
        self.assertTrue(any('repo_identity.remote' in problem
                            for problem in checked['problems']), checked['problems'])

    # ------------------------------------------------------------ AC-4

    def downgrade_to_legacy(self, out):
        path = self.repo / out['path']
        receipt = json.loads(path.read_text(encoding='utf-8'))
        receipt['schema_version'] = '1.0'
        receipt.pop('repo_identity', None)
        receipt['repo_id'] = execution._legacy_repo_id(self.repo)
        receipt['content_sha256'] = execution._canonical_receipt_digest(receipt)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2),
                        encoding='utf-8')

    def test_legacy_receipt_works_only_at_original_path(self):
        out = self.make_receipt()
        self.downgrade_to_legacy(out)
        checked = verify_receipt(self.repo, out['path'])
        self.assertTrue(checked['valid'], checked['problems'])
        self.assertTrue(checked['legacy_path_bound'])
        self.assertEqual(checked['identity']['kind'], 'legacy_path_bound')
        self.assertFalse(checked['identity']['portable'])

        other = self.copy_to('path-b')
        moved = verify_receipt(other, out['path'])
        self.assertFalse(moved['valid'])
        self.assertTrue(any('legacy' in problem for problem in moved['problems']),
                        moved['problems'])

    def test_unknown_schema_is_rejected(self):
        out = self.make_receipt()
        path = self.repo / out['path']
        receipt = json.loads(path.read_text(encoding='utf-8'))
        receipt['schema_version'] = '0.9'
        receipt['content_sha256'] = execution._canonical_receipt_digest(receipt)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        checked = verify_receipt(self.repo, out['path'])
        self.assertFalse(checked['valid'])
        self.assertTrue(any('schema_version' in problem for problem in checked['problems']))


if __name__ == '__main__':
    unittest.main()
