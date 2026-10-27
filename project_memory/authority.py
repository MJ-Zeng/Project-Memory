"""Authoritative verification trust anchor (fail-closed).

A verification record is *not* authoritative because its JSON says
``verified: true``.  It is authoritative only when an out-of-repo trust anchor
authorizes a detached signature over the record.  The anchor contains a public
key; the matching private key must be held by a human or CI signer outside the
agent's write scope.

This module deliberately does not create keys, sign records, or accept a
self-declared ``authority.status == "trusted"``.  When no protected anchor is
configured, every record is ``unconfigured``/``untrusted`` and no Goal can be
achieved automatically.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

ANCHOR_ENV = 'PROJECT_MEMORY_TRUST_ANCHOR'
OPENSSL_ENV = 'PROJECT_MEMORY_OPENSSL'
ANCHOR_SCHEMA = '1.0'
ANCHOR_KIND = 'project_memory_trust_anchor'
SUPPORTED_ALGORITHMS = ('rsa-sha256', 'ecdsa-sha256')


def canonical_bytes(value) -> bytes:
    """Stable bytes for hashing/signing; key order and whitespace are irrelevant."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def canonical_digest(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def verification_payload(record: dict) -> bytes:
    """The signed payload: the record without its own authority envelope."""
    payload = {key: value for key, value in record.items() if key != 'authority'}
    return canonical_bytes(payload)


def verification_digest(record: dict) -> str:
    return hashlib.sha256(verification_payload(record)).hexdigest()


def _openssl() -> str | None:
    candidate = os.environ.get(OPENSSL_ENV, '').strip() or 'openssl'
    return shutil.which(candidate)


def _current_principal() -> str:
    return (os.environ.get('USERNAME') or os.environ.get('USER') or '').strip().casefold()


def _windows_owner(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             f"(Get-Acl -LiteralPath '{str(path)}').Owner"],
            capture_output=True, text=True, encoding='utf-8', timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or '').strip() or None


def anchor_is_protected(path: Path) -> tuple[bool, str]:
    """Conservative check that the current agent cannot rewrite the anchor.

    This is not a substitute for deployment-time ACLs: a same-user process that
    owns the anchor can change it.  The check therefore rejects writable files
    and files owned by the current user instead of assuming protection.
    """
    try:
        stat = path.stat()
    except OSError as exc:
        return False, f'无法读取信任锚：{exc}'
    if os.access(path, os.W_OK):
        return False, '信任锚对当前进程可写；必须由仓库外受保护主体持有'
    if platform.system() == 'Windows':
        owner = _windows_owner(path)
        if not owner:
            return False, '无法确认信任锚所有者'
        principal = _current_principal()
        owner_name = owner.split('\\')[-1].casefold()
        if principal and (owner_name == principal or owner.casefold().endswith('\\' + principal)):
            return False, '信任锚所有者是当前用户；不能作为独立信任根'
        return True, f'owner={owner}'
    if hasattr(os, 'geteuid') and stat.st_uid == os.geteuid():
        return False, '信任锚所有者是当前用户；不能作为独立信任根'
    if stat.st_mode & 0o022:
        return False, '信任锚对组或其他用户可写'
    return True, f'uid={stat.st_uid}'


def load_anchor(repo: Path) -> tuple[dict | None, str]:
    value = os.environ.get(ANCHOR_ENV, '').strip()
    if not value:
        return None, '未配置受保护的信任锚（PROJECT_MEMORY_TRUST_ANCHOR）'
    try:
        resolved = Path(value).resolve()
    except OSError as exc:
        return None, f'信任锚路径无效：{exc}'
    try:
        resolved.relative_to(repo.resolve())
    except ValueError:
        pass
    else:
        return None, '信任锚位于仓库内；仓库内文件可由 Agent 改写，不能作为信任根'
    if not resolved.is_file():
        return None, f'信任锚不是文件：{resolved}'
    try:
        anchor = json.loads(resolved.read_text(encoding='utf-8'))
    except Exception as exc:  # noqa: BLE001 - any malformed anchor is untrusted
        return None, f'信任锚不是合法 JSON：{exc}'
    if not isinstance(anchor, dict):
        return None, '信任锚必须是 JSON 对象'
    if anchor.get('kind') != ANCHOR_KIND or anchor.get('schema_version') != ANCHOR_SCHEMA:
        return None, '信任锚 kind/schema_version 不匹配'
    if anchor.get('algorithm') not in SUPPORTED_ALGORITHMS:
        return None, '信任锚 algorithm 不受支持'
    for field in ('anchor_id', 'issuer', 'public_key_pem'):
        if not isinstance(anchor.get(field), str) or not anchor[field].strip():
            return None, f'信任锚缺少 {field}'
    protected, detail = anchor_is_protected(resolved)
    if not protected:
        return None, detail
    return {**anchor, 'path': str(resolved), 'protection': detail}, 'ok'


def _verify_signature(anchor: dict, payload: bytes, signature_b64: str,
                      algorithm: str) -> tuple[bool, str]:
    openssl = _openssl()
    if not openssl:
        return False, '找不到 openssl，无法验证签名（fail-closed）'
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception as exc:  # noqa: BLE001
        return False, f'签名不是合法 base64：{exc}'
    with tempfile.TemporaryDirectory(prefix='pm-authority-') as tmp:
        root = Path(tmp)
        pub = root / 'public.pem'
        data = root / 'payload.bin'
        sig = root / 'signature.bin'
        pub.write_text(anchor['public_key_pem'], encoding='utf-8')
        data.write_bytes(payload)
        sig.write_bytes(signature)
        result = subprocess.run(
            [openssl, 'dgst', '-sha256', '-verify', str(pub),
             '-signature', str(sig), str(data)],
            capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode != 0:
        detail = (result.stdout or result.stderr or '').strip()
        return False, f'签名验证失败：{detail or "openssl 返回非 0"}'
    return True, 'signature verified'


def verification_authority(repo: Path, record: dict) -> dict:
    """Return the authority status of a verification record.

    ``trusted`` is true only after a signature from the configured anchor
    verifies.  A record that merely contains ``authority.status == "trusted"``
    is untrusted.
    """
    anchor, anchor_reason = load_anchor(repo)
    if anchor is None:
        return {'trusted': False, 'status': 'unconfigured',
                'reason': anchor_reason, 'anchor_id': None, 'issuer': None}
    envelope = record.get('authority')
    if not isinstance(envelope, dict):
        return {'trusted': False, 'status': 'untrusted',
                'reason': '验证记录缺少 authority 信封（本地写出的记录一律不可信）',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    if envelope.get('anchor_id') != anchor['anchor_id']:
        return {'trusted': False, 'status': 'untrusted',
                'reason': 'authority.anchor_id 与受保护信任锚不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    if envelope.get('issuer') != anchor['issuer']:
        return {'trusted': False, 'status': 'untrusted',
                'reason': 'authority.issuer 与受保护信任锚不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    algorithm = envelope.get('algorithm')
    if algorithm != anchor['algorithm']:
        return {'trusted': False, 'status': 'untrusted',
                'reason': 'authority.algorithm 与信任锚不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    payload = verification_payload(record)
    digest = hashlib.sha256(payload).hexdigest()
    if envelope.get('signed_payload_sha256') != digest:
        return {'trusted': False, 'status': 'untrusted',
                'reason': 'authority.signed_payload_sha256 与记录内容不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    signature = envelope.get('signature_b64')
    if not isinstance(signature, str) or not signature.strip():
        return {'trusted': False, 'status': 'untrusted',
                'reason': 'authority.signature_b64 缺失',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    ok, detail = _verify_signature(anchor, payload, signature, algorithm)
    return {'trusted': ok, 'status': 'trusted' if ok else 'untrusted',
            'reason': detail, 'anchor_id': anchor['anchor_id'],
            'issuer': anchor['issuer'], 'signed_payload_sha256': digest}


def untrusted_envelope(reason: str) -> dict:
    """Envelope written by the local CLI.  Never trusted without a real signer."""
    return {'status': 'untrusted', 'issuer': 'local-cli', 'anchor_id': None,
            'algorithm': None, 'signed_payload_sha256': None,
            'signature_b64': None, 'reason': reason}
