"""Immutable execution snapshots and tamper-evident execution receipts.

A receipt is produced only by this module: it exports the requested commit into
an immutable snapshot, executes the command there, and records the observed
exit code, log hash and snapshot digest. Verification code re-computes all of
those values and refuses agent-supplied "passed" logs that have no matching
receipt.

Two execution modes exist, and neither is silently substituted for the other:

``local``
    A plain child process.  It inherits the host (after removing credential-like
    variables) and provides **no OS isolation**.  Receipts are labelled
    ``local_untrusted``.
``trusted``
    Delegates to :mod:`project_memory.trusted_exec`, which runs the command in a
    WSL2 user/mount/PID/network namespace with host filesystems masked and an
    environment allowlist.  If the sandbox preflight fails, ``PMError`` is
    raised; there is no fallback to ``local``.

Honest boundary: a receipt proves that *something* with this content hash is
present in the working copy.  Because an agent that can write the working copy
can also write receipts and attestations, content integrity is **not** the same
as provenance or authority.  Only the fail-closed signature check in
:mod:`project_memory.authority` can authorize a verification record, and this
build deliberately configures no signer.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from . import trusted_exec
from .common import PMError, validate_identifier

RECEIPT_SCHEMA = '1.0'
RECEIPT_KIND = 'execution_receipt'
META_ROOT = '.project-memory'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _meta(repo: Path, name: str) -> Path:
    return repo / META_ROOT / name


def repo_id(repo: Path) -> str:
    return _sha256_bytes(str(repo.resolve()).casefold().encode('utf-8'))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(repo), *args],
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise PMError(f'git {" ".join(args)} 失败：{result.stderr.strip()}')
    return result.stdout.strip()


def resolve_commit(repo: Path, sha: str | None = None) -> tuple[str, str]:
    """Return (commit_sha, tree_sha) and reject unknown or abbreviated input."""
    value = (sha or 'HEAD').strip()
    if value != 'HEAD' and not (len(value) == 40 and all(c in '0123456789abcdef' for c in value)):
        raise PMError('提交必须是完整的 40 位小写 SHA 或 HEAD')
    try:
        commit = _git(repo, 'rev-parse', '--verify', f'{value}^{{commit}}')
        tree = _git(repo, 'rev-parse', '--verify', f'{commit}^{{tree}}')
    except PMError:
        raise PMError(f'提交不存在：{value}')
    return commit, tree


def _sanitize_rel(value: str) -> str:
    return value.replace('\\', '/').lstrip('./')


def _tree_digest(root: Path) -> tuple[str, dict[str, str]]:
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise PMError(f'快照目录包含符号链接，拒绝计算摘要：{path}')
        if not path.is_file():
            continue
        rel = _sanitize_rel(path.relative_to(root).as_posix())
        files[rel] = _sha256_file(path)
    payload = '\n'.join(f'{rel}\x1f{digest}' for rel, digest in files.items())
    return _sha256_bytes(payload.encode('utf-8')), files


def _validate_archive(handle: tarfile.TarFile) -> None:
    """Reject archive members that can escape or redirect the snapshot tree.

    ``filter='data'`` already blocks most of these, but the contract must be a
    stable ``PMError`` rather than a version-specific ``tarfile`` exception.
    """
    for member in handle.getmembers():
        name = member.name.replace('\\', '/')
        if member.issym() or member.islnk():
            raise PMError(f'快照归档包含链接成员（{name}）；符号链接/硬链接不能进入可信快照')
        if member.ischr() or member.isblk() or member.isfifo():
            raise PMError(f'快照归档包含设备或管道成员（{name}）；不能进入可信快照')
        parts = Path(name).parts
        if name.startswith('/') or '..' in parts or Path(name).drive:
            raise PMError(f'快照归档成员路径非法（{name}）')


def create_snapshot(repo: Path, commit_sha: str) -> dict:
    """Export a commit into .project-memory/snapshots/<id>/tree (immutable copy)."""
    commit, tree = resolve_commit(repo, commit_sha)
    snapshot_id = 'SNP-' + _sha256_bytes(f'{commit}\x1f{tree}'.encode('utf-8'))[:16]
    base = _meta(repo, 'snapshots') / snapshot_id
    tree_dir = base / 'tree'
    manifest_path = base / 'manifest.json'
    if (base.parent.is_symlink() or base.is_symlink() or tree_dir.is_symlink()
            or manifest_path.is_symlink()):
        raise PMError(f'快照目录或清单是符号链接，拒绝使用：{snapshot_id}')
    if tree_dir.is_dir() and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        try:
            digest, _ = _tree_digest(tree_dir)
        except PMError:
            digest = None
        if digest == manifest.get('snapshot_sha256') and manifest.get('commit_sha') == commit:
            return manifest
        raise PMError(f'快照内容与清单不一致，拒绝复用：{snapshot_id}')
    base.mkdir(parents=True, exist_ok=True)
    archive = base / 'commit.tar'
    _git(repo, 'archive', f'--format=tar', f'--output={archive.as_posix()}', commit)
    staging = Path(tempfile.mkdtemp(prefix=f'{snapshot_id}-', dir=str(base)))
    try:
        try:
            with tarfile.open(archive, 'r') as handle:
                _validate_archive(handle)
                try:
                    handle.extractall(staging, filter='data')
                except TypeError:  # Python < 3.12 without extraction filters
                    handle.extractall(staging)
        except PMError:
            raise
        except (tarfile.TarError, OSError) as exc:
            raise PMError(f'快照解包失败：{exc}')
        try:
            digest, files = _tree_digest(staging)
        except PMError:
            raise
        except OSError as exc:
            raise PMError(f'快照摘要计算失败：{exc}')
        if tree_dir.exists():
            import shutil
            shutil.rmtree(tree_dir)
        staging.rename(tree_dir)
    finally:
        if staging.exists():
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)
    manifest = {
        'schema_version': RECEIPT_SCHEMA, 'kind': 'execution_snapshot',
        'snapshot_id': snapshot_id, 'commit_sha': commit, 'tree_sha': tree,
        'snapshot_sha256': digest, 'file_count': len(files),
        'files': files, 'created_at': _now(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def _canonical_receipt_digest(receipt: dict) -> str:
    payload = {key: value for key, value in receipt.items() if key != 'content_sha256'}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return _sha256_bytes(encoded.encode('utf-8'))


def _receipt_path(repo: Path, receipt_id: str) -> Path:
    validate_identifier(receipt_id, 'receipt id')
    return _meta(repo, 'receipts') / f'{receipt_id}.json'


def find_receipt(repo: Path, ref: str) -> Path:
    value = str(ref or '').strip()
    if not value:
        raise PMError('缺少执行收据')
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo / candidate
    if candidate.is_symlink():
        raise PMError(f'执行收据不能是符号链接：{value}')
    try:
        candidate = candidate.resolve()
        candidate.relative_to((repo / META_ROOT).resolve())
    except (ValueError, OSError):
        raise PMError(f'执行收据必须位于仓库 .project-memory 内：{value}')
    if not candidate.is_file():
        raise PMError(f'执行收据不存在：{value}')
    return candidate


def load_receipt(repo: Path, ref: str) -> tuple[dict, Path]:
    path = find_receipt(repo, ref)
    try:
        receipt = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise PMError(f'执行收据不是合法 JSON：{exc}')
    if not isinstance(receipt, dict):
        raise PMError('执行收据必须是 JSON 对象')
    return receipt, path


def _provenance(repo: Path, receipt: dict, problems: list[str]) -> dict:
    """Separate content integrity from provenance and trust.

    Nothing in this build can authenticate a receipt against an agent that can
    write the repository, so ``trusted`` is always false.  The label still
    records whether a trusted-mode attestation is present and self-consistent.
    """
    isolation = receipt.get('isolation') if isinstance(receipt.get('isolation'), dict) else {}
    declared = receipt.get('execution_provenance')
    kind = declared.get('kind') if isinstance(declared, dict) else 'unlabelled'
    if kind != 'trusted_launcher':
        return {'kind': 'local_untrusted', 'trusted': False,
                'reason': '本地启动器；没有操作系统隔离，也没有外部签名来源'}
    if isolation.get('mode') != trusted_exec.MODE:
        problems.append('声明可信执行但 isolation.mode 不匹配')
    attestation_path = str(receipt.get('attestation_path') or '')
    if not attestation_path:
        problems.append('声明可信执行但缺少 attestation_path')
        return {'kind': 'trusted_launcher', 'trusted': False,
                'reason': '缺少 attestation，无法确认隔离事实'}
    candidate = Path(attestation_path)
    if not candidate.is_absolute():
        candidate = repo / candidate
    if candidate.is_symlink():
        problems.append('attestation 不能是符号链接')
        return {'kind': 'trusted_launcher', 'trusted': False,
                'reason': 'attestation 是符号链接'}
    try:
        resolved = candidate.resolve()
        resolved.relative_to((repo / META_ROOT).resolve())
    except (ValueError, OSError):
        problems.append('attestation 不在 .project-memory 内')
        return {'kind': 'trusted_launcher', 'trusted': False,
                'reason': 'attestation 路径逃逸'}
    if not resolved.is_file():
        problems.append('attestation 文件不存在')
        return {'kind': 'trusted_launcher', 'trusted': False,
                'reason': 'attestation 文件不存在'}
    if receipt.get('attestation_sha256') and _sha256_file(resolved) != receipt['attestation_sha256']:
        problems.append('attestation 内容哈希与收据不一致')
    try:
        attestation = json.loads(resolved.read_text(encoding='utf-8'))
    except Exception as exc:
        problems.append(f'attestation 不是合法 JSON：{exc}')
        return {'kind': 'trusted_launcher', 'trusted': False,
                'reason': 'attestation 无法解析'}
    expected = {
        'ok': True,
        'mode': trusted_exec.MODE,
        'receipt_id': receipt.get('receipt_id'),
        'snapshot': isolation.get('snapshot_wsl'),
    }
    for key, want in expected.items():
        if want and attestation.get(key) != want:
            problems.append(f'attestation.{key} 与收据不一致')
    command_sha = _sha256_bytes(str(receipt.get('command') or '').encode('utf-8'))
    if attestation.get('command_sha256') != command_sha:
        problems.append('attestation.command_sha256 与收据命令不一致')
    return {'kind': 'trusted_launcher_attested', 'trusted': False,
            'reason': ('attestation 由启动器写出，但位于仓库内且没有外部签名；'
                       '只能证明“曾这样声明”，不能证明来源')}


def verify_receipt(repo: Path, ref: str, expected: dict | None = None) -> dict:
    """Recompute snapshot/log/digest facts. Structural failures are problems, not raises.

    ``valid`` means the receipt is internally consistent with the snapshot, log
    and commit.  It does **not** mean the receipt is authentic or authoritative;
    see the returned ``provenance`` block.
    """
    repo = Path(repo).resolve()
    problems: list[str] = []
    try:
        receipt, path = load_receipt(repo, ref)
    except PMError as exc:
        return {'valid': False, 'problems': [str(exc)], 'receipt': None, 'path': None,
                'provenance': {'kind': 'invalid', 'trusted': False, 'reason': str(exc)}}
    if receipt.get('kind') != RECEIPT_KIND:
        problems.append('kind 不是 execution_receipt')
    if receipt.get('schema_version') != RECEIPT_SCHEMA:
        problems.append('schema_version 不匹配')
    if receipt.get('content_sha256') != _canonical_receipt_digest(receipt):
        problems.append('收据内容哈希不一致（收据被修改）')
    receipt_id = receipt.get('receipt_id')
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        problems.append('收据缺少 receipt_id')
    else:
        try:
            validate_identifier(receipt_id, 'receipt id')
        except PMError as exc:
            problems.append(str(exc))
        else:
            expected_path = _receipt_path(repo, receipt_id).resolve()
            if path.resolve() != expected_path:
                problems.append('收据文件路径与 receipt_id 不一致（复制、改名或替换的收据）')
            try:
                path.resolve().relative_to((_meta(repo, 'receipts')).resolve())
            except (ValueError, OSError):
                problems.append('收据不在 .project-memory/receipts 目录内')
    if receipt.get('repo_id') != repo_id(repo):
        problems.append('收据属于其他仓库')
    commit, tree = None, None
    try:
        commit, tree = resolve_commit(repo, str(receipt.get('commit_sha') or ''))
    except PMError as exc:
        problems.append(str(exc))
    if commit and receipt.get('tree_sha') != tree:
        problems.append('收据 tree_sha 与提交不一致')
    exit_code = receipt.get('exit_code')
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        problems.append('exit_code 必须是整数')
    snapshot_ok = False
    digest = None
    snapshot_id = receipt.get('snapshot_id') or ''
    tree_dir = _meta(repo, 'snapshots') / snapshot_id / 'tree'
    if tree_dir.is_symlink() or (tree_dir.parent.is_symlink()):
        problems.append('快照目录是符号链接')
    elif not snapshot_id or not tree_dir.is_dir():
        problems.append('找不到对应快照目录')
    else:
        try:
            digest, _ = _tree_digest(tree_dir)
        except (PMError, OSError) as exc:
            problems.append(f'快照内容无法校验：{exc}')
        else:
            snapshot_ok = digest == receipt.get('snapshot_sha256')
            if not snapshot_ok:
                problems.append('快照内容哈希与收据不一致')
    log_ok = False
    log_path = receipt.get('log_path') or ''
    if log_path:
        raw_log = Path(log_path)
        if not raw_log.is_absolute():
            raw_log = repo / raw_log
        if raw_log.is_symlink():
            problems.append('日志文件是符号链接')
            full = None
        else:
            full = raw_log.resolve()
        if full is not None:
            try:
                full.relative_to((repo / META_ROOT).resolve())
            except ValueError:
                problems.append('日志路径不在 .project-memory 内')
                full = None
        if full is not None and full.is_file():
            log_ok = _sha256_file(full) == receipt.get('log_sha256')
            if not log_ok:
                problems.append('日志内容哈希与收据不一致（日志被修改）')
        elif full is not None:
            problems.append('日志文件不存在')
    else:
        problems.append('收据缺少 log_path')
    if not receipt.get('command'):
        problems.append('收据缺少执行命令')
    if not receipt.get('executed_by'):
        problems.append('收据缺少执行者')
    provenance = _provenance(repo, receipt, problems)
    for key, want in (expected or {}).items():
        if want is None:
            continue
        if receipt.get(key) != want:
            problems.append(f'{key} 与预期不一致：收据 {receipt.get(key)!r} != 预期 {want!r}')
    return {'valid': not problems, 'problems': problems, 'receipt': receipt,
            'path': path.relative_to(repo).as_posix(), 'snapshot_ok': snapshot_ok,
            'log_ok': log_ok, 'snapshot_sha256': digest,
            'integrity_valid': not problems, 'provenance': provenance}


_SENSITIVE_ENV = ('TOKEN', 'SECRET', 'PASSWORD', 'PASSWD', 'API_KEY', 'APIKEY',
                  'CREDENTIAL', 'QODER', 'GITHUB', 'GH_', 'OPENAI', 'ANTHROPIC',
                  'DEEPSEEK', 'HF_', 'AWS_', 'AZURE', 'SSH_AUTH_SOCK', 'KRB5',
                  'PROJECT_MEMORY_TRUST_ANCHOR', 'PROJECT_MEMORY_OPENSSL')


def _sensitive_env_name(name: str) -> bool:
    upper = str(name).upper()
    return any(token in upper for token in _SENSITIVE_ENV)


def _local_env(tree_dir: Path, extra_env: dict | None) -> dict:
    """Host environment minus credential-like names; extra_env is validated."""
    env = {}
    for key, value in os.environ.items():
        if key in ('PYTHONPATH', 'PYTHONHOME') or _sensitive_env_name(key):
            continue
        env[key] = value
    env.update({'PYTHONPATH': str(tree_dir), 'PYTHONDONTWRITEBYTECODE': '1',
                'PROJECT_MEMORY_EXECUTION_MODE': 'local_untrusted'})
    if extra_env:
        for key, value in extra_env.items():
            name = str(key)
            if name in ('PYTHONPATH', 'PYTHONHOME') or _sensitive_env_name(name):
                raise PMError(f'本地执行不允许注入敏感或路径劫持变量：{name}')
            env[name] = str(value)
    return env


def run_command(repo: Path, command, commit_sha: str | None = None, *,
                executed_by: str = 'unknown-agent', timeout: int = 900,
                extra_env: dict | None = None, mode: str = 'local',
                wsl_distro: str | None = None, subject: str | None = None) -> dict:
    """Execute a command inside a fresh commit snapshot and persist a receipt.

    ``mode='trusted'`` requires a working WSL2 namespace sandbox and never falls
    back to a plain child process.  ``mode='local'`` stays available for normal
    development but its receipt is explicitly labelled untrusted.
    """
    executed_by = str(executed_by or '').strip() or 'unknown-agent'
    if mode not in ('local', 'trusted'):
        raise PMError("执行模式必须是 local 或 trusted")
    if isinstance(command, (list, tuple)):
        argv = [str(part) for part in command]
        if not argv:
            raise PMError('执行命令不能为空')
        shell = False
        command_text = shlex.join(argv) if mode == 'trusted' else ' '.join(argv)
    else:
        command_text = str(command or '').strip()
        if not command_text:
            raise PMError('执行命令不能为空')
        argv = command_text
        shell = True
    if not isinstance(timeout, int) or timeout <= 0:
        raise PMError('timeout 必须是正整数秒')
    if mode == 'trusted' and extra_env:
        raise PMError('可信执行不接受 extra_env：环境变量只能来自启动器 allowlist')
    if mode == 'trusted':
        # Check the launcher before writing anything: a blocked run must not
        # leave snapshots or logs behind that look like partial evidence.
        available, reason = trusted_exec.wsl_available(wsl_distro)
        if not available:
            raise PMError(f'可信执行不可用（fail-closed，不回退普通子进程）：{reason}')
    commit, tree = resolve_commit(repo, commit_sha)
    snapshot = create_snapshot(repo, commit)
    tree_dir = _meta(repo, 'snapshots') / snapshot['snapshot_id'] / 'tree'
    receipt_id = 'EXE-' + _sha256_bytes(
        f'{commit}\x1f{tree}\x1f{command_text}\x1f{time.time_ns()}\x1f{secrets.token_hex(8)}'
        .encode('utf-8'))[:20]
    log_dir = _meta(repo, 'logs')
    receipt_dir = _meta(repo, 'receipts')
    log_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    started = _now()
    attestation = None
    attestation_path = None
    if mode == 'trusted':
        trusted = trusted_exec.run_trusted(
            repo, tree_dir, receipt_id, command_text, timeout=timeout,
            distro=wsl_distro, extra_env=extra_env)
        stdout, stderr, exit_code = trusted['stdout'], trusted['stderr'], trusted['exit_code']
        attestation = trusted['attestation']
        attestation_path = trusted['attestation_path']
    else:
        env = _local_env(tree_dir, extra_env)
        try:
            result = subprocess.run(argv, cwd=str(tree_dir), env=env, shell=shell,
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=timeout)
            stdout, stderr, exit_code = result.stdout or '', result.stderr or '', result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or '') if isinstance(exc.stdout, str) else ''
            stderr = (exc.stderr or '') if isinstance(exc.stderr, str) else ''
            stderr += f'\n[timeout after {timeout}s]'
            exit_code = 124
    finished = _now()
    log_path = log_dir / f'{receipt_id}.log'
    cwd_label = f'{tree_dir} (local, no isolation)' if mode == 'local' else '/opt/root (wsl2 namespace)'
    body = (f'$ {command_text}\n[cwd={cwd_label}]\n'
            f'--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n'
            f'[exit_code={exit_code}]\n')
    log_path.write_text(body, encoding='utf-8')
    log_rel = log_path.relative_to(repo).as_posix()
    if mode == 'trusted':
        isolation = {
            'mode': trusted_exec.MODE, 'os_isolation': True,
            'sandbox': 'wsl2-user-mount-pid-net-namespace',
            'distro': attestation.get('distro') if attestation else wsl_distro,
            'snapshot_wsl': attestation.get('snapshot') if attestation else None,
        }
        provenance = {
            'kind': 'trusted_launcher', 'launcher': 'project_memory.trusted_exec',
            'attested': True, 'trusted': False,
            'reason': ('隔离由启动器 attestation 记录，但 attestation 位于仓库内，'
                       '没有外部签名来源；不能证明收据未被同权限 Agent 改写'),
        }
        trust_label = 'isolated_local_attestation'
    else:
        isolation = {'mode': 'none', 'os_isolation': False,
                     'sandbox': 'plain-child-process', 'workspace': 'immutable-snapshot'}
        provenance = {
            'kind': 'local_untrusted', 'launcher': 'project_memory.execution',
            'attested': False, 'trusted': False,
            'reason': '普通子进程；宿主文件系统与网络可见，收据只能证明内容未被后续修改',
        }
        trust_label = 'local_untrusted'
    receipt = {
        'schema_version': RECEIPT_SCHEMA, 'kind': RECEIPT_KIND,
        'receipt_id': receipt_id, 'repo_id': repo_id(repo),
        'commit_sha': commit, 'tree_sha': tree,
        'snapshot_id': snapshot['snapshot_id'],
        'snapshot_sha256': snapshot['snapshot_sha256'],
        'command': command_text, 'exit_code': exit_code,
        'log_path': log_rel, 'log_sha256': _sha256_file(log_path),
        'log_bytes': log_path.stat().st_size,
        'started_at': started, 'finished_at': finished,
        'executed_by': executed_by, 'subject': str(subject or ''),
        'executor': {'name': 'project-memory', 'mode': mode,
                     'python': platform.python_version(), 'platform': platform.platform()},
        'isolation': isolation,
        'execution_provenance': provenance,
        'trust': trust_label,
        'caveat': ('收据只证明该命令在这个快照内以该退出码执行过；'
                   '不证明测试语义覆盖了任何业务标准，也不证明来源可信。'),
    }
    if mode == 'trusted':
        receipt['attestation_path'] = attestation_path
        if attestation_path:
            receipt['attestation_sha256'] = _sha256_file(repo / attestation_path)
    receipt['content_sha256'] = _canonical_receipt_digest(receipt)
    path = _receipt_path(repo, receipt_id)
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
    return {'receipt': receipt, 'path': path.relative_to(repo).as_posix(),
            'log': log_rel, 'snapshot': snapshot,
            'mode': mode, 'isolation': isolation,
            'attestation': attestation}
