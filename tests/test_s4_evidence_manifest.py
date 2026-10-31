"""S4-1: signed evidence manifests bind files to one commit and tree.

The signing tests use a test-time RSA key (openssl) and patch
``authority.load_anchor`` so the protected-anchor path runs without production
keys.  Every negative control ends with exit code 2 (or a rejected request),
never a warning-only result.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openssl_support import require_openssl
from project_memory import authority
from project_memory.cli import main
from project_memory.common import PMError, git_sha
from project_memory.evidence import _manifest_id, evidence_attach
from project_memory.execution import repo_identity

ISSUER = 'evidence@example.invalid'


class _RepoFixture(unittest.TestCase):
    """A throwaway git repository plus an out-of-repo signing workspace."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.workspace = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.git('init', '-q')
        self.git('config', 'user.email', 's4@example.invalid')
        self.git('config', 'user.name', 'S4')
        (self.repo / 'docs').mkdir()
        (self.repo / 'evidence').mkdir()
        (self.repo / 'docs' / 'a.txt').write_text('alpha\n', encoding='utf-8')
        (self.repo / 'docs' / 'b.txt').write_text('beta\n', encoding='utf-8')
        (self.repo / 'docs' / 'c.txt').write_text('gamma\n', encoding='utf-8')
        (self.repo / 'evidence' / 'data.bin').write_bytes(b'\x00\x01\x02evidence')
        self.git('add', 'docs', 'evidence')
        self.git('commit', '-qm', 'base')
        self.base = git_sha(self.repo)
        (self.repo / 'later.txt').write_text('later\n', encoding='utf-8')
        self.git('add', 'later.txt')
        self.git('commit', '-qm', 'later')
        self.second = git_sha(self.repo)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def request(self, paths=('docs', 'evidence/data.bin'), commit=None,
                name='request.json'):
        output = self.workspace / name
        argv = ['evidence', 'request', '--repo', str(self.repo),
                '--commit', commit or self.base]
        for value in paths:
            argv += ['--path', value]
        argv += ['--output', str(output)]
        code, text, err = self.run_cli(argv)
        self.assertEqual(0, code, err)
        return json.loads(text), output


class EvidenceManifestRequestTest(_RepoFixture):
    """Request-side checks that need no key."""

    def test_request_records_sorted_hashes_tree_and_recomputable_id(self):
        result, path = self.request()
        record = result['manifest']
        self.assertEqual('evidence_manifest', record['kind'])
        self.assertEqual('1.0', record['schema_version'])
        self.assertEqual(self.base, record['commit_sha'])
        tree = self.git('rev-parse', 'HEAD~1^{tree}').stdout.strip()
        self.assertEqual(tree, record['tree_sha'])
        paths = [item['path'] for item in record['files']]
        self.assertEqual(sorted(paths), paths)
        self.assertEqual(['docs/a.txt', 'docs/b.txt', 'docs/c.txt',
                          'evidence/data.bin'], paths)
        for item in record['files']:
            data = (self.repo / item['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
            self.assertEqual(len(data), item['bytes'])
        self.assertTrue(record['manifest_id'].startswith('EVM-'))
        self.assertEqual(_manifest_id(record), record['manifest_id'])
        self.assertEqual(repo_identity(self.repo)['id'],
                         record['repository']['id'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         result['payload_sha256'])
        self.assertNotIn('authority', record)

    def test_directory_recursion_includes_every_regular_file(self):
        result, _path = self.request(paths=['docs'])
        self.assertEqual(['docs/a.txt', 'docs/b.txt', 'docs/c.txt'],
                         [item['path'] for item in result['manifest']['files']])

    def test_path_outside_repository_is_rejected(self):
        outside = self.workspace / 'outside.txt'
        outside.write_text('outside\n', encoding='utf-8')
        for value in ('../outside.txt', str(outside)):
            code, _out, err = self.run_cli(
                ['evidence', 'request', '--repo', str(self.repo),
                 '--commit', self.base, '--path', value,
                 '--output', str(self.workspace / 'r.json')])
            self.assertEqual(1, code)
            self.assertIn('仓库之外', err)
        self.assertFalse((self.workspace / 'r.json').exists())

    def test_duplicate_paths_are_rejected(self):
        code, _out, err = self.run_cli(
            ['evidence', 'request', '--repo', str(self.repo),
             '--commit', self.base, '--path', 'docs', '--path', 'docs/a.txt',
             '--output', str(self.workspace / 'r.json')])
        self.assertEqual(1, code)
        self.assertIn('重复', err)

    def test_symlink_outside_repository_is_rejected(self):
        outside = self.workspace / 'outside.txt'
        outside.write_text('outside\n', encoding='utf-8')
        link = self.repo / 'docs' / 'link.txt'
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'当前环境无法创建符号链接（Windows 权限）：{exc}')
        code, _out, err = self.run_cli(
            ['evidence', 'request', '--repo', str(self.repo),
             '--commit', self.base, '--path', 'docs',
             '--output', str(self.workspace / 'r.json')])
        self.assertEqual(1, code)
        self.assertIn('符号链接', err)

    def test_empty_file_list_is_rejected(self):
        record = {
            'schema_version': '1.0', 'kind': 'evidence_manifest',
            'created_at': '2026-10-31T00:00:00Z', 'commit_sha': self.base,
            'tree_sha': '0' * 40, 'repository': {'id': 'x', 'remote': None},
            'statement': '', 'files': [],
            'generator': {'tool': 'project-memory', 'version': '1.0.0',
                          'python': '3.12.4', 'platform': 'test', 'command': ''},
        }
        record['manifest_id'] = _manifest_id(record)
        request = self.workspace / 'empty.json'
        request.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                           encoding='utf-8')
        with self.assertRaises(PMError) as caught:
            evidence_attach(self.repo, request, self.workspace / 'none.sig',
                            self.workspace / 'none-anchor.json',
                            self.workspace / 'out.json')
        self.assertIn('files 不能为空', str(caught.exception))


class EvidenceManifestSignedTest(_RepoFixture):
    """End-to-end signed manifests with a test-time RSA key."""

    @classmethod
    def setUpClass(cls):
        cls.openssl = require_openssl('S4 证据清单测试需要测试期签名者')
        cls.keydir = tempfile.TemporaryDirectory()
        work = Path(cls.keydir.name)
        cls.key = work / 'signer.pem'
        cls.other_key = work / 'other.pem'
        for key in (cls.key, cls.other_key):
            subprocess.run([cls.openssl, 'genpkey', '-algorithm', 'RSA',
                            '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(key)],
                           check=True, capture_output=True)
        cls.anchor = cls._anchor(work, cls.key, 's4-evidence-anchor')
        cls.other_anchor_doc = cls._anchor(work, cls.other_key, 's4-other-anchor')
        cls.anchor_path = work / 'anchor.json'
        cls.anchor_path.write_text(json.dumps(cls.anchor), encoding='utf-8')
        cls.other_anchor_path = work / 'other-anchor.json'
        cls.other_anchor_path.write_text(json.dumps(cls.other_anchor_doc),
                                         encoding='utf-8')

    @classmethod
    def _anchor(cls, work, key, anchor_id):
        public = work / f'{key.stem}.pub.pem'
        subprocess.run([cls.openssl, 'pkey', '-in', str(key), '-pubout',
                        '-out', str(public)], check=True, capture_output=True)
        return {'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
                'anchor_id': anchor_id, 'issuer': ISSUER,
                'algorithm': 'rsa-sha256',
                'public_key_pem': public.read_text(encoding='utf-8')}

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        super().setUp()

        def fake_anchor(repo, env_name=authority.ANCHOR_ENV, json_env=None):
            if env_name == authority.APPROVAL_ANCHOR_ENV:
                return {**self.anchor, 'path': str(self.anchor_path),
                        'protection': 'test'}, 'ok'
            return None, 'S4 测试未配置验证信任锚'

        patcher = mock.patch('project_memory.authority.load_anchor',
                             side_effect=fake_anchor)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------ helpers

    def sign(self, request_path, key=None, name='sig'):
        signature = self.workspace / f'{name}.sig'
        subprocess.run([self.openssl, 'dgst', '-sha256', '-sign',
                        str(key or self.key), '-out', str(signature),
                        str(request_path)], check=True, capture_output=True)
        return signature

    def attach(self, request_path, signature, anchor_path=None,
               output='manifest.json', expect=0):
        target = self.workspace / output
        code, text, err = self.run_cli(
            ['evidence', 'attach', '--repo', str(self.repo),
             '--request', str(request_path), '--signature', str(signature),
             '--anchor', str(anchor_path or self.anchor_path),
             '--output', str(target)])
        self.assertEqual(expect, code, err)
        return (json.loads(text) if code == 0 else None), target, code

    def signed_manifest(self, paths=('docs', 'evidence/data.bin')):
        _request, request_path = self.request(paths=paths)
        return self.attach(request_path, self.sign(request_path))

    def verify(self, manifest_path, commit=None, repo=None):
        code, text, err = self.run_cli(
            ['evidence', 'verify', '--repo', str(repo or self.repo),
             '--manifest', str(manifest_path),
             '--commit', commit or self.base, '--json'])
        self.assertEqual('', err)
        return code, json.loads(text)

    def resign(self, record, key=None):
        payload = authority.signed_record_payload(record)
        payload_file = self.workspace / 'payload.json'
        payload_file.write_bytes(payload)
        signature = self.sign(payload_file, key=key, name='resign')
        record['authority'] = {
            'status': 'signed',
            'anchor_id': (self.other_anchor_doc if key == self.other_key
                          else self.anchor)['anchor_id'],
            'issuer': ISSUER,
            'algorithm': 'rsa-sha256',
            'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'signature_b64': base64.b64encode(signature.read_bytes()).decode('ascii'),
        }
        return record

    # ------------------------------------------------------------ positives

    def test_attach_and_verify_exit_zero(self):
        attached, path, _code = self.signed_manifest()
        self.assertTrue(attached['signature_valid'])
        self.assertTrue(attached['created'])
        self.assertIn('authority', attached['manifest'])
        code, result = self.verify(path)
        self.assertEqual(0, code)
        self.assertTrue(result['verified'])
        self.assertTrue(result['signed'])
        self.assertTrue(result['trusted'])
        self.assertEqual('trusted', result['authority_status'])
        self.assertEqual([], result['problems'])
        self.assertEqual(attached['manifest_id'], result['manifest_id'])

    def test_attach_same_content_is_idempotent(self):
        _request, request_path = self.request()
        signature = self.sign(request_path)
        first, path, _code = self.attach(request_path, signature)
        second, path2, _code = self.attach(request_path, signature)
        self.assertEqual(path, path2)
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['manifest'], second['manifest'])
        code, result = self.verify(path)
        self.assertEqual(0, code)
        self.assertTrue(result['verified'])

    # ------------------------------------------------------------ negatives

    def test_negative_1_modified_byte_fails(self):
        _attached, path, _code = self.signed_manifest()
        target = self.repo / 'docs' / 'a.txt'
        target.write_text('alphA\n', encoding='utf-8')
        code, result = self.verify(path)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertTrue(any('sha256' in problem for problem in result['problems']))

    def test_negative_2_missing_file_fails(self):
        _attached, path, _code = self.signed_manifest()
        (self.repo / 'evidence' / 'data.bin').unlink()
        code, result = self.verify(path)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertTrue(any('不存在' in problem for problem in result['problems']))

    def test_negative_3_wrong_commit_fails(self):
        _attached, path, _code = self.signed_manifest()
        code, result = self.verify(path, commit=self.second)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertTrue(any('不是' in problem for problem in result['problems']))

    def test_negative_4_tampered_tree_resigned_fails(self):
        _attached, path, _code = self.signed_manifest()
        record = json.loads(path.read_text(encoding='utf-8'))
        record['tree_sha'] = '0' * 40
        record['manifest_id'] = _manifest_id(record)
        record = self.resign(record)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        code, result = self.verify(path)
        self.assertEqual(2, code)
        self.assertTrue(result['signed'])
        self.assertTrue(result['trusted'], result['problems'])
        self.assertFalse(result['verified'])
        self.assertTrue(any('树' in problem for problem in result['problems']))

    def test_negative_5_unsigned_manifest_fails(self):
        _request, request_path = self.request()
        code, result = self.verify(request_path)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertFalse(result['signed'])
        self.assertFalse(result['trusted'])
        self.assertTrue(any('authority' in problem for problem in result['problems']))

    def test_negative_6_other_key_fails(self):
        _request, request_path = self.request()
        wrong_signature = self.sign(request_path, key=self.other_key, name='wrong')
        code, _out, err = self.run_cli(
            ['evidence', 'attach', '--repo', str(self.repo),
             '--request', str(request_path), '--signature', str(wrong_signature),
             '--anchor', str(self.anchor_path),
             '--output', str(self.workspace / 'wrong-key.json')])
        self.assertEqual(1, code)
        self.assertIn('签名', err)
        attached, path, _code = self.attach(
            request_path, wrong_signature, anchor_path=self.other_anchor_path,
            output='other-anchor.json')
        self.assertEqual('s4-other-anchor', attached['anchor_id'])
        code, result = self.verify(path)
        self.assertEqual(2, code)
        self.assertFalse(result['trusted'])
        self.assertIn('anchor_id', result['reason'])
        self.assertFalse(result['verified'])

    def test_negative_7_no_protected_anchor_fails(self):
        _attached, path, _code = self.signed_manifest()
        with mock.patch('project_memory.authority.load_anchor',
                        return_value=(None, '未配置 PROJECT_MEMORY_APPROVAL_ANCHOR')):
            code, result = self.verify(path)
        self.assertEqual(2, code)
        self.assertFalse(result['trusted'])
        self.assertEqual('unconfigured', result['authority_status'])
        self.assertFalse(result['verified'])

    def test_negative_10_duplicate_file_entries_fail_structure(self):
        attached, path, _code = self.signed_manifest()
        record = json.loads(path.read_text(encoding='utf-8'))
        record['files'] = [record['files'][0], record['files'][0]]
        record['manifest_id'] = _manifest_id(record)
        record = self.resign(record)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        code, result = self.verify(path)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertTrue(any('重复' in problem for problem in result['problems']))

    def test_negative_11_other_repository_fails(self):
        self.git('remote', 'add', 'origin', 'https://example.invalid/repo-a.git')
        _attached, path, _code = self.signed_manifest()
        original = repo_identity(self.repo)['id']

        same_history = self.workspace / 'repo-b'
        shutil.copytree(self.repo, same_history)
        subprocess.run(['git', '-C', str(same_history), 'remote', 'set-url',
                        'origin', 'https://example.invalid/repo-b.git'],
                       check=True, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(original, repo_identity(same_history)['id'])
        code, result = self.verify(path, repo=same_history)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertTrue(result['signed'])
        self.assertTrue(result['trusted'], result['problems'])
        self.assertTrue(any('仓库身份' in problem for problem in result['problems']))

        other_root = self.workspace / 'repo-c'
        other_root.mkdir()
        for args in (('init', '-q'), ('config', 'user.email', 'other@example.invalid'),
                     ('config', 'user.name', 'Other')):
            subprocess.run(['git', '-C', str(other_root), *args], check=True,
                           capture_output=True, text=True, encoding='utf-8')
        (other_root / 'README.md').write_text('other\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(other_root), 'add', 'README.md'],
                       check=True, capture_output=True, text=True, encoding='utf-8')
        subprocess.run(['git', '-C', str(other_root), 'commit', '-qm', 'other'],
                       check=True, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(original, repo_identity(other_root)['id'])
        code, result = self.verify(path, repo=other_root)
        self.assertEqual(2, code)
        self.assertFalse(result['verified'])
        self.assertTrue(any('仓库身份' in problem for problem in result['problems']))


if __name__ == '__main__':
    unittest.main()
