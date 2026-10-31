"""B7: the GitHub Actions runner as a second identity for approval gates.

The gate runs on ``pull_request_target`` and checks out only the base commit:
the workflow definition and the verifier both come from base, so a PR that
edits ``project_memory`` or the workflow still has to pass the same gate.  The
PR head is used only as a ``--commit`` string; it is never checked out or
executed.

The CI anchor is a public-key JSON document delivered through a repository
secret (``PROJECT_MEMORY_APPROVAL_ANCHOR_JSON``), never through the PR tree.
It is accepted only when ``GITHUB_ACTIONS`` is exactly ``true``.  That flag is
a misuse guard, not a cryptographic boundary: a local process may set any
environment variable, so local runs keep using an owner-protected file.  A
local run with its own key and its own anchor can still be ``trusted`` without
weakening the CI gate, whose anchor comes from the secret and whose code comes
from base.  ``approval verify --records-dir`` is the gate entry point: it reads
the ``approvals`` branch checkout from outside the PR tree and, under
``--require-approve``, succeeds only when one record is trusted, ``approve``
and bound to the exact PR head commit.

Static tests need no key.  Signing tests use a test-time RSA key and the shared
openssl skip semantics (``PROJECT_MEMORY_REQUIRE_OPENSSL=1`` makes a missing
binary a failure instead of a skip).
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openssl_support import require_openssl
from project_memory import authority
from project_memory.cli import main
from project_memory.coordination import attach_approval, write_approval_request

from test_authority_verifier import VECTORS

WORKFLOW = (Path(__file__).resolve().parents[1]
            / '.github' / 'workflows' / 'approval-gate.yml')
APPROVER = 'ci-approver@example.invalid'
OTHER_APPROVER = 'other-approver@example.invalid'


def ci_anchor_document(**overrides) -> dict:
    document = {
        'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
        'anchor_id': 'b7-ci-anchor', 'issuer': APPROVER,
        'algorithm': 'rsa-sha256',
        'public_key_pem': VECTORS['rsa2048']['public_key_pem'],
    }
    document.update(overrides)
    return document


class CiJsonAnchorTest(unittest.TestCase):
    """Card §4: CI-only JSON anchor, shape checks, file priority."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        self.outside = Path(self.tmp.name) / 'outside'
        self.outside.mkdir()

    def load(self, json_env=authority.TRUST_ANCHOR_JSON_ENV, document=None,
             extra_env=None):
        environment = {
            authority.ANCHOR_ENV: '',
            authority.APPROVAL_ANCHOR_ENV: '',
            authority.TRUST_ANCHOR_JSON_ENV: '',
            authority.APPROVAL_ANCHOR_JSON_ENV: '',
            authority.CI_CONTEXT_ENV: '',
            authority.TRUST_ANCHOR_JSON_ENV if json_env == authority.TRUST_ANCHOR_JSON_ENV
            else authority.APPROVAL_ANCHOR_JSON_ENV: '',
        }
        environment[json_env] = (json.dumps(document)
                                 if document is not None else '')
        environment.update(extra_env or {})
        with mock.patch.dict(os.environ, environment):
            return authority.load_anchor(self.repo, json_env=json_env)

    def test_ci_context_accepts_well_formed_json_anchor(self):
        anchor, reason = self.load(authority.TRUST_ANCHOR_JSON_ENV,
                                   ci_anchor_document(),
                                   {authority.CI_CONTEXT_ENV: 'true'})
        self.assertIsNotNone(anchor, reason)
        self.assertEqual('<env:PROJECT_MEMORY_TRUST_ANCHOR_JSON>', anchor['path'])
        self.assertEqual('ci-secret', anchor['protection'])
        self.assertEqual('b7-ci-anchor', anchor['anchor_id'])

    def test_local_json_anchor_does_not_take_effect(self):
        anchor, reason = self.load(authority.TRUST_ANCHOR_JSON_ENV,
                                   ci_anchor_document())
        self.assertIsNone(anchor, reason)
        self.assertIn('只在 CI', reason)

    def test_ci_flag_must_be_the_literal_true(self):
        anchor, reason = self.load(authority.TRUST_ANCHOR_JSON_ENV,
                                   ci_anchor_document(),
                                   {authority.CI_CONTEXT_ENV: 'false'})
        self.assertIsNone(anchor, reason)
        self.assertIn('只在 CI', reason)

    def test_ci_flag_rejects_any_other_spelling(self):
        for value in ('TRUE', 'True', ' true ', '1'):
            anchor, reason = self.load(authority.TRUST_ANCHOR_JSON_ENV,
                                       ci_anchor_document(),
                                       {authority.CI_CONTEXT_ENV: value})
            self.assertIsNone(anchor, (value, reason))
            self.assertIn('只在 CI', reason, (value, reason))
        anchor, reason = self.load(authority.TRUST_ANCHOR_JSON_ENV,
                                   ci_anchor_document(),
                                   {authority.CI_CONTEXT_ENV: 'true'})
        self.assertIsNotNone(anchor, reason)

    def test_malformed_json_anchor_is_rejected(self):
        anchor, reason = self.load(authority.TRUST_ANCHOR_JSON_ENV, None,
                                   {authority.CI_CONTEXT_ENV: 'true'})
        self.assertIsNone(anchor)
        document = ci_anchor_document()
        environment = {
            authority.ANCHOR_ENV: '',
            authority.TRUST_ANCHOR_JSON_ENV: '{not json',
            authority.CI_CONTEXT_ENV: 'true',
        }
        with mock.patch.dict(os.environ, environment):
            anchor, reason = authority.load_anchor(
                self.repo, json_env=authority.TRUST_ANCHOR_JSON_ENV)
        self.assertIsNone(anchor)
        self.assertIn('不是合法 JSON', reason)

    def test_ci_json_anchor_keeps_file_anchor_shape_checks(self):
        bad_documents = (
            ci_anchor_document(kind='other'),
            ci_anchor_document(schema_version='0.9'),
            ci_anchor_document(algorithm='ed25519'),
            ci_anchor_document(anchor_id=''),
            ci_anchor_document(issuer=''),
            ci_anchor_document(public_key_pem=''),
            [],
        )
        for document in bad_documents:
            anchor, reason = self.load(authority.TRUST_ANCHOR_JSON_ENV,
                                       document,
                                       {authority.CI_CONTEXT_ENV: 'true'})
            self.assertIsNone(anchor, (document, reason))

    def test_protected_file_anchor_wins_over_json_anchor(self):
        path = self.outside / 'anchor.json'
        document = ci_anchor_document(anchor_id='file-anchor')
        path.write_text(json.dumps(document), encoding='utf-8')
        environment = {
            authority.ANCHOR_ENV: str(path),
            authority.TRUST_ANCHOR_JSON_ENV: json.dumps(
                ci_anchor_document(anchor_id='json-anchor')),
            authority.CI_CONTEXT_ENV: 'true',
        }
        with mock.patch.dict(os.environ, environment):
            with mock.patch('project_memory.authority.anchor_is_protected',
                            return_value=(True, 'owner=test')):
                anchor, reason = authority.load_anchor(
                    self.repo, json_env=authority.TRUST_ANCHOR_JSON_ENV)
        self.assertIsNotNone(anchor, reason)
        self.assertEqual('file-anchor', anchor['anchor_id'])
        self.assertEqual(str(path.resolve()), anchor['path'])

    def test_invalid_file_anchor_fails_closed_even_with_valid_ci_json(self):
        missing = self.outside / 'missing.json'
        environment = {
            authority.ANCHOR_ENV: str(missing),
            authority.TRUST_ANCHOR_JSON_ENV: json.dumps(ci_anchor_document()),
            authority.CI_CONTEXT_ENV: 'true',
        }
        with mock.patch.dict(os.environ, environment):
            anchor, reason = authority.load_anchor(
                self.repo, json_env=authority.TRUST_ANCHOR_JSON_ENV)
        self.assertIsNone(anchor, reason)
        self.assertIn(str(missing.resolve()), reason)

    def test_unprotected_file_anchor_does_not_fall_back_to_json(self):
        path = self.outside / 'anchor.json'
        path.write_text(json.dumps(ci_anchor_document()), encoding='utf-8')
        environment = {
            authority.ANCHOR_ENV: str(path),
            authority.TRUST_ANCHOR_JSON_ENV: json.dumps(ci_anchor_document()),
            authority.CI_CONTEXT_ENV: 'true',
        }
        with mock.patch.dict(os.environ, environment):
            with mock.patch('project_memory.authority.anchor_is_protected',
                            return_value=(False, '信任锚所有者是当前用户；不能作为独立信任根')):
                anchor, reason = authority.load_anchor(
                    self.repo, json_env=authority.TRUST_ANCHOR_JSON_ENV)
        self.assertIsNone(anchor, reason)
        self.assertIn('所有者', reason)

    def test_verification_authority_uses_ci_anchor_but_not_locally(self):
        document = ci_anchor_document()
        environment = {
            authority.ANCHOR_ENV: '',
            authority.TRUST_ANCHOR_JSON_ENV: json.dumps(document),
            authority.CI_CONTEXT_ENV: 'true',
        }
        with mock.patch.dict(os.environ, environment):
            verdict = authority.verification_authority(self.repo, {})
        self.assertEqual('untrusted', verdict['status'])
        self.assertEqual('b7-ci-anchor', verdict['anchor_id'])
        with mock.patch.dict(os.environ, {**environment,
                                          authority.CI_CONTEXT_ENV: ''}):
            verdict = authority.verification_authority(self.repo, {})
        self.assertEqual('unconfigured', verdict['status'])


class _SignedFixture(unittest.TestCase):
    """A repository with two adjacent commits and a test-time RSA signer."""

    @classmethod
    def setUpClass(cls):
        cls.openssl = require_openssl('B7 CI 审批门禁测试需要测试期签名者')
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
        cls.anchor = ci_anchor_document(
            public_key_pem=public.read_text(encoding='utf-8'))
        cls.anchor_path = work / 'approver-anchor.json'
        cls.anchor_path.write_text(json.dumps(cls.anchor), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.repo = self.work / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'b7@example.invalid')
        self.git('config', 'user.name', 'B7')
        (self.repo / 'README.md').write_text('hello\n', encoding='utf-8')
        self.git('add', 'README.md')
        self.git('commit', '-qm', 'base')
        self.base = self.sha()
        (self.repo / 'next.txt').write_text('next\n', encoding='utf-8')
        self.git('add', 'next.txt')
        self.git('commit', '-qm', 'next')
        self.next_sha = self.sha()
        self.records = self.work / 'records'
        self.records.mkdir()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def sha(self):
        return self.git('rev-parse', 'HEAD').stdout.strip()

    def sign(self, payload: bytes, name='sig', key=None) -> bytes:
        payload_file = self.work / f'{name}.payload'
        signature_file = self.work / f'{name}.sig'
        payload_file.write_bytes(payload)
        subprocess.run([self.openssl, 'dgst', '-sha256', '-sign',
                        str(key or self.key), '-out', str(signature_file),
                        str(payload_file)], check=True, capture_output=True)
        return signature_file.read_bytes()

    def make_record(self, commit, decision='approve', approver=APPROVER,
                    key=None, name='record'):
        request = write_approval_request(
            self.repo, commit, approver, decision, 'B7 门禁测试',
            output=self.work / f'{name}-request.json')
        payload = authority.signed_record_payload(request['request'])
        signature_path = self.work / f'{name}.sig'
        signature_path.write_bytes(self.sign(payload, name, key))
        output = self.records / f"{commit}-{request['approval_id']}.json"
        attached = attach_approval(self.repo, request['path'], signature_path,
                                   self.anchor_path, output=output)
        self.assertTrue(attached['signature_valid'])
        return output

    def forged_record(self, commit):
        """A record signed by another key, written without attach approval."""
        request = write_approval_request(
            self.repo, commit, APPROVER, 'approve', '伪造签名',
            output=self.work / 'forged-request.json')
        payload = authority.signed_record_payload(request['request'])
        record = dict(request['request'])
        record['authority'] = {
            'status': 'signed', 'anchor_id': self.anchor['anchor_id'],
            'issuer': APPROVER, 'algorithm': 'rsa-sha256',
            'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'signature_b64': base64.b64encode(
                self.sign(payload, 'forged', self.other_key)).decode('ascii'),
        }
        path = self.records / f"{commit}-{record['approval_id']}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        return path

    @contextlib.contextmanager
    def ci_anchor(self):
        with mock.patch.dict(os.environ, {
            authority.ANCHOR_ENV: '',
            authority.APPROVAL_ANCHOR_ENV: '',
            authority.CI_CONTEXT_ENV: 'true',
            authority.APPROVAL_ANCHOR_JSON_ENV: json.dumps(self.anchor),
        }):
            yield

    def verify(self, commit, records_dir=None, require_approve=True):
        argv = ['approval', 'verify', '--repo', str(self.repo),
                '--records-dir', str(records_dir or self.records),
                '--commit', commit]
        if require_approve:
            argv.append('--require-approve')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()


class RecordsDirVerifyTest(_SignedFixture):
    """Card §4: gate semantics for a records directory."""

    def test_one_valid_approval_passes(self):
        self.make_record(self.base)
        with self.ci_anchor():
            code, output = self.verify(self.base)
        report = json.loads(output)
        self.assertEqual(0, code, output)
        self.assertTrue(report['approved'])
        self.assertEqual(1, report['scanned'])
        self.assertTrue(report['records'][0]['verified'])
        self.assertEqual('trusted', report['records'][0]['authority_status'])

    def test_empty_directory_fails(self):
        with self.ci_anchor():
            code, output = self.verify(self.base)
        report = json.loads(output)
        self.assertEqual(2, code, output)
        self.assertFalse(report['approved'])
        self.assertIn('目录中没有审批记录', ' '.join(report['problems']))

    def test_empty_directory_without_require_approve_reports_and_exits_zero(self):
        with self.ci_anchor():
            code, output = self.verify(self.base, require_approve=False)
        report = json.loads(output)
        self.assertEqual(0, code, output)
        self.assertFalse(report['approved'])
        self.assertEqual(0, report['scanned'])
        self.assertIn('目录中没有审批记录', ' '.join(report['problems']))

    def test_missing_directory_fails_closed(self):
        with self.ci_anchor():
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(['approval', 'verify', '--repo', str(self.repo),
                             '--records-dir', str(self.work / 'absent'),
                             '--commit', self.base, '--require-approve'])
        self.assertEqual(1, code)

    def test_record_for_another_commit_fails(self):
        self.make_record(self.next_sha)
        with self.ci_anchor():
            code, output = self.verify(self.base)
        report = json.loads(output)
        self.assertEqual(2, code, output)
        self.assertFalse(report['approved'])
        self.assertTrue(report['records'][0]['trusted'])
        self.assertIn(self.base, ' '.join(report['records'][0]['problems']))

    def test_reject_decision_does_not_pass_the_gate(self):
        self.make_record(self.base, decision='reject')
        with self.ci_anchor():
            code, output = self.verify(self.base)
        report = json.loads(output)
        self.assertEqual(2, code, output)
        self.assertFalse(report['approved'])
        self.assertIn('approve', ' '.join(report['records'][0]['problems']))

    def test_forged_signature_fails(self):
        self.forged_record(self.base)
        with self.ci_anchor():
            code, output = self.verify(self.base)
        report = json.loads(output)
        self.assertEqual(2, code, output)
        self.assertFalse(report['approved'])
        self.assertIn('签名', ' '.join(report['records'][0]['problems']))

    def test_missing_anchor_fails_with_reason(self):
        self.make_record(self.base)
        with mock.patch.dict(os.environ, {
                authority.APPROVAL_ANCHOR_ENV: '',
                authority.APPROVAL_ANCHOR_JSON_ENV: '',
                authority.CI_CONTEXT_ENV: 'true'}):
            code, output = self.verify(self.base)
        report = json.loads(output)
        self.assertEqual(2, code, output)
        self.assertIn('信任锚', ' '.join(report['records'][0]['problems']))

    def test_negative_control_edit_commit_then_restore(self):
        path = self.make_record(self.base)
        original = path.read_text(encoding='utf-8')
        record = json.loads(original)
        with self.ci_anchor():
            before_code, before_output = self.verify(self.base)
            record['commit_sha'] = self.next_sha
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                            encoding='utf-8')
            broken_code, broken_output = self.verify(self.base)
            path.write_text(original, encoding='utf-8')
            after_code, after_output = self.verify(self.base)
        print(f'negative-control before: exit={before_code} '
              f"approved={json.loads(before_output)['approved']}")
        print(f'negative-control edited: exit={broken_code} '
              f"problems={json.loads(broken_output)['records'][0]['problems']}")
        print(f'negative-control restored: exit={after_code} '
              f"approved={json.loads(after_output)['approved']}")
        self.assertEqual(0, before_code)
        self.assertEqual(2, broken_code)
        self.assertEqual(0, after_code)

    def test_single_record_mode_is_unchanged(self):
        path = self.make_record(self.base)
        with self.ci_anchor():
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(['approval', 'verify', '--repo', str(self.repo),
                             '--record', str(path), '--commit', self.base])
                wrong = main(['approval', 'verify', '--repo', str(self.repo),
                              '--record', str(path), '--commit', self.next_sha])
        self.assertEqual(0, code)
        self.assertEqual(2, wrong)

    def test_require_approve_is_rejected_in_single_record_mode(self):
        path = self.make_record(self.base)
        stderr = io.StringIO()
        with self.ci_anchor(), contextlib.redirect_stderr(stderr):
            code = main(['approval', 'verify', '--repo', str(self.repo),
                         '--record', str(path), '--commit', self.base,
                         '--require-approve'])
        self.assertEqual(1, code)
        self.assertIn('--records-dir', stderr.getvalue())


class WorkflowStaticTest(unittest.TestCase):
    """Card §5: base-only checkout, pinned, read-only, no PR code execution."""

    def setUp(self):
        self.text = WORKFLOW.read_text(encoding='utf-8')
        self.lines = self.text.splitlines()

    def line_index(self, needle):
        return next(i for i, line in enumerate(self.lines) if needle in line)

    def test_workflow_exists_and_parses(self):
        self.assertTrue(WORKFLOW.is_file())
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml is None:
            self.skipTest('PyYAML 未安装；仅做文本静态检查')
        document = yaml.safe_load(self.text)
        self.assertEqual('approval-gate', document['name'])
        # PyYAML resolves the bare YAML 1.1 key ``on`` to boolean True.
        triggers = document.get('on', document.get(True))
        self.assertIsInstance(triggers, dict)
        self.assertIn('pull_request_target', triggers)
        self.assertIn('workflow_dispatch', triggers)
        self.assertNotIn('pull_request', triggers)
        target = triggers['pull_request_target']
        self.assertEqual(['dev/v1.0'], target['branches'])
        self.assertEqual(['opened', 'synchronize', 'reopened', 'edited'],
                         target['types'])

    def test_uses_pull_request_target_without_a_pull_request_trigger(self):
        self.assertIn('pull_request_target:', self.text)
        self.assertIsNone(
            re.search(r'^\s*pull_request:\s*$', self.text, re.MULTILINE),
            '不得保留独立的 pull_request: 触发；PR 可能用它运行被篡改的同名工作流')

    def test_actions_are_pinned_to_40_hex_commit_shas(self):
        uses = re.findall(r'uses:\s*(\S+)', self.text)
        self.assertTrue(uses)
        for reference in uses:
            name, _, revision = reference.partition('@')
            self.assertRegex(revision, r'^[0-9a-f]{40}$',
                             f'{name} 必须按提交 SHA 固定')

    def test_permissions_are_read_only(self):
        block = re.search(r'^permissions:\n((?:[ \t]+.*\n)+)', self.text,
                          re.MULTILINE)
        self.assertIsNotNone(block)
        self.assertNotIn('write', block.group(1))
        self.assertIn('contents: read', block.group(1))
        self.assertNotIn('pull-requests', block.group(1))
        self.assertNotIn('checks', block.group(1))

    def test_checkout_uses_the_pull_request_base(self):
        start = self.line_index('uses: actions/checkout@')
        ref_line = next(line for line in self.lines[start:start + 6]
                        if 'ref:' in line)
        self.assertIn('github.event.pull_request.base.sha', ref_line)
        self.assertNotIn('pull_request.head.sha', ref_line)
        self.assertNotIn('refs/pull/', ref_line)

    def test_no_checkout_uses_the_pr_head(self):
        refs = [line for line in self.lines if re.search(r'^\s+ref:\s', line)]
        self.assertTrue(refs)
        for line in refs:
            self.assertNotIn('pull_request.head.sha', line)
            self.assertNotIn('refs/pull/', line)

    def test_checkout_does_not_persist_credentials(self):
        self.assertIn('persist-credentials: false', self.text)

    def test_steps_use_bash(self):
        self.assertIn('shell: bash', self.text)

    def test_resolves_head_from_event_or_authenticated_dispatch_fetch(self):
        self.assertIn('EVENT_HEAD: ${{ github.event.pull_request.head.sha }}',
                      self.text)
        self.assertIn('refs/pull/$PR_NUMBER/head', self.text)
        self.assertIn("git rev-parse 'FETCH_HEAD^{commit}'", self.text)
        self.assertIn("grep -Eq '^[0-9a-f]{40}$'", self.text)

    def test_approvals_fetch_authenticates_and_is_not_swallowed(self):
        index = self.line_index(
            'origin approvals:refs/remotes/origin/approvals')
        window = '\n'.join(self.lines[max(0, index - 5):index + 2])
        self.assertIn('http.extraheader', window)
        self.assertIn('::add-mask::', window)
        self.assertNotIn('|| true', window)

    def test_no_pip_install_or_pytest(self):
        self.assertNotIn('pip install', self.text)
        self.assertNotIn('pytest', self.text)

    def test_gate_runs_records_dir_verify_for_the_resolved_head(self):
        self.assertIn('echo "PM_HEAD=$PM_HEAD" >> "$GITHUB_ENV"', self.text)
        self.assertIn('--records-dir .pm-approvals/records', self.text)
        self.assertIn('--commit "$PM_HEAD" --require-approve', self.text)
        self.assertIn('PROJECT_MEMORY_APPROVAL_ANCHOR_JSON', self.text)


if __name__ == '__main__':
    unittest.main()
