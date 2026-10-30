"""B-9: verify reads the real PR CI outcome instead of trusting a declaration.

The tests split in two layers:

* ``PullRequestCiStatusTest`` drives ``GitHubReader.pull_request_ci_status``
  against canned API responses (no network).
* ``ExternalVerificationTest`` runs the whole ``verify`` path with
  ``GITHUB_REPOSITORY`` and a patched reader.  A green CI on the verified commit
  raises trust to ``externally_verified``; a failed/pending CI, a decoy head SHA,
  a missing repository, or an API error all degrade to ``agent_claimed``.

Every integration assertion also proves the safety property: even a fully green
external check never sets ``verified`` or satisfies a Goal.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project_memory.cli import main, parser
from project_memory.common import PMError, git_sha
from project_memory.coordination import (create_goal, evaluate_goal, finish_run,
                                         start_run, verify_run)
from project_memory.execution import run_command
from project_memory.gh import GitHubReader

GOAL = 'G-1'
TASK = '325'
CRITERION = '模块通过测试'
DECOY_SHA = 'f' * 40


def green_status(head_sha):
    return {'head_sha': head_sha, 'status': 'success',
            'runs': [{'name': 'gate', 'conclusion': 'success',
                      'status': 'completed',
                      'html_url': 'https://example.invalid/run/1'}],
            '_provenance': 'github_api'}


class PullRequestCiStatusTest(unittest.TestCase):
    def reader(self, pull, checks):
        responses = {'/repos/test/repo/pulls/7': pull}
        head_sha = (pull.get('head') or {}).get('sha')
        if head_sha:
            responses[f'/repos/test/repo/commits/{head_sha}/check-runs?per_page=100'] = checks

        class StubReader(GitHubReader):
            def get(inner, endpoint):
                return responses[endpoint]

        return StubReader('test/repo', token='fake')

    def status(self, conclusions):
        runs = [{'name': f'job-{index}', 'status': 'completed',
                 'conclusion': conclusion, 'html_url': None}
                for index, conclusion in enumerate(conclusions)]
        return self.reader({'head': {'sha': 'a' * 40}},
                           {'total_count': len(runs), 'check_runs': runs}
                           ).pull_request_ci_status(7)

    def test_all_success_is_success(self):
        result = self.status(['success', 'success'])
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['head_sha'], 'a' * 40)
        self.assertEqual(len(result['runs']), 2)
        self.assertEqual(result['_provenance'], 'github_api')
        self.assertFalse(result['truncated'])

    def test_any_failure_is_failure(self):
        self.assertEqual(self.status(['success', 'failure'])['status'], 'failure')

    def test_incomplete_run_is_pending(self):
        runs = [{'name': 'gate', 'status': 'in_progress', 'conclusion': None,
                 'html_url': None}]
        result = self.reader({'head': {'sha': 'b' * 40}},
                             {'total_count': 1, 'check_runs': runs}
                             ).pull_request_ci_status(7)
        self.assertEqual(result['status'], 'pending')

    def test_failure_dominates_pending(self):
        runs = [{'name': 'fail', 'status': 'completed', 'conclusion': 'failure'},
                {'name': 'running', 'status': 'in_progress', 'conclusion': None}]
        result = self.reader({'head': {'sha': 'c' * 40}},
                             {'total_count': 2, 'check_runs': runs}
                             ).pull_request_ci_status(7)
        self.assertEqual(result['status'], 'failure')

    def test_no_check_runs_is_error_not_success(self):
        result = self.status([])
        self.assertEqual(result['status'], 'error')

    def test_non_success_conclusion_is_not_green(self):
        # Cancelled/skipped/neutral runs are deliberately treated as not green:
        # only an explicit success set may raise trust.
        self.assertEqual(self.status(['success', 'skipped'])['status'], 'failure')
        self.assertEqual(self.status(['neutral'])['status'], 'failure')

    def test_truncated_check_run_list_is_error(self):
        runs = [{'name': f'job-{index}', 'status': 'completed', 'conclusion': 'success'}
                for index in range(100)]
        result = self.reader({'head': {'sha': 'd' * 40}},
                             {'total_count': 101, 'check_runs': runs}
                             ).pull_request_ci_status(7)
        self.assertEqual(result['status'], 'error')
        self.assertTrue(result['truncated'])

    def test_invalid_pr_number_is_rejected(self):
        reader = GitHubReader('test/repo', token='fake')
        for value in (0, -1, True, '7'):
            with self.assertRaises(PMError):
                reader.pull_request_ci_status(value)

    def test_missing_head_sha_is_rejected(self):
        with self.assertRaises(PMError):
            self.reader({'head': {}}, {}).pull_request_ci_status(7)


class ExternalVerificationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'b9@example.invalid')
        self.git('config', 'user.name', 'B9')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        self.git('add', 'README.md')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)
        create_goal(self.repo, GOAL, 'B9 goal', 'background', 'outcome', 'owner',
                    [CRITERION])
        start_run(self.repo, GOAL, TASK, 'run-target', 'dev-agent', 'qodercn', 'auto',
                  base_sha=self.base)
        finish_run(self.repo, TASK, 'run-target', ['implemented'], ['verify'],
                   head_sha=self.base)
        start_run(self.repo, GOAL, TASK, 'run-verifier', 'verifier-agent', 'qodercn',
                  'auto', base_sha=self.base, role='verifier')
        self.mapping = [{
            'criterion_id': 'C1',
            'goal_id': GOAL,
            'task_id': TASK,
            'criterion_description': CRITERION,
            'target_repository': str(self.repo),
            'target_commit_sha': self.base,
            'evidence_id': 'EV-CI-1',
            'evidence_source': 'ci',
            'evidence_ci_url': 'https://example.invalid/run/1',
            'evidence_ci_status': 'passed',
            'execution_status': 'passed',
            'coverage_claim': 'CI 覆盖该标准',
            'coverage_review_status': 'confirmed',
            'independent_verifier': 'verifier-agent',
            'verification_result': 'pass',
        }]

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def verify(self, ci_status, mapping=None, evidence_level='externally_verified',
               pr_number=42, test_receipt=None):
        environment = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_TOKEN': 'secret-token'}
        with mock.patch.dict(os.environ, environment, clear=False):
            with mock.patch.object(GitHubReader, 'pull_request_ci_status',
                                   return_value=ci_status):
                return verify_run(self.repo, 'run-target', 'run-verifier', 'b9 check',
                                  'pass', evidence_level, pr_number=pr_number,
                                  test_receipt=test_receipt,
                                  criterion_evidence=mapping or self.mapping)

    def receipt(self):
        return run_command(self.repo, [sys.executable, '-c',
                                       "import sys; print('1 passed'); sys.exit(0)"],
                           self.base, executed_by='b9-harness')

    def test_green_ci_on_verified_commit_raises_trust(self):
        result = self.verify(green_status(self.base))
        self.assertFalse(result['verified'])
        self.assertEqual(result['status'], 'MANUAL_REVIEW_REQUIRED')
        record = result['verification']
        self.assertEqual(record['trust_level'], 'externally_verified')
        self.assertEqual(record['mapping_status'], 'review_required')
        entry = record['criterion_evidence'][0]
        self.assertEqual(entry['observed_level'], 'externally_verified')
        self.assertTrue(entry['external_ci_verified'])
        self.assertFalse(entry['evidence_matched'])
        self.assertEqual(entry['evidence_state'], 'MANUAL_REVIEW_REQUIRED')
        ci = record['checks']['ci']
        self.assertEqual(ci['provenance'], 'github_api')
        self.assertEqual(ci['status'], 'success')
        self.assertTrue(ci['head_sha_matches_target'])
        self.assertEqual(ci['pr'], 42)
        self.assertEqual(ci['repository'], 'owner/repo')
        self.assertEqual(ci['fetch'], 'ok')
        self.assertNotIn('secret-token', json.dumps(record))
        self.assertFalse(evaluate_goal(self.repo, GOAL)['satisfied'])
        # D-2: the user-facing caveat must describe the new, limited meaning of
        # external evidence instead of claiming the level is no longer accepted.
        self.assertIn('不证明语义覆盖', result['caveat'])
        self.assertIn('review 证据仍只是声明', result['caveat'])

    def test_decoy_head_sha_degrades_to_agent_claimed(self):
        # Negative control: a green CI for a different, non-empty commit must not
        # be accepted for this commit.
        result = self.verify(green_status(DECOY_SHA))
        self.assertIsNone(result['verification'])
        self.assertEqual(result['status'], 'PARTIAL_COVERAGE')
        entry = result['criterion_evidence'][0]
        self.assertEqual(entry['observed_level'], 'agent_claimed')
        self.assertFalse(entry['external_ci_verified'])
        self.assertEqual(result['ci']['status'], 'success')
        self.assertFalse(result['ci']['head_sha_matches_target'])

    def test_failing_ci_degrades_to_agent_claimed(self):
        status = {'head_sha': self.base, 'status': 'failure', 'runs': [],
                  '_provenance': 'github_api'}
        result = self.verify(status)
        self.assertEqual(result['status'], 'PARTIAL_COVERAGE')
        self.assertEqual(result['criterion_evidence'][0]['observed_level'], 'agent_claimed')
        self.assertEqual(result['ci']['status'], 'failure')
        self.assertTrue(result['ci']['head_sha_matches_target'])

    def test_pending_ci_degrades_to_agent_claimed(self):
        status = {'head_sha': self.base, 'status': 'pending', 'runs': [],
                  '_provenance': 'github_api'}
        result = self.verify(status)
        self.assertEqual(result['status'], 'PARTIAL_COVERAGE')
        self.assertEqual(result['criterion_evidence'][0]['observed_level'], 'agent_claimed')

    def test_missing_github_repository_degrades(self):
        status = green_status(self.base)
        with mock.patch.dict(os.environ, {'GITHUB_TOKEN': 'secret-token'}, clear=False):
            os.environ.pop('GITHUB_REPOSITORY', None)
            with mock.patch.object(GitHubReader, 'pull_request_ci_status',
                                   return_value=status) as fetch:
                result = verify_run(self.repo, 'run-target', 'run-verifier', 'b9 check',
                                    'pass', 'externally_verified', pr_number=42,
                                    criterion_evidence=self.mapping)
        fetch.assert_not_called()
        self.assertEqual(result['status'], 'PARTIAL_COVERAGE')
        self.assertEqual(result['criterion_evidence'][0]['observed_level'], 'agent_claimed')
        ci = result['ci']
        self.assertEqual(ci['provenance'], 'none')
        self.assertEqual(ci['fetch'], 'missing_repository')
        self.assertEqual(ci['repository'], '')

    def test_api_error_degrades_without_raising(self):
        with mock.patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/repo',
                                          'GITHUB_TOKEN': 'secret-token'}, clear=False):
            with mock.patch.object(GitHubReader, 'pull_request_ci_status',
                                   side_effect=PMError('GitHub API 返回 HTTP 403')):
                result = verify_run(self.repo, 'run-target', 'run-verifier', 'b9 check',
                                    'pass', 'externally_verified', pr_number=42,
                                    criterion_evidence=self.mapping)
        self.assertEqual(result['status'], 'PARTIAL_COVERAGE')
        self.assertEqual(result['criterion_evidence'][0]['observed_level'], 'agent_claimed')
        ci = result['ci']
        self.assertEqual(ci['provenance'], 'none')
        self.assertEqual(ci['fetch'], 'api_error')
        self.assertEqual(ci['repository'], 'owner/repo')

    def test_invalid_github_repository_degrades(self):
        # D-5: a malformed owner/name must not raise or upgrade; the ci record
        # has to show the problem is configuration, not a CI result.
        for bad_slug in ('a', 'a/b/c'):
            env = {'GITHUB_REPOSITORY': bad_slug, 'GITHUB_TOKEN': 'secret-token'}
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch.object(GitHubReader, 'pull_request_ci_status',
                                       return_value=green_status(self.base)) as fetch:
                    result = verify_run(self.repo, 'run-target', 'run-verifier',
                                        'b9 check', 'pass', 'externally_verified',
                                        pr_number=42, criterion_evidence=self.mapping)
            fetch.assert_not_called()
            self.assertEqual(result['status'], 'PARTIAL_COVERAGE')
            self.assertEqual(result['criterion_evidence'][0]['observed_level'],
                             'agent_claimed')
            self.assertEqual(result['ci']['provenance'], 'none')
            self.assertEqual(result['ci']['fetch'], 'invalid_repository')
            self.assertEqual(result['ci']['repository'], bad_slug)

    def test_locally_observed_declaration_caps_green_ci_trust(self):
        # D-5: min(declared, observed) must cap a locally_observed declaration
        # even when the fetched CI is green; CI never lifts it above the claim.
        result = self.verify(green_status(self.base), evidence_level='locally_observed',
                             test_receipt=self.receipt()['path'])
        record = result['verification']
        self.assertEqual(record['evidence_level'], 'locally_observed')
        self.assertEqual(record['trust_level'], 'locally_observed')
        entry = record['criterion_evidence'][0]
        self.assertEqual(entry['observed_level'], 'externally_verified')
        self.assertTrue(entry['external_ci_verified'])
        self.assertEqual(record['checks']['ci']['fetch'], 'ok')

    def test_fail_locally_observed_keeps_locally_observed_trust(self):
        # D-1 regression lock: the non-PASS branch must keep the baseline
        # trust_level instead of echoing a stronger declared level.
        result = verify_run(self.repo, 'run-target', 'run-verifier', 'b9 check',
                            'fail', 'locally_observed',
                            test_receipt=self.receipt()['path'],
                            criterion_evidence=self.mapping)
        self.assertFalse(result['verified'])
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['verification']['trust_level'], 'locally_observed')

    def test_non_pass_externally_verified_is_rejected(self):
        # D-1/D-5: only a PASS may declare external verification; the fetch is
        # never attempted for fail/inconclusive.
        for verdict in ('fail', 'inconclusive'):
            with mock.patch.object(GitHubReader, 'pull_request_ci_status') as fetch:
                with mock.patch.dict(os.environ,
                                     {'GITHUB_REPOSITORY': 'owner/repo'},
                                     clear=False):
                    with self.assertRaises(PMError) as ctx:
                        verify_run(self.repo, 'run-target', 'run-verifier', 'b9 check',
                                   verdict, 'externally_verified', pr_number=42,
                                   criterion_evidence=self.mapping)
            fetch.assert_not_called()
            self.assertIn('只适用于 pass', str(ctx.exception))

    def test_externally_verified_without_pr_is_rejected(self):
        with self.assertRaises(PMError) as ctx:
            verify_run(self.repo, 'run-target', 'run-verifier', 'b9 check', 'pass',
                       'externally_verified', criterion_evidence=self.mapping)
        self.assertIn('externally_verified', str(ctx.exception))

    def test_declared_ci_without_external_fetch_stays_agent_claimed(self):
        # The pre-B-9 path: no --pr, so a declared CI URL/status is only a claim.
        receipt = run_command(self.repo, [sys.executable, '-c',
                                          "import sys; print('1 passed'); sys.exit(0)"],
                              self.base, executed_by='b9-harness')
        result = verify_run(self.repo, 'run-target', 'run-verifier', 'b9 check', 'pass',
                            'locally_observed', test_receipt=receipt['path'],
                            criterion_evidence=self.mapping)
        self.assertEqual(result['status'], 'PARTIAL_COVERAGE')
        entry = result['criterion_evidence'][0]
        self.assertEqual(entry['observed_level'], 'agent_claimed')
        self.assertFalse(entry['external_ci_verified'])


class CliWiringTest(unittest.TestCase):
    def test_parser_accepts_pr_and_externally_verified(self):
        args = parser().parse_args([
            'verify', '--target-run', 'a', '--verifier-run', 'b',
            '--standard', 's', '--verdict', 'pass',
            '--evidence-level', 'externally_verified', '--pr', '42'])
        self.assertEqual(args.pr_number, 42)

    def test_cli_threads_pr_into_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
            subprocess.run(['git', '-C', str(repo), 'config', 'user.email', 'x@y.invalid'],
                           check=True)
            subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'x'], check=True)
            (repo / 'README.md').write_text('hello\n', encoding='utf-8')
            subprocess.run(['git', '-C', str(repo), 'add', 'README.md'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'base'], check=True)
            base = git_sha(repo)
            create_goal(repo, GOAL, 'B9 goal', 'background', 'outcome', 'owner',
                        [CRITERION])
            start_run(repo, GOAL, TASK, 'run-target', 'dev-agent', 'qodercn', 'auto',
                      base_sha=base)
            finish_run(repo, TASK, 'run-target', ['done'], ['verify'], head_sha=base)
            start_run(repo, GOAL, TASK, 'run-verifier', 'verifier-agent', 'qodercn',
                      'auto', base_sha=base, role='verifier')
            mapping = Path(tmp) / 'mapping.json'
            mapping.write_text(json.dumps([{
                'criterion_id': 'C1', 'goal_id': GOAL, 'task_id': TASK,
                'criterion_description': CRITERION,
                'target_repository': str(repo), 'target_commit_sha': base,
                'evidence_id': 'EV-CI-1', 'evidence_source': 'ci',
                'evidence_ci_url': 'https://example.invalid/run/1',
                'evidence_ci_status': 'passed', 'execution_status': 'passed',
                'coverage_claim': 'CI 覆盖该标准', 'coverage_review_status': 'confirmed',
                'independent_verifier': 'verifier-agent', 'verification_result': 'pass',
            }], ensure_ascii=False), encoding='utf-8')
            out = io.StringIO()
            with mock.patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/repo'},
                                 clear=False):
                with mock.patch.object(GitHubReader, 'pull_request_ci_status',
                                       return_value=green_status(base)):
                    with contextlib.redirect_stdout(out):
                        code = main(['verify', '--repo', str(repo),
                                     '--target-run', 'run-target',
                                     '--verifier-run', 'run-verifier',
                                     '--standard', 'b9', '--verdict', 'pass',
                                     '--evidence-level', 'externally_verified',
                                     '--pr', '42', '--criterion-evidence',
                                     str(mapping)])
            self.assertEqual(code, 2)  # never auto-verified
            result = json.loads(out.getvalue())
            self.assertEqual(result['verification']['trust_level'],
                             'externally_verified')
            self.assertEqual(result['verification']['checks']['ci']['pr'], 42)


if __name__ == '__main__':
    unittest.main()
