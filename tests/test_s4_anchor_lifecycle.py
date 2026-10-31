"""S4-2: trust-anchor lifecycle (B-13) and the approval repository recheck.

An anchor document may carry four optional fields -- ``not_before``,
``not_after``, ``revoked_anchor_ids`` and ``fingerprint_sha256``.  They are
validated in ``authority._anchor_document`` (structure and fingerprint) and
decided in ``authority._anchor_lifecycle_problem`` (time and self-revocation),
which ``load_anchor`` runs on every trust decision.  Because every verifier in
``authority`` reads the anchor through ``load_anchor``, an expired or revoked
anchor makes approvals, verification records, evidence manifests and execution
attestations ``trusted=false`` without touching anything already written.

Test injection deliberately does *not* patch ``authority.load_anchor``: that
would bypass the code under test.  The signed tests patch
``authority._load_file_anchor`` with a loader that still runs the real
``_anchor_document`` validation, so only the path/owner checks (not part of
this card) are replaced.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from openssl_support import require_openssl
from project_memory import authority
from project_memory.cli import main
from project_memory.common import git_sha
from project_memory.coordination import (approval_authority, attach_approval,
                                         signed_record_authority,
                                         write_approval_request)
from project_memory.execution import repo_identity

APPROVER = 'approver@example.invalid'
ANCHOR_ID = 'ANCHOR-S42-TEST'
OTHER_ANCHOR_ID = 'ANCHOR-S42-DRILL'
REPOSITORY_PROBLEM = '审批记录的 repository.id 与当前仓库不一致'


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _hours(delta: float) -> str:
    """An ISO-8601 stamp relative to now, so no test expires with the calendar."""
    return _stamp(datetime.now(timezone.utc) + timedelta(hours=delta))


class AnchorDocumentStaticTest(unittest.TestCase):
    """Document-level rules that need no key and no signature."""

    def document(self, **extra):
        value = {'kind': 'project_memory_trust_anchor', 'schema_version': '1.0',
                 'anchor_id': ANCHOR_ID, 'issuer': APPROVER,
                 'algorithm': 'rsa-sha256',
                 'public_key_pem': '-----BEGIN PUBLIC KEY-----\nAAAA\n'
                                   '-----END PUBLIC KEY-----\n'}
        value.update(extra)
        return value

    def test_document_without_optional_fields_is_unchanged(self):
        anchor, reason = authority._anchor_document(self.document())
        self.assertEqual('ok', reason)
        self.assertIsNotNone(anchor)
        self.assertIsNone(authority._anchor_lifecycle_problem(anchor))

    def test_validity_window_is_a_closed_interval(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        inside = {'not_before': _stamp(now), 'not_after': _stamp(now)}
        self.assertIsNone(authority._anchor_lifecycle_problem(
            self.document(**inside), now=now))
        expired = {'not_after': _stamp(now - timedelta(seconds=1))}
        problem = authority._anchor_lifecycle_problem(
            self.document(**expired), now=now)
        self.assertIn('已过期', problem)
        pending = {'not_before': _stamp(now + timedelta(seconds=1))}
        problem = authority._anchor_lifecycle_problem(
            self.document(**pending), now=now)
        self.assertIn('尚未生效', problem)

    def test_self_revocation_is_reported_but_other_ids_are_not(self):
        revoked = self.document(revoked_anchor_ids=[ANCHOR_ID, OTHER_ANCHOR_ID])
        self.assertIn('吊销', authority._anchor_lifecycle_problem(revoked))
        other = self.document(revoked_anchor_ids=[OTHER_ANCHOR_ID])
        self.assertIsNone(authority._anchor_lifecycle_problem(other))

    def test_malformed_optional_fields_make_the_document_illegal(self):
        cases = (
            {'revoked_anchor_ids': OTHER_ANCHOR_ID},
            {'revoked_anchor_ids': ['']},
            {'revoked_anchor_ids': ['   ']},
            {'revoked_anchor_ids': [42]},
            {'revoked_anchor_ids': ['-leading-dash']},
            {'not_before': '2026-01-01T00:00:00'},
            {'not_after': 'not-a-time'},
            {'not_before': _hours(1), 'not_after': _hours(-1)},
            {'fingerprint_sha256': 'deadbeef'},
        )
        for extra in cases:
            anchor, reason = authority._anchor_document(self.document(**extra))
            self.assertIsNone(anchor, extra)
            self.assertNotEqual('ok', reason, extra)

    def test_load_anchor_document_does_not_decide_lifecycle(self):
        """``attach``/``request`` only check format and signature, never trust."""
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'revoked-anchor.json'
            revoked = self.document(revoked_anchor_ids=[ANCHOR_ID])
            path.write_text(json.dumps(revoked), encoding='utf-8')
            anchor, reason = authority.load_anchor_document(path)
            self.assertEqual('ok', reason)
            self.assertIsNotNone(anchor)
            self.assertIn('吊销', authority._anchor_lifecycle_problem(anchor))
            expired = Path(work) / 'expired-anchor.json'
            expired.write_text(json.dumps(self.document(not_after=_hours(-24))),
                               encoding='utf-8')
            anchor, reason = authority.load_anchor_document(expired)
            self.assertEqual('ok', reason)
            self.assertIn('已过期', authority._anchor_lifecycle_problem(anchor))


class AnchorLifecycleSignedTest(unittest.TestCase):
    """End-to-end anchor lifecycle with a test-time RSA key."""

    @classmethod
    def setUpClass(cls):
        cls.openssl = require_openssl('S4-2 锚生命周期测试需要测试期签名者')
        cls.keydir = tempfile.TemporaryDirectory()
        work = Path(cls.keydir.name)
        cls.key = work / 'anchor-key.pem'
        subprocess.run([cls.openssl, 'genpkey', '-algorithm', 'RSA',
                        '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(cls.key)],
                       check=True, capture_output=True)
        cls.public_path = work / 'anchor-key.pub.pem'
        subprocess.run([cls.openssl, 'pkey', '-in', str(cls.key), '-pubout',
                        '-out', str(cls.public_path)], check=True,
                       capture_output=True)
        cls.public_pem = cls.public_path.read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.repo = self.init_repo(self.work / 'repo-a', 'repo-a')
        self.base = git_sha(self.repo)
        self.anchor_doc = self.document()
        self.anchor_path = self.work / 'anchor.json'
        self.anchor_path.write_text(json.dumps(self.anchor_doc), encoding='utf-8')
        self.record_path = self.signed_approval()

    # ------------------------------------------------------------ fixtures

    def init_repo(self, path, marker):
        """A throwaway repository; ``marker`` keeps root commits distinct."""
        repo = Path(path)
        repo.mkdir(parents=True)
        self.git(repo, 'init', '-q')
        self.git(repo, 'config', 'user.email', f'{marker}@example.invalid')
        self.git(repo, 'config', 'user.name', marker)
        (repo / 'README.md').write_text(f'{marker}\n', encoding='utf-8')
        self.git(repo, 'add', 'README.md')
        self.git(repo, 'commit', '-qm', f'base {marker}')
        self.git(repo, 'remote', 'add', 'origin',
                 f'https://example.invalid/{marker}.git')
        return repo

    def git(self, repo, *args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def document(self, **extra):
        value = {'kind': 'project_memory_trust_anchor', 'schema_version': '1.0',
                 'anchor_id': ANCHOR_ID, 'issuer': APPROVER,
                 'algorithm': 'rsa-sha256', 'public_key_pem': self.public_pem}
        value.update(extra)
        return value

    def sign(self, payload: bytes, name: str = 'sig') -> bytes:
        payload_file = self.work / f'{name}.payload'
        signature_file = self.work / f'{name}.sig'
        payload_file.write_bytes(payload)
        subprocess.run([self.openssl, 'dgst', '-sha256', '-sign', str(self.key),
                        '-out', str(signature_file), str(payload_file)],
                       check=True, capture_output=True)
        return signature_file.read_bytes()

    def signed_approval(self):
        """One genuinely signed approval record, reused by every anchor variant."""
        request = write_approval_request(self.repo, self.base, APPROVER, 'approve',
                                         'S4-2 锚生命周期夹具',
                                         output=self.work / 'request.json')
        signature = self.work / 'request.sig'
        signature.write_bytes(
            self.sign(authority.signed_record_payload(request['request']), 'request'))
        attached = attach_approval(self.repo, request['path'], signature,
                                   self.anchor_path)
        self.assertTrue(attached['created'])
        return self.repo / attached['path']

    def attestation(self):
        record = {'schema_version': '1.0', 'kind': 'execution_attestation',
                  'attestation_id': 'ATT-s42', 'task': 'S4-2',
                  'commit_sha': self.base, 'repository': repo_identity(self.repo)}
        payload = authority.signed_record_payload(record)
        record['authority'] = {
            'status': 'signed', 'anchor_id': ANCHOR_ID, 'issuer': APPROVER,
            'algorithm': 'rsa-sha256',
            'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'signature_b64': base64.b64encode(self.sign(payload, 'att')).decode('ascii')}
        return record

    def anchor_loader(self, document):
        """Replace only the path/owner checks; keep real document validation."""

        def fake(_repo, _value):
            anchor, reason = authority._anchor_document(document)
            if anchor is None:
                return None, reason
            return {**anchor, 'path': '<test-anchor>', 'protection': 'test'}, 'ok'

        return fake

    def under_anchor(self, document):
        return (mock.patch('project_memory.authority._load_file_anchor',
                           side_effect=self.anchor_loader(document)),
                mock.patch.dict(os.environ, {
                    authority.APPROVAL_ANCHOR_ENV: '<test-approval-anchor>',
                    authority.ANCHOR_ENV: '<test-trust-anchor>'}))

    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def verify(self, document, repo=None, record=None, commit=None):
        anchor_patcher, env_patcher = self.under_anchor(document)
        with anchor_patcher, env_patcher:
            code, output = self.run_cli(
                ['approval', 'verify', '--repo', str(repo or self.repo),
                 '--record', str(record or self.record_path),
                 '--commit', commit or self.base, '--json'])
        return code, (json.loads(output) if output.strip() else None)

    def record_verdict(self, document, record):
        anchor_patcher, env_patcher = self.under_anchor(document)
        with anchor_patcher, env_patcher:
            return signed_record_authority(self.repo, record)

    # ------------------------------------------------------------ positives

    def test_fingerprint_matches_the_openssl_der_digest(self):
        der = subprocess.run([self.openssl, 'pkey', '-pubin', '-in',
                              str(self.public_path), '-outform', 'DER'],
                             check=True, capture_output=True).stdout
        self.assertEqual(hashlib.sha256(der).hexdigest(),
                         authority.public_key_fingerprint(self.public_pem))

    def test_anchor_without_optional_fields_keeps_existing_behaviour(self):
        code, result = self.verify(self.document())
        self.assertEqual(0, code)
        self.assertTrue(result['verified'])
        self.assertTrue(result['trusted'])
        self.assertEqual([], result['problems'])

    def test_valid_window_other_revocation_and_fingerprint_stay_trusted(self):
        document = self.document(not_before=_hours(-24), not_after=_hours(24),
                                 revoked_anchor_ids=[OTHER_ANCHOR_ID],
                                 fingerprint_sha256='sha256:' + authority
                                 .public_key_fingerprint(self.public_pem).upper())
        code, result = self.verify(document)
        self.assertEqual(0, code)
        self.assertTrue(result['verified'])
        self.assertTrue(result['trusted'])
        verdict = self.record_verdict(document, self.attestation())
        self.assertTrue(verdict['trusted'])
        self.assertEqual('trusted', verdict['status'])

    def test_only_not_before_already_effective_is_trusted(self):
        code, result = self.verify(self.document(not_before=_hours(-24)))
        self.assertEqual(0, code)
        self.assertTrue(result['verified'])

    # ------------------------------------------------------ negative controls

    def test_self_revoked_anchor_is_untrusted(self):
        document = self.document(revoked_anchor_ids=[OTHER_ANCHOR_ID, ANCHOR_ID])
        code, result = self.verify(document)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertFalse(result['trusted'])
        self.assertIn('吊销', result['reason'])
        verdict = self.record_verdict(document, self.attestation())
        self.assertFalse(verdict['trusted'])
        self.assertIn('吊销', verdict['reason'])

    def test_expired_anchor_is_untrusted(self):
        code, result = self.verify(self.document(not_after=_hours(-24)))
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertIn('已过期', result['reason'])

    def test_not_yet_effective_anchor_is_untrusted(self):
        code, result = self.verify(self.document(not_before=_hours(24)))
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertIn('尚未生效', result['reason'])

    def test_revocation_list_must_be_an_array_of_ids(self):
        for revoked in (OTHER_ANCHOR_ID, [''], ['  '], [42], [None],
                        ['-leading-dash'], ['x' * 129]):
            code, result = self.verify(self.document(revoked_anchor_ids=revoked))
            self.assertEqual(2, code, revoked)
            self.assertFalse(result['verified'], revoked)
            self.assertIn('revoked_anchor_ids', result['reason'], revoked)

    def test_wrong_fingerprint_is_rejected(self):
        wrong = '0' * 63 + '1'
        self.assertNotEqual(authority.public_key_fingerprint(self.public_pem), wrong)
        code, result = self.verify(self.document(fingerprint_sha256='sha256:' + wrong))
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertIn('fingerprint_sha256', result['reason'])

    def test_malformed_time_fields_are_rejected(self):
        for extra in ({'not_before': '2026-01-01T00:00:00'},
                      {'not_after': '2026-01-01 00:00:00'},
                      {'not_before': 'not-a-time'},
                      {'not_before': _hours(1), 'not_after': _hours(-1)}):
            code, result = self.verify(self.document(**extra))
            self.assertEqual(2, code, extra)
            self.assertFalse(result['verified'], extra)
            self.assertTrue(result['reason'], extra)

    def test_approval_from_another_repository_does_not_verify(self):
        other = self.init_repo(self.work / 'repo-b', 'repo-b')
        self.assertNotEqual(repo_identity(other)['id'], repo_identity(self.repo)['id'])
        record = json.loads(self.record_path.read_text(encoding='utf-8'))
        foreign = self.work / 'foreign-approval.json'
        foreign.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                           encoding='utf-8')
        code, result = self.verify(self.document(), repo=other, record=foreign,
                                   commit=record['commit_sha'])
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertTrue(result['trusted'])
        self.assertEqual([REPOSITORY_PROBLEM], result['problems'])
        same_code, same = self.verify(self.document(), record=foreign,
                                      commit=record['commit_sha'])
        self.assertEqual(0, same_code)
        self.assertTrue(same['verified'])

    def test_untouched_records_stay_verifiable_after_revocation(self):
        """Revocation stops later decisions; it never rewrites written records."""
        before = json.loads(self.record_path.read_text(encoding='utf-8'))
        self.assertTrue(self.approval_trusted(self.document()))
        code, _ = self.verify(self.document(revoked_anchor_ids=[ANCHOR_ID]))
        self.assertEqual(2, code)
        self.assertEqual(before, json.loads(self.record_path.read_text(encoding='utf-8')))
        self.assertTrue(self.approval_trusted(self.document()))

    def approval_trusted(self, document):
        record = json.loads(self.record_path.read_text(encoding='utf-8'))
        anchor_patcher, env_patcher = self.under_anchor(document)
        with anchor_patcher, env_patcher:
            return approval_authority(self.repo, record)['trusted']


if __name__ == '__main__':
    unittest.main()
