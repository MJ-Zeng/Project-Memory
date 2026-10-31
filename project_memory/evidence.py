"""Signed evidence manifests: bind evidence files to one commit and tree.

A manifest is a detached-signature record signed by the same out-of-repo
approval anchor used for approval events.  The signature proves that the anchor
holder vouches for *this* list of files at *this* commit; it does not prove that
a protected executor produced the files or that the commands really ran (see
ADR-0003).  Verification re-scans the working tree and fails closed: no anchor,
bad signature, foreign repository, links or other reparse points, changed
bytes, missing file, wrong commit or wrong tree all yield exit code 2.
"""
from __future__ import annotations

import base64
import hashlib
import os
import platform as _platform
import re
import stat
from pathlib import Path

from . import __version__
from . import authority
from .common import PMError, json_text, safe_json, utc_now, write_new
from .coordination import _approval_repository, _approval_repository_matches
from .execution import resolve_commit

MANIFEST_KIND = 'evidence_manifest'
MANIFEST_SCHEMA = '1.0'
GIT_SHA = re.compile(r'[0-9a-f]{40}')
SHA256 = re.compile(r'[0-9a-f]{64}')


# ------------------------------------------------------------------ record core

def _manifest_core(record: dict) -> dict:
    """Fields covered by ``manifest_id`` (excludes the id and its signature)."""
    return {key: value for key, value in record.items()
            if key not in ('manifest_id', 'authority')}


def _manifest_id(record: dict) -> str:
    """Deterministic id: ``EVM-`` plus 12 hex of the canonical payload digest."""
    return 'EVM-' + authority.canonical_digest(_manifest_core(record))[:12]


def _record_path(value) -> str:
    """Validate a repository-relative ``/`` path; reject anything ambiguous."""
    text = value if isinstance(value, str) else ''
    if not text or text != text.strip():
        raise PMError('files.path 不能为空或包含首尾空白')
    if '\\' in text:
        raise PMError(f'files.path 必须使用 / 分隔：{text!r}')
    if text.startswith('/') or re.match(r'^[A-Za-z]:', text):
        raise PMError(f'files.path 必须是仓库相对路径：{text!r}')
    parts = text.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise PMError(f'files.path 含空段、. 或 ..：{text!r}')
    return text


_MOUNT_POINT_TAG = 0xA0000003


def _link_kind(st) -> str | None:
    """Name a link-like component; junctions are reparse points, not symlinks."""
    if stat.S_ISLNK(st.st_mode):
        return '符号链接'
    tag = getattr(st, 'st_reparse_tag', 0)
    if not tag:
        return None
    if tag == _MOUNT_POINT_TAG:
        return '目录联接或挂载点'
    return f'reparse point（tag 0x{tag:X}）'


def _escapes_root(root: Path, path: Path) -> bool:
    """True when the resolved path is no longer below the resolved root."""
    resolved_root = Path(os.path.realpath(root))
    try:
        Path(os.path.realpath(path)).relative_to(resolved_root)
    except ValueError:
        return True
    return False


def _safe_file(repo: Path, rel: str) -> Path:
    """Join ``rel`` under ``repo``; reject links, junctions and escapes."""
    root = repo.resolve()
    current = root
    for part in rel.split('/'):
        current = current / part
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise PMError(f'证据文件不存在：{rel}（{exc}）') from exc
        kind = _link_kind(st)
        if kind:
            raise PMError(f'证据路径包含{kind}：{rel}')
    if not stat.S_ISREG(os.lstat(current).st_mode):
        raise PMError(f'证据路径不是普通文件：{rel}')
    if _escapes_root(root, current):
        raise PMError(f'证据路径解析后位于仓库之外：{rel}')
    return current


# ---------------------------------------------------------------- path inputs

def _input_path(repo: Path, value) -> tuple[Path, str]:
    """Resolve one ``--path`` argument to ``(absolute path, repo-relative)``."""
    raw = str(value or '')
    if not raw.strip():
        raise PMError('--path 不能为空')
    root = repo.resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / raw
    absolute = Path(os.path.abspath(candidate))
    try:
        rel = absolute.relative_to(root)
    except ValueError:
        raise PMError(f'路径位于仓库之外：{raw}') from None
    if not rel.parts:
        raise PMError('不能把仓库根目录整体作为证据路径')
    # Reject a linked target or linked parent before walking a directory.
    current = root
    for part in rel.parts:
        current = current / part
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise PMError(f'路径不存在：{raw}（{exc}）') from exc
        kind = _link_kind(st)
        if kind:
            raise PMError(f'拒绝{kind}：{raw}')
    if _escapes_root(root, current):
        raise PMError(f'路径解析后位于仓库之外：{raw}')
    return current, rel.as_posix()


def _walk(directory: Path, root: Path, found: dict[str, Path]) -> None:
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError as exc:
        raise PMError(f'无法读取目录 {directory}：{exc}') from exc
    for entry in entries:
        path = Path(entry.path)
        rel = path.relative_to(root).as_posix()
        try:
            st = os.lstat(path)
        except OSError as exc:
            raise PMError(f'无法读取证据路径 {path}：{exc}') from exc
        kind = _link_kind(st)
        if kind:
            raise PMError(f'拒绝{kind}：{rel}')
        if _escapes_root(root, path):
            raise PMError(f'证据路径解析后位于仓库之外：{rel}')
        if stat.S_ISDIR(st.st_mode):
            _walk(path, root, found)
        elif stat.S_ISREG(st.st_mode):
            if rel in found:
                raise PMError(f'证据路径重复：{rel}')
            found[rel] = path
        else:
            raise PMError(f'不是普通文件：{rel}')


def collect_files(repo: Path, values) -> list[dict]:
    """Expand files/directories into sorted ``{path, sha256, bytes}`` entries."""
    root = repo.resolve()
    found: dict[str, Path] = {}
    for value in values:
        target, rel = _input_path(repo, value)
        mode = os.lstat(target).st_mode
        if stat.S_ISDIR(mode):
            _walk(target, root, found)
        elif stat.S_ISREG(mode):
            if rel in found:
                raise PMError(f'证据路径重复：{rel}')
            found[rel] = target
        else:
            raise PMError(f'不是普通文件：{rel}')
    if not found:
        raise PMError('证据清单不能为空：没有收集到任何普通文件')
    files = []
    for rel in sorted(found):
        data = found[rel].read_bytes()
        files.append({'path': rel, 'sha256': hashlib.sha256(data).hexdigest(),
                      'bytes': len(data)})
    return files


# ------------------------------------------------------------------- structure

def _structure_problem(record) -> str | None:
    """Structural validation shared by attach and verify; no trust decision."""
    if not isinstance(record, dict):
        return '证据清单必须是 JSON 对象'
    if record.get('kind') != MANIFEST_KIND:
        return 'kind 不是 evidence_manifest'
    if record.get('schema_version') != MANIFEST_SCHEMA:
        return 'schema_version 不是 1.0'
    if not isinstance(record.get('created_at'), str) or not record['created_at'].strip():
        return 'created_at 缺失'
    for field in ('commit_sha', 'tree_sha'):
        if not GIT_SHA.fullmatch(str(record.get(field) or '')):
            return f'{field} 必须是完整的 40 位小写 SHA'
    repository = record.get('repository')
    if (not isinstance(repository, dict)
            or not isinstance(repository.get('id'), str)
            or not repository['id'].strip()):
        return 'repository 缺失或格式错误'
    if not isinstance(record.get('statement', ''), str):
        return 'statement 必须是字符串'
    generator = record.get('generator')
    if not isinstance(generator, dict):
        return 'generator 缺失'
    for field in ('tool', 'version', 'python', 'platform'):
        if not isinstance(generator.get(field), str) or not generator[field].strip():
            return f'generator.{field} 缺失'
    if not isinstance(generator.get('command', ''), str):
        return 'generator.command 必须是字符串'
    files = record.get('files')
    if not isinstance(files, list) or not files:
        return 'files 不能为空'
    paths = []
    for item in files:
        if not isinstance(item, dict):
            return 'files 的每一项必须是对象'
        try:
            paths.append(_record_path(item.get('path')))
        except PMError as exc:
            return str(exc)
        if not SHA256.fullmatch(str(item.get('sha256') or '')):
            return f'files.sha256 必须是 64 位小写 SHA-256：{item.get("path")}'
        size = item.get('bytes')
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            return f'files.bytes 必须是非负整数：{item.get("path")}'
    if len(paths) != len(set(paths)):
        return 'files 路径重复'
    if paths != sorted(paths):
        return 'files 必须按 path 升序存放'
    if record.get('manifest_id') != _manifest_id(record):
        return 'manifest_id 不可重算（记录被修改或格式错误）'
    return None


# ---------------------------------------------------------------- public API

def evidence_request(repo: Path, commit_sha: str, paths, statement: str = '',
                     output: Path | None = None) -> dict:
    """Write an unsigned manifest request; an out-of-repo key signs it later."""
    if not isinstance(statement, str) or '\n' in statement or '\r' in statement:
        raise PMError('statement 必须是单行字符串')
    commit_sha = str(commit_sha or '').strip()
    if not GIT_SHA.fullmatch(commit_sha):
        raise PMError('commit 必须是完整的 40 位小写 SHA')
    commit, tree = resolve_commit(repo, commit_sha)
    files = collect_files(repo, paths)
    record = {
        'schema_version': MANIFEST_SCHEMA, 'kind': MANIFEST_KIND,
        'created_at': utc_now(), 'commit_sha': commit, 'tree_sha': tree,
        'repository': _approval_repository(repo), 'statement': statement.strip(),
        'generator': {
            'tool': 'project-memory', 'version': __version__,
            'python': _platform.python_version(),
            'platform': _platform.platform(),
            'command': f'project-memory evidence request --commit {commit}',
        },
        'files': files,
    }
    record['manifest_id'] = _manifest_id(record)
    payload = authority.signed_record_payload(record)
    if output is None:
        raise PMError('必须提供 --output')
    output = Path(output)
    shown = str(output.resolve())
    result = {'schema_version': MANIFEST_SCHEMA,
              'kind': 'evidence_manifest_request_result',
              'path': shown, 'manifest_id': record['manifest_id'],
              'manifest': record, 'payload_sha256': hashlib.sha256(payload).hexdigest(),
              'sign_command': (f'openssl dgst -sha256 -sign <审批私钥> -out <签名文件> '
                               f'{shown}'),
              'requires': ('由仓库外审批私钥对请求文件的规范 JSON 字节签名，再运行 '
                           'evidence attach；Agent 不持有私钥，也不能自行签名')}
    if output.is_file():
        if output.read_bytes() != payload:
            raise PMError(f'请求文件已存在且内容不同，拒绝覆盖：{shown}')
        return result
    if not write_new(output, payload.decode('utf-8')):
        if not output.is_file() or output.read_bytes() != payload:
            raise PMError(f'请求文件已存在且内容不同，拒绝覆盖：{shown}')
    return result


def evidence_attach(repo: Path, request_path, signature_path, anchor_path,
                    output: Path | None = None) -> dict:
    """Attach an externally produced signature after local format checks only."""
    request = _load(Path(request_path))
    problem = _structure_problem(request)
    if problem:
        raise PMError(f'证据清单请求不合规：{problem}')
    if not _approval_repository_matches(request, repo):
        raise PMError('证据清单的仓库身份与当前仓库不一致')
    signature_file = Path(signature_path)
    if not signature_file.is_file():
        raise PMError(f'签名文件不存在：{signature_file}')
    signature = signature_file.read_bytes()
    if not signature:
        raise PMError('签名为空')
    anchor, anchor_reason = authority.load_anchor_document(anchor_path)
    if anchor is None:
        raise PMError(f'无法校验证据清单签名：{anchor_reason}')
    payload = authority.signed_record_payload(request)
    signature_b64 = base64.b64encode(signature).decode('ascii')
    ok, detail = authority.verify_detached_signature(
        anchor, payload, signature_b64, anchor['algorithm'])
    if not ok:
        raise PMError(f'证据清单签名无效：{detail}')
    record = {**request, 'authority': {
        'status': 'signed', 'anchor_id': anchor['anchor_id'],
        'issuer': anchor['issuer'], 'algorithm': anchor['algorithm'],
        'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
        'signature_b64': signature_b64}}
    if output is None:
        raise PMError('必须提供 --output')
    path = Path(output)
    shown = str(path.resolve())
    if path.is_file():
        existing = _load(path)
        if _signed_same(existing, record):
            _require_existing_signature(existing, anchor)
            return {'schema_version': MANIFEST_SCHEMA,
                    'kind': 'evidence_manifest_attach_result', 'path': shown,
                    'manifest_id': existing.get('manifest_id'),
                    'manifest': existing, 'created': False, 'signature_valid': True,
                    'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer'],
                    'note': '已存在同名且内容相同的证据清单；未覆盖'}
        raise PMError(f'证据清单 {request["manifest_id"]} 已存在且内容不同，拒绝覆盖')
    if not write_new(path, json_text(record)):
        existing = _load(path)
        if not _signed_same(existing, record):
            raise PMError(f'证据清单 {request["manifest_id"]} 已存在且内容不同，拒绝覆盖')
        _require_existing_signature(existing, anchor)
        return {'schema_version': MANIFEST_SCHEMA,
                'kind': 'evidence_manifest_attach_result', 'path': shown,
                'manifest_id': existing.get('manifest_id'), 'manifest': existing,
                'created': False, 'signature_valid': True,
                'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer'],
                'note': '并发写入命中同名清单；未覆盖'}
    return {'schema_version': MANIFEST_SCHEMA,
            'kind': 'evidence_manifest_attach_result', 'path': shown,
            'manifest_id': record.get('manifest_id'), 'manifest': record,
            'created': True, 'signature_valid': True,
            'anchor_id': anchor['anchor_id'], 'issuer': anchor['issuer'],
            'note': ('附加时只对给定公钥校验格式与签名；信任决定在 verify 时由 '
                     'PROJECT_MEMORY_APPROVAL_ANCHOR 重新做出')}


def evidence_verify(repo: Path, manifest_path, commit_sha: str) -> dict:
    """Check a signed manifest against the protected approval anchor and disk."""
    commit_sha = str(commit_sha or '').strip()
    try:
        record = _load(Path(manifest_path))
    except PMError as exc:
        return _result(None, commit_sha, None, False, False, 'invalid', str(exc),
                       [str(exc)])
    problems = []
    problem = _structure_problem(record)
    if problem:
        problems.append(problem)
    if GIT_SHA.fullmatch(commit_sha):
        try:
            commit, tree = resolve_commit(repo, commit_sha)
        except PMError as exc:
            commit, tree = None, None
            problems.append(str(exc))
    else:
        commit, tree = None, None
        problems.append('--commit 必须是完整的 40 位小写 SHA')
    if not _approval_repository_matches(record, repo):
        problems.append('证据清单的仓库身份与当前仓库不一致')
    if commit is not None:
        if record.get('commit_sha') != commit:
            problems.append(f'清单绑定提交 {record.get("commit_sha")}，不是 {commit}')
        if record.get('tree_sha') != tree:
            problems.append(f'清单树 {record.get("tree_sha")} 不是提交 {commit} 的树 {tree}')
    verdict = authority.evidence_authority(repo, record)
    if not verdict.get('trusted'):
        problems.append(f'证据清单未通过验签（{verdict.get("status")}）：'
                        f'{verdict.get("reason")}')
    if not problems:
        problems.extend(_file_problems(repo, record.get('files') or []))
    return _result(record.get('manifest_id'), record.get('commit_sha'),
                   record.get('tree_sha'), isinstance(record.get('authority'), dict),
                   bool(verdict.get('trusted')), verdict.get('status'),
                   verdict.get('reason'), problems,
                   authoring=verdict)


def _file_problems(repo: Path, files) -> list[str]:
    problems = []
    for item in files:
        rel = item.get('path')
        try:
            path = _safe_file(repo, _record_path(rel))
            data = path.read_bytes()
        except PMError as exc:
            problems.append(str(exc))
            continue
        except OSError as exc:
            problems.append(f'无法读取证据文件：{rel}（{exc}）')
            continue
        if hashlib.sha256(data).hexdigest() != item.get('sha256'):
            problems.append(f'文件内容已变化（sha256 不符）：{rel}')
        elif len(data) != item.get('bytes'):
            problems.append(f'文件大小已变化：{rel}')
    return problems


def _result(manifest_id, commit_sha, tree_sha, signed, trusted, status, reason,
            problems, authoring=None) -> dict:
    return {'schema_version': MANIFEST_SCHEMA,
            'kind': 'evidence_manifest_verify_result',
            'manifest_id': manifest_id, 'commit_sha': commit_sha,
            'tree_sha': tree_sha, 'signed': signed, 'trusted': trusted,
            'authority_status': status, 'reason': reason,
            'verified': not problems, 'problems': problems,
            'anchor_id': (authoring or {}).get('anchor_id'),
            'issuer': (authoring or {}).get('issuer')}


def _signed_same(existing: dict, record: dict) -> bool:
    """Same payload and anchor identity; signature bytes may differ (ECDSA)."""
    if not isinstance(existing, dict):
        return False
    if _manifest_core(existing) != _manifest_core(record):
        return False
    left = existing.get('authority')
    left = left if isinstance(left, dict) else {}
    right = record.get('authority')
    right = right if isinstance(right, dict) else {}
    return all(left.get(key) == right.get(key)
               for key in ('anchor_id', 'issuer', 'algorithm'))


def _require_existing_signature(existing: dict, anchor: dict) -> None:
    """Re-check the stored signature before reporting an existing file as idempotent."""
    authoring = existing.get('authority')
    signature_b64 = authoring.get('signature_b64') if isinstance(authoring, dict) else None
    ok, detail = authority.verify_detached_signature(
        anchor, authority.signed_record_payload(existing), signature_b64,
        anchor['algorithm'])
    if not ok:
        raise PMError(f'已有证据清单签名无效，拒绝视为幂等：{detail}')


def _load(path: Path) -> dict:
    value = safe_json(path)
    if not isinstance(value, dict):
        raise PMError(f'证据清单必须是 JSON 对象：{path}')
    return value
