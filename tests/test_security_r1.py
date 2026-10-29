"""R1: release gates for vacuous required sets and missing openssl.

A Goal whose required set is empty (hand-edited ``required=false`` or deleted
required criteria) must fail closed: ``evaluate`` reports
``insufficient_evidence`` with a machine-readable ``no_required_criteria``
marker, ``goal show`` stays readable and flags the same problem, and
``transition --to achieved`` is refused with an audit entry.

The openssl switch is covered separately: a missing binary may skip locally,
but ``PROJECT_MEMORY_REQUIRE_OPENSSL`` must turn that skip into a failure.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openssl_support import REQUIRE_ENV, openssl_required, require_openssl
from project_memory.common import PMError, git_sha
from project_memory.coordination import (create_goal, evaluate_goal, goal_show,
                                         load_goal, transition_goal)

GOAL = 'G-R1'
CRITERION = '模块通过测试'
OPTIONAL = '可选的附加检查'


class EmptyRequiredSetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'r1@example.invalid')
        self.git('config', 'user.name', 'R1')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        self.git('add', 'README.md')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)
        self.audit = self.repo / '.project-memory/audit/verification_attempts.jsonl'
        self.request = self.repo / '.project-memory/audit/head.request.json'

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def make_goal(self, criteria=None):
        return create_goal(
            self.repo, GOAL, GOAL + ' title', 'background', 'outcome',
            'owner@example.com',
            criteria or [{'id': 'C1', 'statement': CRITERION, 'required': True,
                          'evidence': []},
                         {'id': 'C2', 'statement': OPTIONAL, 'required': False,
                          'evidence': []}])

    def edit_goal(self, mutate):
        path = self.repo / '.project-memory/goals' / f'{GOAL}.json'
        goal = json.loads(path.read_text(encoding='utf-8'))
        mutate(goal)
        path.write_text(json.dumps(goal, ensure_ascii=False, indent=2),
                        encoding='utf-8')

    def to_evaluating(self):
        transition_goal(self.repo, GOAL, 'approved',
                        approved_by='human-lead@example.com')
        transition_goal(self.repo, GOAL, 'active')
        transition_goal(self.repo, GOAL, 'evaluating')

    def audit_entries(self):
        return [json.loads(line) for line in
                self.audit.read_text(encoding='utf-8').splitlines() if line.strip()]

    def assert_fail_closed(self):
        evaluation = evaluate_goal(self.repo, GOAL)
        self.assertFalse(evaluation['satisfied'])
        self.assertEqual(evaluation['evaluation_status'], 'insufficient_evidence')
        self.assertTrue(evaluation['no_required_criteria'])
        self.assertIn('no_required_criteria', evaluation['status_problems'])
        self.assertNotEqual(evaluation['effective_status'], 'achieved')

        shown = goal_show(self.repo, GOAL)
        self.assertEqual(shown['goal']['id'], GOAL)
        self.assertIn('no_required_criteria', shown['status_problems'])
        self.assertNotEqual(shown['effective_status'], 'achieved')

    def assert_transition_refused(self):
        self.to_evaluating()
        before = self.audit_entries()
        with self.assertRaises(PMError) as ctx:
            transition_goal(self.repo, GOAL, 'achieved',
                            approved_by='human-lead@example.com')
        self.assertIn('insufficient_evidence', str(ctx.exception))
        self.assertEqual(load_goal(self.repo, GOAL)['status'], 'evaluating')
        self.assertFalse(self.request.exists())
        after = self.audit_entries()
        self.assertEqual(len(after), len(before) + 1)
        entry = after[-1]
        self.assertEqual(entry['outcome'], 'rejected')
        self.assertEqual(entry['reason'], 'goal_achieved_unsatisfied')
        self.assertTrue(entry['no_required_criteria'])
        self.assertEqual(entry['evaluation_status'], 'insufficient_evidence')

    def test_flipping_only_required_criterion_fails_closed(self):
        self.make_goal()
        self.edit_goal(lambda goal: goal['success_criteria'][0].update(required=False))
        self.assert_fail_closed()
        self.assert_transition_refused()

    def test_deleting_all_required_criteria_fails_closed(self):
        self.make_goal()
        self.edit_goal(lambda goal: goal.__setitem__(
            'success_criteria',
            [criterion for criterion in goal['success_criteria']
             if criterion['id'] != 'C1']))
        self.assert_fail_closed()
        self.assert_transition_refused()

    def test_create_still_requires_a_required_criterion(self):
        with self.assertRaises(PMError) as ctx:
            create_goal(self.repo, 'G-EMPTY', 'empty', '', 'outcome',
                        'owner@example.com', [])
        self.assertIn('必达的成功标准', str(ctx.exception))
        with self.assertRaises(PMError):
            create_goal(self.repo, 'G-OPT', 'optional only', '', 'outcome',
                        'owner@example.com',
                        [{'id': 'C1', 'statement': CRITERION,
                          'required': False, 'evidence': []}])


class OpensslSwitchTest(unittest.TestCase):
    def test_truthy_values_are_case_insensitive(self):
        for value in ('1', 'true', 'TRUE', 'Yes', 'yes'):
            with mock.patch.dict(os.environ, {REQUIRE_ENV: value}, clear=False):
                self.assertTrue(openssl_required(), value)
        for value in ('', '0', 'false', 'no', 'off'):
            with mock.patch.dict(os.environ, {REQUIRE_ENV: value}, clear=False):
                self.assertFalse(openssl_required(), value)

    def test_missing_openssl_skips_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(REQUIRE_ENV, None)
            with mock.patch('openssl_support.openssl_path', return_value=None):
                with self.assertRaises(unittest.SkipTest) as ctx:
                    require_openssl('R1 签名测试')
        self.assertIn('openssl', str(ctx.exception))

    def test_missing_openssl_fails_when_required(self):
        with mock.patch.dict(os.environ, {REQUIRE_ENV: 'yes'}, clear=False):
            with mock.patch('openssl_support.openssl_path', return_value=None):
                with self.assertRaises(AssertionError) as ctx:
                    require_openssl('R1 签名测试')
        message = str(ctx.exception)
        self.assertIn('openssl', message)
        self.assertIn(REQUIRE_ENV, message)


if __name__ == '__main__':
    unittest.main()
