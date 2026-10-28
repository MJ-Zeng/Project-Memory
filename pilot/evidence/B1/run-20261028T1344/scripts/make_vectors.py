"""Generate the fixed signature vectors used by tests/test_authority_verifier.py.

Every vector is produced with the local OpenSSL CLI and cross-checked with
`openssl dgst -verify` before being printed, so the unit tests are deterministic
and do not need a signer at test time.  These are throwaway test keys; the
project's real signer keys never enter this repository.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from project_memory import authority  # noqa: E402

RECORD = {
    'schema_version': '1.2', 'kind': 'verification_record',
    'verification_id': 'VER-vector', 'task': '325', 'goal_id': 'G-B1',
    'target_head_sha': '0' * 40, 'verdict': 'pass', 'status': 'VERIFIED',
    'mapping_status': 'complete',
    'criterion_evidence': [{'criterion_id': 'C1', 'goal_id': 'G-B1',
                            'target_commit_sha': '0' * 40, 'evidence_matched': True}],
}
PAYLOAD = authority.verification_payload(RECORD)


def run(argv, expect_zero=True):
    proc = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                          errors='replace')
    if expect_zero and proc.returncode != 0:
        raise SystemExit(f'{argv} -> {proc.returncode}\n{proc.stderr}')
    return proc


def openssl_version() -> str:
    return run(['openssl', 'version']).stdout.strip()


def sign(key: Path, payload: Path, out: Path) -> None:
    run(['openssl', 'dgst', '-sha256', '-sign', str(key), '-out', str(out), str(payload)])


def cross_check(pub: Path, payload: Path, signature: Path) -> str:
    proc = run(['openssl', 'dgst', '-sha256', '-verify', str(pub),
                '-signature', str(signature), str(payload)], expect_zero=False)
    return (proc.stdout or '').strip()


def key_pair(work: Path, name: str, kind: str, bits: int | None = None,
             curve: str | None = None) -> tuple[Path, Path]:
    key = work / f'{name}.pem'
    pub = work / f'{name}-pub.pem'
    if kind == 'rsa':
        run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
             f'rsa_keygen_bits:{bits}', '-out', str(key)])
    else:
        run(['openssl', 'ecparam', '-name', curve, '-genkey', '-noout', '-out', str(key)])
    run(['openssl', 'pkey', '-in', str(key), '-pubout', '-out', str(pub)])
    return key, pub


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix='pm-b1-vectors-'))
    payload_file = work / 'payload.bin'
    payload_file.write_bytes(PAYLOAD)
    vectors: dict = {'generator': openssl_version(), 'record': RECORD,
                     'payload_sha256': __import__('hashlib').sha256(PAYLOAD).hexdigest()}

    rsa_key, rsa_pub = key_pair(work, 'rsa2048', 'rsa', bits=2048)
    sign(rsa_key, payload_file, work / 'rsa.sig')
    rsa_sig = (work / 'rsa.sig').read_bytes()
    flipped = bytearray(rsa_sig)
    flipped[-1] ^= 0x01
    tampered = work / 'rsa.tampered.sig'
    tampered.write_bytes(bytes(flipped))
    vectors['rsa2048'] = {
        'public_key_pem': rsa_pub.read_text(encoding='utf-8'),
        'signature_b64': base64.b64encode(rsa_sig).decode('ascii'),
        'openssl_says': cross_check(rsa_pub, payload_file, work / 'rsa.sig'),
        'openssl_says_for_tampered': cross_check(rsa_pub, payload_file, tampered),
    }
    _, small_pub = key_pair(work, 'rsa1024', 'rsa', bits=1024)
    vectors['rsa1024_public_key_pem'] = small_pub.read_text(encoding='utf-8')
    _, other_pub = key_pair(work, 'rsa-other', 'rsa', bits=2048)
    vectors['other_rsa_public_key_pem'] = other_pub.read_text(encoding='utf-8')

    ec_key, ec_pub = key_pair(work, 'ecp256', 'ec', curve='prime256v1')
    sign(ec_key, payload_file, work / 'ec.sig')
    ec_sig = (work / 'ec.sig').read_bytes()
    vectors['ecp256'] = {
        'public_key_pem': ec_pub.read_text(encoding='utf-8'),
        'signature_b64': base64.b64encode(ec_sig).decode('ascii'),
        'openssl_says': cross_check(ec_pub, payload_file, work / 'ec.sig'),
    }
    vectors['ecp256_non_canonical_r_b64'] = base64.b64encode(_non_canonical(ec_sig)).decode('ascii')
    vectors['ecp256_r_zero_b64'] = base64.b64encode(_zero_r(ec_sig)).decode('ascii')
    _, p384_pub = key_pair(work, 'ecp384', 'ec', curve='secp384r1')
    vectors['secp384r1_public_key_pem'] = p384_pub.read_text(encoding='utf-8')

    print(json.dumps(vectors, ensure_ascii=False, indent=1))
    return 0


def _rebuild(parts: list[tuple[int, bytes]]) -> bytes:
    body = b''.join(bytes([tag]) + _encode_length(len(value)) + value for tag, value in parts)
    return bytes([0x30]) + _encode_length(len(body)) + body


def _encode_length(size: int) -> bytes:
    if size < 0x80:
        return bytes([size])
    raw = size.to_bytes((size.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(raw)]) + raw


def _non_canonical(signature: bytes) -> bytes:
    items = authority._der_sequence(signature)
    tag, value = items[0]
    padded = b'\x00\x00' + value if value[0] & 0x80 else b'\x00' + value
    return _rebuild([(0x02, padded)] + items[1:])


def _zero_r(signature: bytes) -> bytes:
    items = authority._der_sequence(signature)
    return _rebuild([(0x02, b'\x00')] + items[1:])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
