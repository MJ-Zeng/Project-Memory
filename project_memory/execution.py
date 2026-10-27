"""Immutable execution snapshots and tamper-evident execution receipts.

A receipt is produced only by this module: it exports the requested commit into
an isolated snapshot, executes the command there, and records the observed exit
code, log hash and snapshot digest. Verification code re-computes all of those
values and refuses agent-supplied "passed" logs that have no matching receipt.

Honest limitation: a receipt is tamper-evident against later edits, not
tamper-proof against an agent that controls the whole working copy. It raises
the cost of forgery and makes silent edits detectable; it does not replace an
external CI or human approval source.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

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
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        rel = _sanitize_rel(path.relative_to(root).as_posix())
        files[rel] = _sha256_file(path)
    payload = '\n'.join(f'{rel}\x1f{digest}' for rel, digest in files.items())
    return _sha256_bytes(payload.encode('utf-8')), files


def create_snapshot(repo: Path, commit_sha: str) -> dict:
    """Export a commit into .project-memory/snapshots/<id>/tree (immutable copy)."""
    commit, tree = resolve_commit(repo, commit_sha)
    snapshot_id = 'SNP-' + _sha256_bytes(f'{commit}\x1f{tree}'.encode('utf-8'))[:16]
    base = _meta(repo, 'snapshots') / snapshot_id
    tree_dir = base / 'tree'
    manifest_path = base / 'manifest.json'
    if tree_dir.is_dir() and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        digest, _ = _tree_digest(tree_dir)
        if digest == manifest.get('snapshot_sha256') and manifest.get('commit_sha') == commit:
            return manifest
        raise PMError(f'快照内容与清单不一致，拒绝复用：{snapshot_id}')
    base.mkdir(parents=True, exist_ok=True)
    archive = base / 'commit.tar'
    _git(repo, 'archive', f'--format=tar', f'--output={archive.as_posix()}', commit)
    staging = Path(tempfile.mkdtemp(prefix=f'{snapshot_id}-', dir=str(base)))
    try:
        with tarfile.open(archive, 'r') as handle:
            try:
                handle.extractall(staging, filter='data')
            except TypeError:
                handle.extractall(staging)
        digest, files = _tree_digest(staging)
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


def verify_receipt(repo: Path, ref: str, expected: dict | None = None) -> dict:
    """Recompute snapshot/log/digest facts. Structural failures are problems, not raises."""
    problems: list[str] = []
    try:
        receipt, path = load_receipt(repo, ref)
    except PMError as exc:
        return {'valid': False, 'problems': [str(exc)], 'receipt': None, 'path': None}
    if receipt.get('kind') != RECEIPT_KIND:
        problems.append('kind 不是 execution_receipt')
    if receipt.get('schema_version') != RECEIPT_SCHEMA:
        problems.append('schema_version 不匹配')
    if receipt.get('content_sha256') != _canonical_receipt_digest(receipt):
        problems.append('收据内容哈希不一致（收据被修改）')
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
    if not snapshot_id or not tree_dir.is_dir():
        problems.append('找不到对应快照目录')
    else:
        digest, _ = _tree_digest(tree_dir)
        snapshot_ok = digest == receipt.get('snapshot_sha256')
        if not snapshot_ok:
            problems.append('快照内容哈希与收据不一致')
    log_ok = False
    log_path = receipt.get('log_path') or ''
    if log_path:
        full = (repo / log_path).resolve()
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
    for key, want in (expected or {}).items():
        if want is None:
            continue
        if receipt.get(key) != want:
            problems.append(f'{key} 与预期不一致：收据 {receipt.get(key)!r} != 预期 {want!r}')
    return {'valid': not problems, 'problems': problems, 'receipt': receipt,
            'path': path.relative_to(repo).as_posix(), 'snapshot_ok': snapshot_ok,
            'log_ok': log_ok, 'snapshot_sha256': digest}


def run_command(repo: Path, command, commit_sha: str | None = None, *,
                executed_by: str = 'unknown-agent', timeout: int = 900,
                extra_env: dict | None = None) -> dict:
    """Execute a command inside a fresh commit snapshot and persist a receipt."""
    executed_by = str(executed_by or '').strip() or 'unknown-agent'
    if isinstance(command, (list, tuple)):
        argv = [str(part) for part in command]
        if not argv:
            raise PMError('执行命令不能为空')
        shell = False
        command_text = ' '.join(argv)
    else:
        command_text = str(command or '').strip()
        if not command_text:
            raise PMError('执行命令不能为空')
        argv = command_text
        shell = True
    if not isinstance(timeout, int) or timeout <= 0:
        raise PMError('timeout 必须是正整数秒')
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
    env = {key: value for key, value in os.environ.items()
           if key not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update({'PYTHONPATH': str(tree_dir), 'PYTHONDONTWRITEBYTECODE': '1'})
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items()})
    started = _now()
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
    body = (f'$ {command_text}\n[cwd={tree_dir}]\n'
            f'--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n'
            f'[exit_code={exit_code}]\n')
    log_path.write_text(body, encoding='utf-8')
    log_rel = log_path.relative_to(repo).as_posix()
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
        'executed_by': executed_by,
        'executor': {'name': 'project-memory', 'mode': 'local_launcher',
                     'python': platform.python_version(), 'platform': platform.platform()},
        'trust': 'local_launcher',
        'caveat': ('收据只证明该命令在这个快照内以该退出码执行过；'
                   '不证明测试语义覆盖了任何业务标准。'),
    }
    receipt['content_sha256'] = _canonical_receipt_digest(receipt)
    path = _receipt_path(repo, receipt_id)
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
    return {'receipt': receipt, 'path': path.relative_to(repo).as_posix(),
            'log': log_rel, 'snapshot': snapshot}
