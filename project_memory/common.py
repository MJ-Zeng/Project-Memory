"""Safe local I/O and deliberately small YAML-frontmatter subset."""
from __future__ import annotations
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:  # POSIX advisory locks; Windows uses msvcrt.locking below.
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

class PMError(Exception):
    pass


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def require_repo(root: Path) -> Path:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise PMError(f'仓库目录不存在：{root}')
    return root


def git_sha_optional(repo: Path) -> str | None:
    """Return HEAD for a working Git repo, or None for a plain workspace."""
    p = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def git_sha(repo: Path) -> str:
    sha = git_sha_optional(repo)
    if not sha:
        raise PMError('当前目录不是带 HEAD 提交的 Git 仓库；请指定有效的已提交仓库')
    return sha


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_utf8_stdio() -> None:
    """Windows consoles default to GBK; JSON reports contain Chinese text."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except (OSError, ValueError):
                pass


def safe_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise PMError(f'无法读取 JSON {path}：{e}') from e


def json_text(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def write_new(path: Path, content: str) -> bool:
    """Atomic no-clobber; hardlink makes concurrent creators fail safely."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.pm-tmp-', delete=False) as f:
            temp_name = f.name
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temp_name, path)
            return True
        except FileExistsError:
            return False
        except OSError:
            # Filesystems without hardlink support still need no-clobber semantics.
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.pm-tmp-', delete=False) as f:
            name = f.name
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.02
_lock_holds = threading.local()


def _lock_path_for(path: Path) -> Path:
    """Sidecar lock named from the record path, never from its inode.

    ``os.replace`` gives a record a new inode, so a lock attached to the file
    object would not serialise anything.  The name is a hash of the normalized
    real path, and lock files are never deleted (removing one re-opens the race).
    """
    key = hashlib.sha256(os.path.normcase(os.path.realpath(path)).encode('utf-8')).hexdigest()[:16]
    for parent in Path(os.path.abspath(path)).parents:
        if parent.name == '.project-memory':
            return parent / 'cache' / 'locks' / f'{key}.lock'
    return Path(os.path.abspath(path)).parent / f'.pm-lock-{key}.lock'


def _try_lock(fd: int) -> bool:
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        else:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        # Closing the descriptor releases the lock either way.
        pass


@contextlib.contextmanager
def record_lock(path: Path, timeout: float = LOCK_TIMEOUT_SECONDS, label: str = '记录'):
    """Exclusive cross-process lock around one record's read-modify-write.

    Re-entrant per thread, so a nested call on the same record (for example an
    audit migration inside an append) cannot deadlock itself.  Advisory only:
    a same-user process that ignores this lock is not stopped by it.
    """
    key = os.path.normcase(os.path.realpath(_lock_path_for(path)))
    held = getattr(_lock_holds, 'keys', None)
    if held is None:
        held = _lock_holds.keys = {}
    if key in held:
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
            if not held[key]:
                del held[key]
        return
    lock_file = _lock_path_for(path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise PMError(f'等待{label}锁超时（{timeout:.1f} 秒），可能有其他进程仍在写入：{lock_file}')
            time.sleep(_LOCK_POLL_SECONDS)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b'\n')  # Windows byte-range locks need a lockable byte.
        held[key] = 1
        try:
            yield
        finally:
            held[key] -= 1
            if not held[key]:
                del held[key]
    finally:
        _unlock(fd)
        os.close(fd)


def frontmatter(markdown: str) -> tuple[dict, str]:
    """Parse a documented YAML subset; unknown constructs fail closed.

    Supports scalar strings, JSON-like scalar arrays, true/false, and integers.
    Does not support nested YAML, multiline strings, anchors, or aliases.
    """
    if not markdown.startswith('---\n'):
        return {}, markdown
    end = markdown.find('\n---\n', 4)
    if end < 0:
        raise PMError('frontmatter 以 --- 开始，但没有结束的 ---')
    result = {}
    for line in markdown[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.match(r'^([a-zA-Z_][\w-]*):(?:\s*(.*))?$', line)
        if not match:
            raise PMError(f'不支持的 YAML frontmatter 行：{line!r}')
        key, raw = match.group(1), (match.group(2) or '').strip()
        if key in result:
            raise PMError(f'frontmatter 键重复：{key}')
        if raw.startswith('[') or raw.startswith('"'):
            try:
                result[key] = json.loads(raw)
            except ValueError:
                raise PMError(f'请使用与 JSON 兼容的行内数组或字符串：{key}') from None
        elif raw in ('true', 'false'):
            result[key] = raw == 'true'
        elif re.fullmatch(r'\d+', raw):
            result[key] = int(raw)
        else:
            result[key] = raw
    return result, markdown[end+5:]


def md_header(metadata: dict) -> str:
    lines = ['---']
    for key, value in metadata.items():
        if isinstance(value, (list, dict)) or not isinstance(value, str):
            encoded = json.dumps(value, ensure_ascii=False)
        else:
            encoded = json.dumps(value, ensure_ascii=False)
        lines.append(f'{key}: {encoded}')
    lines.append('---')
    return '\n'.join(lines) + '\n\n'


def relpath(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        raise PMError(f'路径位于仓库之外：{path}') from None


def validate_identifier(value: str, label: str = 'id') -> str:
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}', value):
        raise PMError(f'{label} 不合法：{value!r}')
    return value


def path_component(value) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value).strip())
    if text in ('', '.', '..'):
        text = '_'
    return text[:120]
