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

Signature checking is performed here, in-process, with the standard library
only.  It never resolves an external program, so neither ``PATH`` nor any
environment variable can select or replace the verifier: an attacker who
controls the environment of the CLI still cannot make a forged signature pass.
See ``docs/decisions/ADR-0002-inprocess-signature-verifier.md``.

Accepting a JSON anchor only when ``GITHUB_ACTIONS`` is the literal ``true`` is
a misuse guard, not a cryptographic boundary: a local process can set any
environment variable.  The real boundary is that the CI anchor lives in a
repository secret outside the tree and the gate verifier runs from the base
commit; a local run with its own key and its own anchor can still obtain
``trusted`` without weakening the CI gate.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

ANCHOR_ENV = 'PROJECT_MEMORY_TRUST_ANCHOR'
APPROVAL_ANCHOR_ENV = 'PROJECT_MEMORY_APPROVAL_ANCHOR'
TRUST_ANCHOR_JSON_ENV = 'PROJECT_MEMORY_TRUST_ANCHOR_JSON'
APPROVAL_ANCHOR_JSON_ENV = 'PROJECT_MEMORY_APPROVAL_ANCHOR_JSON'
CI_CONTEXT_ENV = 'GITHUB_ACTIONS'
ANCHOR_SCHEMA = '1.0'
ANCHOR_KIND = 'project_memory_trust_anchor'
SUPPORTED_ALGORITHMS = ('rsa-sha256', 'ecdsa-sha256')
MIN_RSA_MODULUS_BITS = 2048
MAX_KEY_DER_BYTES = 65536
MAX_SIGNATURE_BYTES = 1024
ANCHOR_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
FINGERPRINT_HEX_PATTERN = re.compile(r'[0-9a-fA-F]{64}')


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


def verification_subject_payload(record: dict) -> bytes:
    """Bytes an approval event binds for a verification record.

    The digest excludes both ``authority`` (the detached signature envelope)
    and ``authority_evaluation`` (the local, recomputable verdict), so attaching
    a signature never changes what an approval references.  The algorithm is
    SHA-256 over the canonical JSON bytes of the remaining fields.
    """
    payload = {key: value for key, value in record.items()
               if key not in ('authority', 'authority_evaluation')}
    return canonical_bytes(payload)


def verification_subject_digest(record: dict) -> str:
    """SHA-256 hex digest of :func:`verification_subject_payload`."""
    return hashlib.sha256(verification_subject_payload(record)).hexdigest()


class _DerError(ValueError):
    """Malformed or unsupported DER input; always handled as fail-closed."""


def _der_read_tlv(buf: bytes, index: int) -> tuple[int, bytes, int]:
    """Return ``(tag, value, next)`` for the DER object starting at ``index``."""
    if index >= len(buf):
        raise _DerError('DER 数据截断')
    tag = buf[index]
    first = buf[index + 1] if index + 1 < len(buf) else None
    if first is None:
        raise _DerError('DER 数据截断')
    if first < 0x80:
        length, start = first, index + 2
    else:
        count = first & 0x7F
        if count == 0 or count > 4 or index + 2 + count > len(buf):
            raise _DerError('DER 长度编码非法')
        length = int.from_bytes(buf[index + 2:index + 2 + count], 'big')
        if length < 0x80:
            raise _DerError('DER 长度不是最小编码')
        start = index + 2 + count
    end = start + length
    if end > len(buf):
        raise _DerError('DER 内容越界')
    return tag, buf[start:end], end


def _der_children(body: bytes) -> list[tuple[int, bytes]]:
    items = []
    index = 0
    while index < len(body):
        tag, value, index = _der_read_tlv(body, index)
        items.append((tag, value))
    return items


def _der_sequence(encoded: bytes) -> list[tuple[int, bytes]]:
    tag, body, end = _der_read_tlv(encoded, 0)
    if tag != 0x30 or end != len(encoded):
        raise _DerError('期望 DER SEQUENCE')
    return _der_children(body)


def _der_integer(body: bytes) -> int:
    if not body:
        raise _DerError('DER INTEGER 为空')
    if body[0] & 0x80:
        raise _DerError('DER INTEGER 为负数')
    if len(body) > 1 and body[0] == 0x00 and not body[1] & 0x80:
        raise _DerError('DER INTEGER 不是最小编码')
    return int.from_bytes(body, 'big')


_RSA_OID = b'\x2a\x86\x48\x86\xf7\x0d\x01\x01\x01'
_EC_PUBLIC_KEY_OID = b'\x2a\x86\x48\xce\x3d\x02\x01'
_PRIME256V1_OID = b'\x2a\x86\x48\xce\x3d\x03\x01\x07'
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex('3031300d060960864801650304020105000420')


def _pem_der(pem: str) -> bytes:
    """Decode a SubjectPublicKeyInfo PEM body into its DER bytes."""
    head, tail = '-----BEGIN PUBLIC KEY-----', '-----END PUBLIC KEY-----'
    text = str(pem or '').strip()
    if head not in text or tail not in text:
        raise _DerError('公钥不是 SubjectPublicKeyInfo PEM')
    body = text.split(head, 1)[1].split(tail, 1)[0]
    try:
        der = base64.b64decode(''.join(body.split()), validate=True)
    except Exception as exc:  # noqa: BLE001 - malformed base64 is not a key
        raise _DerError(f'公钥 base64 非法：{exc}') from exc
    if len(der) > MAX_KEY_DER_BYTES:
        raise _DerError('公钥 DER 过大')
    return der


def public_key_fingerprint(pem: str) -> str:
    """SHA-256 of the DER SubjectPublicKeyInfo, lowercase hex.

    The DER bytes are hashed rather than the PEM text so that line endings and
    line wrapping cannot change the fingerprint.  It only proves "the public key
    in this anchor document is the one that was published"; proving that the
    issuer is a real person needs an out-of-repo channel.
    """
    return hashlib.sha256(_pem_der(pem)).hexdigest()


def _public_key(pem: str) -> tuple[str, int, int]:
    """Parse a SubjectPublicKeyInfo PEM into ``('rsa'|'ecdsa', a, b)``.

    RSA returns ``(modulus, publicExponent)``; ECDSA returns the uncompressed
    P-256 point coordinates ``(x, y)``.  Anything else is refused.
    """
    der = _pem_der(pem)
    algorithm = _der_sequence(der)
    if len(algorithm) != 2 or algorithm[0][0] != 0x30 or algorithm[1][0] != 0x03:
        raise _DerError('SubjectPublicKeyInfo 结构不符')
    fields = _der_children(algorithm[0][1])
    if len(fields) != 2 or fields[0][0] != 0x06:
        raise _DerError('AlgorithmIdentifier 结构不符')
    curve = fields[1][1] if fields[1][0] == 0x06 else None
    bit_string = algorithm[1][1]
    if not bit_string or bit_string[0] != 0x00:
        raise _DerError('BIT STRING 未字节对齐')
    key = bit_string[1:]
    if fields[0][1] == _RSA_OID:
        parts = _der_sequence(key)
        if len(parts) != 2 or parts[0][0] != 0x02 or parts[1][0] != 0x02:
            raise _DerError('RSAPublicKey 结构不符')
        modulus, exponent = _der_integer(parts[0][1]), _der_integer(parts[1][1])
        if modulus.bit_length() < MIN_RSA_MODULUS_BITS:
            raise _DerError(f'RSA 模数小于 {MIN_RSA_MODULUS_BITS} 位')
        if exponent < 3 or exponent % 2 == 0 or exponent.bit_length() > 64:
            raise _DerError('RSA 公钥指数非法')
        return 'rsa', modulus, exponent
    if fields[0][1] == _EC_PUBLIC_KEY_OID and curve == _PRIME256V1_OID:
        if len(key) != 65 or key[0] != 0x04:
            raise _DerError('仅支持 P-256 未压缩公钥点')
        return 'ecdsa', int.from_bytes(key[1:33], 'big'), int.from_bytes(key[33:65], 'big')
    raise _DerError('信任锚公钥的算法或曲线不受支持')


def _equals(left: bytes, right: bytes) -> bool:
    """Length-checked byte comparison that does not return early."""
    if len(left) != len(right):
        return False
    accumulator = 0
    for a, b in zip(left, right):
        accumulator |= a ^ b
    return accumulator == 0


def _rsa_verify(modulus: int, exponent: int, message: bytes, signature: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 with SHA-256, public operation only."""
    size = (modulus.bit_length() + 7) // 8
    if len(signature) != size or len(signature) > MAX_SIGNATURE_BYTES:
        return False
    value = int.from_bytes(signature, 'big')
    if value >= modulus:
        return False
    encoded = pow(value, exponent, modulus).to_bytes(size, 'big')
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(message).digest()
    padding = size - len(digest_info) - 3
    if padding < 8:
        return False
    return _equals(encoded, b'\x00\x01' + b'\xff' * padding + b'\x00' + digest_info)


# NIST P-256 (prime256v1) domain parameters.
_P256_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_P256_A = _P256_P - 3
_P256_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_P256_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
           0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _point_double(point):
    if point is None:
        return None
    x, y = point
    if y == 0:
        return None
    slope = (3 * x * x + _P256_A) * pow(2 * y, -1, _P256_P) % _P256_P
    result_x = (slope * slope - 2 * x) % _P256_P
    return (result_x, (slope * (x - result_x) - y) % _P256_P)


def _point_add(left, right):
    if left is None:
        return right
    if right is None:
        return left
    if left[0] == right[0]:
        if left[1] != right[1]:
            return None
        return _point_double(left)
    slope = (right[1] - left[1]) * pow(right[0] - left[0], -1, _P256_P) % _P256_P
    result_x = (slope * slope - left[0] - right[0]) % _P256_P
    return (result_x, (slope * (left[0] - result_x) - left[1]) % _P256_P)


def _point_multiply(scalar: int, point):
    result, addend = None, point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_double(addend)
        scalar >>= 1
    return result


def _point_on_curve(x: int, y: int) -> bool:
    return (y * y - (pow(x, 3, _P256_P) + _P256_A * x + _P256_B)) % _P256_P == 0


def _ecdsa_verify(point_x: int, point_y: int, message: bytes, signature: bytes) -> bool:
    """ECDSA over P-256 with SHA-256; strict DER and full range checks."""
    if len(signature) > MAX_SIGNATURE_BYTES:
        return False
    if not _point_on_curve(point_x, point_y) or not (0 < point_x < _P256_P):
        return False
    components = _der_sequence(signature)
    if len(components) != 2 or any(tag != 0x02 for tag, _ in components):
        return False
    radius, scalar = (_der_integer(value) for _, value in components)
    if not 0 < radius < _P256_N or not 0 < scalar < _P256_N:
        return False
    integer = int.from_bytes(hashlib.sha256(message).digest(), 'big')
    weight = pow(scalar, -1, _P256_N)
    scaled = _point_add(_point_multiply(integer * weight % _P256_N, _P256_G),
                        _point_multiply(radius * weight % _P256_N, (point_x, point_y)))
    return scaled is not None and scaled[0] % _P256_N == radius


def _verify_signature(anchor: dict, payload: bytes, signature_b64: str,
                      algorithm: str) -> tuple[bool, str]:
    """Check a detached signature with the pinned in-process implementation.

    No subprocess, no ``PATH`` lookup, no output-string trust: acceptance comes
    only from the arithmetic identity against the anchor's public key.  Every
    failure mode returns ``(False, reason)``.
    """
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception as exc:  # noqa: BLE001 - any bad encoding is untrusted
        return False, f'签名不是合法 base64：{exc}'
    if not signature:
        return False, '签名为空'
    try:
        kind, first, second = _public_key(anchor.get('public_key_pem'))
    except (_DerError, ValueError, IndexError) as exc:
        return False, f'信任锚公钥无法解析：{exc}'
    expected = {'rsa-sha256': 'rsa', 'ecdsa-sha256': 'ecdsa'}.get(algorithm)
    if expected != kind:
        return False, f'验签实现与信任锚公钥不匹配（algorithm={algorithm}，密钥类型={kind}）'
    try:
        if kind == 'rsa':
            verified = _rsa_verify(first, second, payload, signature)
        else:
            verified = _ecdsa_verify(first, second, payload, signature)
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        return False, f'签名运算失败（fail-closed）：{exc}'
    if not verified:
        return False, '签名验证失败'
    return True, 'signature verified'


_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_SE_FILE_OBJECT = 1
_OWNER_SECURITY_INFORMATION = 0x00000001


def _windows_apis():
    """Load the system libraries that report SIDs.

    Resolved through the OS loader by module name, never through ``PATH``, and
    never through a helper process: the identity of the trust-root owner check
    must not depend on the caller's environment either.
    """
    import ctypes
    from ctypes import wintypes
    return (ctypes, wintypes,
            ctypes.WinDLL('kernel32', use_last_error=True),
            ctypes.WinDLL('advapi32', use_last_error=True))


def _sid_string(sid: int) -> str | None:
    ctypes, wintypes, kernel32, advapi32 = _windows_apis()
    text = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(text)):
        return None
    value = text.value
    kernel32.LocalFree(text)
    return value or None


def _current_user_sid() -> str | None:
    """SID of the token the current process actually runs as."""
    try:
        ctypes, wintypes, kernel32, advapi32 = _windows_apis()
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                              ctypes.POINTER(wintypes.HANDLE)]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), _TOKEN_QUERY,
                                         ctypes.byref(token)):
            return None
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                 ctypes.c_void_p, wintypes.DWORD,
                                                 ctypes.POINTER(wintypes.DWORD)]
        needed = wintypes.DWORD()
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        if not needed.value:
            return None
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, _TOKEN_USER, buffer, needed,
                                            ctypes.byref(needed)):
            return None
        return _sid_string(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
    except (OSError, ValueError, AttributeError):
        return None


def _file_owner_sid(path: Path) -> str | None:
    """Owner SID of a file, or None when it cannot be determined."""
    try:
        ctypes, wintypes, kernel32, advapi32 = _windows_apis()
        pointer = ctypes.POINTER(ctypes.c_void_p)
        advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
        advapi32.GetNamedSecurityInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                                   wintypes.DWORD, pointer, pointer,
                                                   pointer, pointer, pointer]
        owner = ctypes.c_void_p()
        group = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        sacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        code = advapi32.GetNamedSecurityInfoW(str(path), _SE_FILE_OBJECT,
                                              _OWNER_SECURITY_INFORMATION,
                                              ctypes.byref(owner), ctypes.byref(group),
                                              ctypes.byref(dacl), ctypes.byref(sacl),
                                              ctypes.byref(descriptor))
        try:
            if code != 0 or not owner.value:
                return None
            return _sid_string(owner.value)
        finally:
            if descriptor.value:
                kernel32.LocalFree(descriptor)
    except (OSError, ValueError, AttributeError):
        return None


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
        owner = _file_owner_sid(path)
        if not owner:
            return False, '无法确认信任锚所有者'
        principal = _current_user_sid()
        if not principal:
            return False, '无法确认当前进程的用户身份'
        if owner.casefold() == principal.casefold():
            return False, '信任锚所有者是当前用户；不能作为独立信任根'
        return True, f'owner={owner}'
    if hasattr(os, 'geteuid') and stat.st_uid == os.geteuid():
        return False, '信任锚所有者是当前用户；不能作为独立信任根'
    if stat.st_mode & 0o022:
        return False, '信任锚对组或其他用户可写'
    return True, f'uid={stat.st_uid}'


class _AnchorFieldError(ValueError):
    """A malformed optional anchor field.  Every such field fails closed."""


def _anchor_timestamp(value, field: str) -> datetime:
    """Parse an ISO-8601 anchor timestamp into UTC; no timezone means invalid."""
    text = str(value).strip()
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _AnchorFieldError(f'{field} 不是合法 ISO-8601 时间：{value}') from exc
    if moment.tzinfo is None:
        raise _AnchorFieldError(f'{field} 缺少时区（必须带 Z 或 ±HH:MM）：{value}')
    return moment.astimezone(timezone.utc)


def _anchor_optional_problem(value: dict) -> str | None:
    """Validate the optional lifecycle fields of an anchor document.

    Revocation and expiry come only from this document, i.e. from the protected
    anchor file or the CI secret; nothing inside the repository can revoke an
    anchor.  Unrecognized extra fields are ignored for forward compatibility,
    but they never grant trust.
    """
    not_before, not_after = value.get('not_before'), value.get('not_after')
    try:
        start = (_anchor_timestamp(not_before, 'not_before')
                 if not_before is not None else None)
        end = (_anchor_timestamp(not_after, 'not_after')
               if not_after is not None else None)
    except _AnchorFieldError as exc:
        return str(exc)
    if start is not None and end is not None and start > end:
        return f'not_before（{not_before}）晚于 not_after（{not_after}）'
    revoked = value.get('revoked_anchor_ids')
    if revoked is not None:
        if not isinstance(revoked, list):
            return 'revoked_anchor_ids 必须是 JSON 数组'
        for item in revoked:
            if not isinstance(item, str) or not ANCHOR_ID_PATTERN.fullmatch(item):
                return f'revoked_anchor_ids 含非法条目：{item!r}'
    fingerprint = value.get('fingerprint_sha256')
    if fingerprint is not None:
        declared = str(fingerprint).strip()
        if declared.lower().startswith('sha256:'):
            declared = declared.split(':', 1)[1].strip()
        if not FINGERPRINT_HEX_PATTERN.fullmatch(declared):
            return 'fingerprint_sha256 必须是 64 位十六进制（可带 sha256: 前缀）'
        try:
            actual = public_key_fingerprint(value['public_key_pem'])
        except _DerError as exc:
            return f'fingerprint_sha256 无法核对公钥：{exc}'
        if declared.lower() != actual:
            return f'fingerprint_sha256（{declared.lower()}）与公钥实算（{actual}）不一致'
    return None


def _anchor_lifecycle_problem(anchor: dict, now: datetime | None = None) -> str | None:
    """Validity window and self-revocation; ``None`` means the anchor is usable.

    This runs on every trust decision, so an expired or revoked anchor stops
    later verifications while leaving already-written records and merged commits
    untouched.  ``now`` exists only to keep tests readable; production always
    uses the current UTC time with a closed interval.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    not_before, not_after = anchor.get('not_before'), anchor.get('not_after')
    try:
        if (not_before is not None
                and _anchor_timestamp(not_before, 'not_before') > moment):
            return f'信任锚尚未生效（not_before={not_before}）'
        if (not_after is not None
                and _anchor_timestamp(not_after, 'not_after') < moment):
            return f'信任锚已过期（not_after={not_after}）'
    except _AnchorFieldError as exc:
        return str(exc)
    anchor_id = anchor.get('anchor_id')
    revoked = anchor.get('revoked_anchor_ids')
    if isinstance(revoked, list) and anchor_id in revoked:
        return f'信任锚已吊销（anchor_id={anchor_id} 在 revoked_anchor_ids 中）'
    return None


def _anchor_document(value) -> tuple[dict | None, str]:
    """Validate the shape of an anchor document; no owner or trust check."""
    if not isinstance(value, dict):
        return None, '信任锚必须是 JSON 对象'
    if value.get('kind') != ANCHOR_KIND or value.get('schema_version') != ANCHOR_SCHEMA:
        return None, '信任锚 kind/schema_version 不匹配'
    if value.get('algorithm') not in SUPPORTED_ALGORITHMS:
        return None, '信任锚 algorithm 不受支持'
    for field in ('anchor_id', 'issuer', 'public_key_pem'):
        if not isinstance(value.get(field), str) or not value[field].strip():
            return None, f'信任锚缺少 {field}'
    problem = _anchor_optional_problem(value)
    if problem:
        return None, problem
    return dict(value), 'ok'


def _env_value(name: str | None) -> str:
    """Read one of the fixed trust-anchor environment names.

    The whitelist is deliberate: no caller can make ``authority`` read an
    arbitrary environment variable, and it still cannot select a verifier.
    """
    if name == ANCHOR_ENV:
        return os.environ.get(ANCHOR_ENV, '')
    if name == APPROVAL_ANCHOR_ENV:
        return os.environ.get(APPROVAL_ANCHOR_ENV, '')
    if name == TRUST_ANCHOR_JSON_ENV:
        return os.environ.get(TRUST_ANCHOR_JSON_ENV, '')
    if name == APPROVAL_ANCHOR_JSON_ENV:
        return os.environ.get(APPROVAL_ANCHOR_JSON_ENV, '')
    if name == CI_CONTEXT_ENV:
        return os.environ.get(CI_CONTEXT_ENV, '')
    return ''


def _is_ci_context() -> bool:
    return _env_value(CI_CONTEXT_ENV) == 'true'


def _load_file_anchor(repo: Path, value: str) -> tuple[dict | None, str]:
    """Load an anchor file named by a path environment variable."""
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
    anchor, reason = _anchor_document(anchor)
    if anchor is None:
        return None, reason
    protected, detail = anchor_is_protected(resolved)
    if not protected:
        return None, detail
    return {**anchor, 'path': str(resolved), 'protection': detail}, 'ok'


def _load_json_anchor(name: str, value: str) -> tuple[dict | None, str]:
    """Parse a JSON anchor from a CI secret; shape checks match file anchors."""
    try:
        anchor = json.loads(value)
    except Exception as exc:  # noqa: BLE001 - any malformed anchor is untrusted
        return None, f'{name} 不是合法 JSON：{exc}'
    anchor, reason = _anchor_document(anchor)
    if anchor is None:
        return None, f'{name}：{reason}'
    return {**anchor, 'path': f'<env:{name}>', 'protection': 'ci-secret'}, 'ok'


def _anchor_with_lifecycle(anchor: dict | None, reason: str) -> tuple[dict | None, str]:
    """Apply the lifecycle decision to an already document-valid anchor."""
    if anchor is None:
        return None, reason
    problem = _anchor_lifecycle_problem(anchor)
    if problem:
        return None, problem
    return anchor, reason


def load_anchor(repo: Path, env_name: str = ANCHOR_ENV,
                json_env: str | None = None) -> tuple[dict | None, str]:
    """Load the trust anchor from a protected file or a CI-only JSON secret.

    An explicitly configured file anchor is authoritative: if it cannot be
    loaded (missing, inside the repository, wrong shape, not owner-protected,
    outside its validity window, or revoked) the function fails closed and never
    falls back to the JSON anchor.

    The JSON form is accepted only when ``GITHUB_ACTIONS`` is exactly ``true``
    and no file anchor was configured.  That flag is a misuse guard, not a
    cryptographic boundary: a local process can set any environment variable,
    so non-CI runs keep using an owner-protected file.  This does not weaken
    the CI gate: there the JSON value comes from a repository secret outside
    the tree and the verifier runs from the base commit.  A local run with its
    own key and its own anchor can still obtain ``trusted``.  The JSON
    kind/schema/algorithm/field checks are identical to the file path; only the
    file-owner check is skipped because the secret has no file owner.

    Both forms are also checked for ``not_before``/``not_after``/self-revocation
    here, which is why every trust decision in this module inherits the
    lifecycle: they all read the anchor through this function.
    """
    env_name = env_name or ANCHOR_ENV
    value = _env_value(env_name).strip()
    if value:
        return _anchor_with_lifecycle(*_load_file_anchor(repo, value))
    json_value = _env_value(json_env).strip() if json_env else ''
    if json_value:
        if _is_ci_context():
            return _anchor_with_lifecycle(*_load_json_anchor(json_env, json_value))
        return None, (f'未配置受保护的信任锚（{env_name}）；'
                      f'{json_env} 只在 CI（{CI_CONTEXT_ENV}=true）中生效')
    return None, f'未配置受保护的信任锚（{env_name}）'


def load_anchor_document(path) -> tuple[dict | None, str]:
    """Load an anchor file for a local format and signature check only.

    This intentionally performs no owner/protection check and no lifecycle
    decision: ``not_before``/``not_after`` and ``revoked_anchor_ids`` are only
    *structurally* validated here (plus the fingerprint against the public key).
    It answers "is this a well-formed public-key document?", never "do I trust
    it?".  The trust decision is made only at evaluation or gate time by
    re-reading the anchor named by ``PROJECT_MEMORY_APPROVAL_ANCHOR`` through
    ``load_anchor``, which is where expiry and revocation are enforced.
    """
    path = Path(path)
    if not path.is_file():
        return None, f'信任锚不是文件：{path}'
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:  # noqa: BLE001 - any malformed anchor is untrusted
        return None, f'信任锚不是合法 JSON：{exc}'
    return _anchor_document(value)


def verify_detached_signature(anchor: dict, payload: bytes, signature_b64: str,
                              algorithm: str) -> tuple[bool, str]:
    """Public detached-signature check with a supplied anchor document."""
    return _verify_signature(anchor, payload, signature_b64, algorithm)


def verification_authority(repo: Path, record: dict) -> dict:
    """Return the authority status of a verification record.

    ``trusted`` is true only after a signature from the configured anchor
    verifies.  A record that merely contains ``authority.status == "trusted"``
    is untrusted.
    """
    anchor, anchor_reason = load_anchor(repo, json_env=TRUST_ANCHOR_JSON_ENV)
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


EXECUTION_ATTESTATION_KIND = 'execution_attestation'
EXECUTION_EXCEPTION_KIND = 'execution_exception'
EXECUTION_RECORD_SCHEMA = '1.0'


def execution_record_payload(record: dict) -> bytes:
    """Signed payload for an execution attestation/exception (excludes authority)."""
    payload = {key: value for key, value in record.items() if key != 'authority'}
    return canonical_bytes(payload)


def execution_record_digest(record: dict) -> str:
    return hashlib.sha256(execution_record_payload(record)).hexdigest()


def _execution_record_authority(repo: Path, record: dict, label: str,
                                env_name: str = ANCHOR_ENV,
                                json_env: str | None = TRUST_ANCHOR_JSON_ENV) -> dict:
    """Verify an execution record against the protected anchor; fail closed."""
    anchor, anchor_reason = load_anchor(repo, env_name, json_env=json_env)
    if anchor is None:
        return {'trusted': False, 'status': 'unconfigured',
                'reason': anchor_reason, 'anchor_id': None, 'issuer': None}
    envelope = record.get('authority') if isinstance(record, dict) else None
    if not isinstance(envelope, dict):
        return {'trusted': False, 'status': 'untrusted',
                'reason': f'{label}缺少 authority 信封（本地写出的记录一律不可信）',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    if envelope.get('anchor_id') != anchor['anchor_id']:
        return {'trusted': False, 'status': 'untrusted',
                'reason': f'{label}的 authority.anchor_id 与受保护信任锚不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    if envelope.get('issuer') != anchor['issuer']:
        return {'trusted': False, 'status': 'untrusted',
                'reason': f'{label}的 authority.issuer 与受保护信任锚不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    algorithm = envelope.get('algorithm')
    if algorithm != anchor['algorithm']:
        return {'trusted': False, 'status': 'untrusted',
                'reason': f'{label}的 authority.algorithm 与信任锚不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    payload = execution_record_payload(record)
    digest = hashlib.sha256(payload).hexdigest()
    if envelope.get('signed_payload_sha256') != digest:
        return {'trusted': False, 'status': 'untrusted',
                'reason': f'{label}的 signed_payload_sha256 与记录内容不一致',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    signature = envelope.get('signature_b64')
    if not isinstance(signature, str) or not signature.strip():
        return {'trusted': False, 'status': 'untrusted',
                'reason': f'{label}的 authority.signature_b64 缺失',
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer']}
    ok, detail = _verify_signature(anchor, payload, signature, algorithm)
    return {'trusted': ok, 'status': 'trusted' if ok else 'untrusted',
            'reason': detail, 'anchor_id': anchor['anchor_id'],
            'issuer': anchor['issuer'], 'signed_payload_sha256': digest}


def verify_execution_attestation_authority(repo: Path, record: dict) -> dict:
    """Return the authority status of a signed execution attestation."""
    return _execution_record_authority(repo, record, '执行 attestation')


def verify_execution_exception_authority(repo: Path, record: dict) -> dict:
    """Return the authority status of a signed human exception."""
    return _execution_record_authority(repo, record, '人类例外')


def signed_record_payload(record: dict) -> bytes:
    """Signed payload for any detached-signature record (excludes ``authority``)."""
    return execution_record_payload(record)


def signed_record_digest(record: dict) -> str:
    return execution_record_digest(record)


def signed_record_authority(repo: Path, record: dict, label: str = '签名记录') -> dict:
    """Verify a detached anchor signature over ``record`` minus ``authority``.

    This is the generic entry point used by audit checkpoints.  It performs the
    same fail-closed checks as verification/execution records and never accepts a
    self-declared ``authority.status``.
    """
    return _execution_record_authority(repo, record, label)


def approval_authority(repo: Path, record: dict) -> dict:
    """Return the authority status of a signed approval event.

    Trust comes only from the approval anchor named by
    ``PROJECT_MEMORY_APPROVAL_ANCHOR``.  A valid signature is still untrusted
    when ``record["approver"]`` differs from that anchor's ``issuer``: the
    approver identity is the signer, not a self-declared field.
    """
    verdict = _execution_record_authority(repo, record, '签名审批',
                                          env_name=APPROVAL_ANCHOR_ENV,
                                          json_env=APPROVAL_ANCHOR_JSON_ENV)
    if not verdict.get('trusted'):
        return verdict
    approver = record.get('approver') if isinstance(record, dict) else None
    if approver != verdict.get('issuer'):
        return {**verdict, 'trusted': False, 'status': 'untrusted',
                'reason': '审批记录的 approver 与审批锚 issuer 不一致'}
    return verdict


def evidence_authority(repo: Path, record: dict) -> dict:
    """Return the authority status of a signed evidence manifest.

    Manifests share the approval anchor and carry no approver field, so only
    the anchor signature decides trust.  Everything else (commit, tree, file
    hashes) is checked by the caller.
    """
    return _execution_record_authority(repo, record, '证据清单',
                                       env_name=APPROVAL_ANCHOR_ENV,
                                       json_env=APPROVAL_ANCHOR_JSON_ENV)
