"""B1: the signature verifier must not be selectable by the caller's environment.

RC3 found that ``authority`` resolved ``openssl`` through ``PATH`` /
``PROJECT_MEMORY_OPENSSL`` and trusted only its exit code, so an agent that
launches the CLI could substitute the verifier and get a forged signature
accepted.  These tests pin the replacement behaviour: the verdict comes from the
anchor's public key and the arithmetic in ``authority``, never from a program the
caller chooses.  Positive vectors were produced with OpenSSL 3.5.9 29 Sep 2026 (Library: OpenSSL 3.5.9 29 Sep 2026) and are kept
as fixed data, so the suite is deterministic and needs no signer at test time.
"""
import base64
import hashlib
import inspect
import json
import os
import platform
import re
import tempfile
import unittest
from pathlib import Path

from project_memory import authority

VECTORS = json.loads(r'''
{
 "generator": "OpenSSL 3.5.9 29 Sep 2026 (Library: OpenSSL 3.5.9 29 Sep 2026)",
 "record": {
  "schema_version": "1.2",
  "kind": "verification_record",
  "verification_id": "VER-vector",
  "task": "325",
  "goal_id": "G-B1",
  "target_head_sha": "0000000000000000000000000000000000000000",
  "verdict": "pass",
  "status": "VERIFIED",
  "mapping_status": "complete",
  "criterion_evidence": [
   {
    "criterion_id": "C1",
    "goal_id": "G-B1",
    "target_commit_sha": "0000000000000000000000000000000000000000",
    "evidence_matched": true
   }
  ]
 },
 "payload_sha256": "bedbc5f20e61caa4bd0bba053622aa0568078ab9ae38a71c5fa9cf0b9af618a6",
 "rsa2048": {
  "public_key_pem": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwXsuGJp+tMw/3xphWNVr\ntEiqTAFC/gJYuDgj1BEqQnX0lPOwJ9W51sDBYEt/4L+rUkZ71rW89iNMd8yel4lZ\ncqoi8E2/ibT606m/amAOIPPnPtzNp53YCpIx+NtK4AfLDheca9MiFU7WwOJv/NnR\ndw/8+0eL9cXF6i+L1z4pVRiDfsYTHvzZX/jne9In+fTfQnurUXXZ2xOg3xwE0+nK\nN3wwYCML7XICQx2ofbgDGDVNJFk/C6ln4wVMwkEaqWIMskmto2iAGXPabf04a5c2\n9dZ6q/toSDMnj+5Cb3uT7O/MMoh4TWyx3Ktfz76rrgtjPVcpPP+suTDPkVaeNkEi\nOQIDAQAB\n-----END PUBLIC KEY-----\n",
  "signature_b64": "PTEtFoLecPSw+d1YZG3wkYSA73dJDcd6CDH77S79zwn4gH8nuFgYTFWioaSvi705AIfRMHwN/BNZ+hd7ovR1WQt3xDRo+oMqmIQG7hswd/kKimUjm59cdRqH9lIYzPV6GDjlwskuayQajX0m9dXYFPuv2ijpgvn4qWRe9r8c6m02w/KTsam2yOrdecJu+ZrwspEamwP76LueSg1ZMmQZK1W0bWnKD58/cr3d6oKLtlYyGjWIo9b2HYW7t3jJZVWEljC2emjKhiwjn4p4ZB3YCph1GvvEm5gQ14WrrrmHK7649Hwj139mGSyYdr/6iuJfnZwpDaXRKAuZMsL1t2NGsA==",
  "openssl_says": "Verified OK",
  "openssl_says_for_tampered": "Verification failure"
 },
 "rsa1024_public_key_pem": "-----BEGIN PUBLIC KEY-----\nMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDHufgwmBlt757mhMmfl45Vditp\nn9MQh68F6o8Rm99CqnYO8LNgPIxp/k6kgyTYOuOVF5ULDeFQp7LEmEUPIe2fpOTs\nTMeSem1HiMZp0NStJ1QWNOzsCLIldgiP7hya7gD5ZKL7fRhGa6COpCQg7XqAhhV7\nedLZn+nerFUpExyi5QIDAQAB\n-----END PUBLIC KEY-----\n",
 "other_rsa_public_key_pem": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApu3pMcq0BF5ltbTWPl9W\nBmKuociufnro5gUpWwQpg5TK82ENIhWM48dsCSg516enqUSthA7ipFb7d7JXPxeF\nk8R1HoXCbbilZvBKIRS/N7Sp8339zNfb2VN7JqfiNkMdSW+s2Ad824UlbpvkYDt8\ncKBaHOR2KEBZUarjSTIu8lOuOExMWDEdkYrbHmYXcBBd1bYZZ+c5s+hZQJm0FIco\nyTk4yGZFV+6v/ZbzcCMEzEnouN9CNldq7Nwj1Q69d+ODTiGWmU6iXxS7vCZzyYm+\n0JkKLk6D5h6XV5W4lEFP7IuaLWlRhwdbLQnua9tuEd9IliW3UXcdCzuxYn7ztjpF\n9QIDAQAB\n-----END PUBLIC KEY-----\n",
 "ecp256": {
  "public_key_pem": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEpKrZjCe4LjlVujDpDAgrnvcUiHsM\nswMStzZYF9K/sQ/XLJLX3xSgeCc0vPmvgvwdiyhfzls42GtbuBVslx5IUw==\n-----END PUBLIC KEY-----\n",
  "signature_b64": "MEYCIQDNPAQ4lBsDVyiziwtnI3lU4oTFQ6mSUqbPpJ0hgqpEYwIhAKSof74reTBnAZnwbjlPWR/Lm0oLTB4KzPtofCqwowFG",
  "openssl_says": "Verified OK"
 },
 "ecp256_non_canonical_r_b64": "MEcCIgAAzTwEOJQbA1cos4sLZyN5VOKExUOpklKmz6SdIYKqRGMCIQCkqH++K3kwZwGZ8G45T1kfy5tKC0weCsz7aHwqsKMBRg==",
 "ecp256_r_zero_b64": "MCYCAQACIQCkqH++K3kwZwGZ8G45T1kfy5tKC0weCsz7aHwqsKMBRg==",
 "secp384r1_public_key_pem": "-----BEGIN PUBLIC KEY-----\nMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEhjm5+spOZ1G1gnp0kJx1qY60zR6bpJyo\nxruFX005BVK5ms670IWH0VogOjKHdfOdWukIrz+yawlvTQEBfyLHjFCY6hHru3F/\ns33PApKidI5HNtQIYDEzh8w3zXi//j7e\n-----END PUBLIC KEY-----\n"
}
''')

RECORD = VECTORS['record']
PAYLOAD = authority.verification_payload(RECORD)
GARBAGE = base64.b64encode(b'agent-cannot-produce-this').decode('ascii')
HOSTILE_ENV = 'PROJECT_MEMORY_OPENSSL'


def anchor(pem: str) -> dict:
    return {'algorithm': 'rsa-sha256', 'anchor_id': 'test', 'issuer': 'test',
            'public_key_pem': pem}


class VerifierIsNotEnvironmentSelectable(unittest.TestCase):
    """AC-2/3/4/5/6: no PATH lookup, no env var, no output trust, no fallback."""

    def setUp(self):
        self.previous = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.previous)

    def plant_fake_verifier(self) -> Path:
        """Stand in a verifier that always prints `Verified OK` and exits 0."""
        directory = Path(tempfile.mkdtemp(prefix='pm-b1-fakebin-'))
        script = directory / ('openssl.bat' if platform.system() == 'Windows' else 'openssl')
        if script.suffix == '.bat':
            script.write_text('@echo off\r\necho Verified OK\r\nexit /b 0\r\n', encoding='ascii')
        else:
            script.write_text('#!/bin/sh\necho "Verified OK"\nexit 0\n', encoding='ascii')
            os.chmod(script, 0o755)
        os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
        os.environ[HOSTILE_ENV] = str(script)
        return script

    def test_forged_signature_rejected_with_substituted_verifier(self):
        self.plant_fake_verifier()
        ok, reason = authority._verify_signature(anchor(VECTORS['rsa2048']['public_key_pem']),
                                                 PAYLOAD, GARBAGE, 'rsa-sha256')
        self.assertFalse(ok, reason)
        self.assertIn('签名验证失败', reason)

    def test_valid_signature_still_accepted_in_the_same_environment(self):
        # Proves the rejections above are not "everything fails": with the fake
        # verifier planted, the genuine signature still verifies (AC-1 vs AC-2).
        self.plant_fake_verifier()
        ok, reason = authority._verify_signature(
            anchor(VECTORS['rsa2048']['public_key_pem']), PAYLOAD,
            VECTORS['rsa2048']['signature_b64'], 'rsa-sha256')
        self.assertTrue(ok, reason)

    def test_module_keeps_no_external_verifier_dependency(self):
        for name in ('shutil', 'subprocess', 'tempfile'):
            self.assertNotIn(name, dir(authority), f'authority 不应再引入 {name}')
        source = inspect.getsource(authority)
        self.assertNotIn('PROJECT_MEMORY_OPENSSL', source)
        self.assertNotIn('powershell', source)
        self.assertNotIn('Get-Acl', source)
        # Anchors may come from a fixed set of environment names; the verifier
        # itself still cannot be selected.  ``env_name``/``json_env`` variables
        # are never passed to ``os.environ.get`` directly, so an arbitrary name
        # cannot be read.  The approval file anchor remains one of the fixed
        # names because B8's local workflow still uses it.
        used = set(re.findall(r'os\.environ\.get\(\s*([A-Za-z_][A-Za-z0-9_]*)',
                              source))
        self.assertEqual(
            {'ANCHOR_ENV', 'APPROVAL_ANCHOR_ENV', 'TRUST_ANCHOR_JSON_ENV',
             'APPROVAL_ANCHOR_JSON_ENV', 'CI_CONTEXT_ENV'},
            used, 'authority 只允许读取固定的信任锚环境变量名字')


class RsaVectorTest(unittest.TestCase):
    """AC-1/6/9: RSASSA-PKCS1-v1_5 + SHA-256, fail-closed on every edge."""

    def setUp(self):
        self.pem = VECTORS['rsa2048']['public_key_pem']
        self.signature = VECTORS['rsa2048']['signature_b64']

    def verify(self, payload=None, signature=None, pem=None, algorithm='rsa-sha256'):
        return authority._verify_signature(
            anchor(pem or self.pem), PAYLOAD if payload is None else payload,
            self.signature if signature is None else signature, algorithm)

    def test_vector_is_a_real_signature(self):
        self.assertEqual('Verified OK', VECTORS['rsa2048']['openssl_says'])
        self.assertIn('failure', VECTORS['rsa2048']['openssl_says_for_tampered'].lower())
        self.assertEqual(VECTORS['payload_sha256'], hashlib.sha256(PAYLOAD).hexdigest())

    def test_valid_signature_accepted(self):
        ok, reason = self.verify()
        self.assertTrue(ok, reason)
        self.assertEqual('signature verified', reason)

    def test_tampered_payload_rejected(self):
        self.assertFalse(self.verify(payload=PAYLOAD + b' ')[0])

    def test_flipped_signature_byte_rejected(self):
        raw = bytearray(base64.b64decode(self.signature))
        raw[len(raw) // 2] ^= 0x01
        self.assertFalse(self.verify(signature=base64.b64encode(bytes(raw)).decode('ascii'))[0])

    def test_truncated_signature_rejected(self):
        raw = base64.b64decode(self.signature)
        self.assertFalse(self.verify(signature=base64.b64encode(raw[:-1]).decode('ascii'))[0])

    def test_signature_integer_above_modulus_rejected(self):
        _, modulus, _ = authority._public_key(self.pem)
        size = (modulus.bit_length() + 7) // 8
        self.assertFalse(self.verify(signature=base64.b64encode(b'\xff' * size).decode('ascii'))[0])

    def test_other_signers_key_rejected(self):
        self.assertFalse(self.verify(pem=VECTORS['other_rsa_public_key_pem'])[0])

    def test_non_base64_signature_rejected(self):
        ok, reason = self.verify(signature='not base64 !!')
        self.assertFalse(ok)
        self.assertIn('base64', reason)

    def test_empty_signature_rejected(self):
        ok, reason = self.verify(signature='')
        self.assertFalse(ok)
        self.assertIn('空', reason)

    def test_anchor_without_public_key_rejected(self):
        ok, reason = authority._verify_signature({'algorithm': 'rsa-sha256'}, PAYLOAD,
                                                 self.signature, 'rsa-sha256')
        self.assertFalse(ok)
        self.assertIn('公钥', reason)

    def test_unparseable_public_key_rejected(self):
        junk = ('-----BEGIN PUBLIC KEY-----\n'
                + base64.b64encode(b'\x30\x0f\x02\x01\x01\x03\x01\x00\x30\x00' * 4).decode('ascii')
                + '\n-----END PUBLIC KEY-----\n')
        ok, reason = self.verify(pem=junk)
        self.assertFalse(ok, reason)

    def test_small_modulus_rejected(self):
        ok, reason = self.verify(pem=VECTORS['rsa1024_public_key_pem'])
        self.assertFalse(ok)
        self.assertIn('2048', reason)

    def test_key_kind_must_match_algorithm(self):
        ok, reason = self.verify(algorithm='ecdsa-sha256')
        self.assertFalse(ok)
        self.assertIn('不匹配', reason)

    def test_unsupported_algorithm_rejected(self):
        self.assertFalse(self.verify(algorithm='ed25519')[0])


class EcdsaVectorTest(unittest.TestCase):
    """AC-6/9: ECDSA is pinned to P-256 with strict DER and full range checks."""

    def setUp(self):
        self.pem = VECTORS['ecp256']['public_key_pem']
        self.signature = VECTORS['ecp256']['signature_b64']

    def verify(self, payload=None, signature=None, pem=None):
        return authority._verify_signature(
            anchor(pem or self.pem), PAYLOAD if payload is None else payload,
            self.signature if signature is None else signature, 'ecdsa-sha256')

    def test_valid_p256_signature_accepted(self):
        ok, reason = self.verify()
        self.assertTrue(ok, reason)
        self.assertEqual('Verified OK', VECTORS['ecp256']['openssl_says'])

    def test_tampered_payload_rejected(self):
        self.assertFalse(self.verify(payload=PAYLOAD + b'x')[0])

    def test_non_canonical_r_rejected(self):
        self.assertFalse(self.verify(signature=VECTORS['ecp256_non_canonical_r_b64'])[0])

    def test_r_zero_rejected(self):
        self.assertFalse(self.verify(signature=VECTORS['ecp256_r_zero_b64'])[0])

    def test_other_curve_rejected(self):
        ok, reason = self.verify(pem=VECTORS['secp384r1_public_key_pem'])
        self.assertFalse(ok)
        self.assertIn('不受支持', reason)

    def test_off_curve_public_point_rejected(self):
        raw = base64.b64decode(self.signature)
        self.assertFalse(authority._ecdsa_verify(1, 1, PAYLOAD, raw))

    def test_degenerate_der_signature_rejected(self):
        raw = base64.b64decode(self.signature)
        for candidate in (b'\x30\x00', b'\x30\x06\x02\x01\x01',
                          raw[:len(raw) - 1], b'', b'\x30\x81\x02\x02\x00'):
            # Through the production entry point, so a malformed DER is a
            # rejection rather than an exception escaping the authority check.
            ok, reason = self.verify(
                signature=base64.b64encode(candidate).decode('ascii') or '')
            self.assertFalse(ok, (candidate, reason))


class AnchorIdentityTest(unittest.TestCase):
    """The trust-root owner check must not come from PATH or a name in $USER."""

    def test_anchor_owned_by_current_principal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'anchor.json'
            path.write_text('{}', encoding='utf-8')
            os.chmod(path, 0o444)
            try:
                protected, reason = authority.anchor_is_protected(path)
            finally:
                os.chmod(path, 0o644)
            self.assertFalse(protected, reason)
            self.assertIn('当前用户', reason)

    def test_owner_identity_comes_from_the_security_api(self):
        if platform.system() != 'Windows':
            self.assertIsNone(authority._file_owner_sid(Path(__file__)))
            return
        owner = authority._file_owner_sid(Path(__file__).resolve())
        current = authority._current_user_sid()
        self.assertIsNotNone(owner)
        self.assertRegex(owner, r'^S-1-\d+(-\d+)+$')
        if owner == current:
            return
        # Elevated runners (for example GitHub-hosted Windows) own checked-out
        # files as a well-known group such as BUILTIN\Administrators, so the
        # owner SID legitimately differs from the current user SID there.
        self.assertRegex(owner, r'^S-1-5-32-\d+$', (owner, current))


if __name__ == '__main__':
    unittest.main()
