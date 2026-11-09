"""Safe local I/O and deliberately small YAML-frontmatter subset."""
from __future__ import annotations
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import stat
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


REPLACE_DEADLINE_SECONDS = 2.0
_REPLACE_POLL_SECONDS = 0.02


def _replace_with_retry(source: str, target: Path) -> None:
    """``os.replace`` that survives a Windows sharing violation, bounded.

    On Windows a rename onto a file another process still has open is refused
    with ``PermissionError`` (WinError 5): the reader does not have to be a
    Project Memory writer, any process holding the record open — a peer reading
    it outside the lock, an indexer, an editor — is enough.  POSIX rename ignores
    readers, so this loop only ever costs a Windows call.  The retry is bounded
    and the last error propagates; a record is never reported as written when the
    replace actually failed.
    """
    deadline = time.monotonic() + REPLACE_DEADLINE_SECONDS
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_POLL_SECONDS)


def atomic_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.pm-tmp-', delete=False) as f:
            name = f.name
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.02
_lock_holds = threading.local()
_lock_fds: dict[str, int] = {}


def _after_fork_child() -> None:
    """Drop what ``fork`` copied but the child never acquired.

    Inherited re-entrancy counts let the child walk into the parent's critical
    section (measured on Linux: the probe reported ``acquired=True`` instead of
    timing out).  An inherited descriptor keeps a POSIX ``flock`` alive after the
    parent dies without unlocking, because the lock lives on the open file
    description and only dies once every descriptor referring to it is closed.
    Closing our copy here does not unlock the parent.
    """
    for fd in _lock_fds.values():
        try:
            os.close(fd)
        except OSError:
            pass
    _lock_fds.clear()
    keys = getattr(_lock_holds, 'keys', None)
    if keys is not None:
        keys.clear()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork_child)

_EXTENDED_PREFIX = '\\\\?\\'
_EXTENDED_UNC_PREFIX = '\\\\?\\UNC\\'


def canonical_realpath(path) -> str:
    """``os.path.realpath`` with the Windows device-namespace prefix removed.

    Windows hands back the same object under two spellings: normally
    ``C:\\dir\\file``, but while a peer is replacing that file — or has just
    created it — the resolver sometimes answers ``\\\\?\\C:\\dir\\file``.
    Measured here: 1 of 40 134 resolutions of a record under continuous
    replacement came back prefixed, and it produced a different lock key.
    Both the sidecar name and the boundary check are derived from realpath, so
    without this normalization one process can take a lock nobody else takes
    (mutual exclusion silently lost) or a legal in-repository path gets refused.
    A prefix that does not name a drive or UNC share — a volume GUID path or a
    ``GLOBALROOT`` device path — is left as it is, so it still fails closed.  The
    UNC form is rewritten to the native ``\\\\server\\\\share`` spelling, because
    ``os.path.normcase()`` does not unify separators and a ``//server/share``
    answer would hash to a different lock key than the ``\\\\server\\\\share`` a
    resolver normally returns.
    """
    text = os.path.realpath(path)
    if text.startswith(_EXTENDED_UNC_PREFIX):
        return '\\\\' + text[len(_EXTENDED_UNC_PREFIX):]
    if (text.startswith(_EXTENDED_PREFIX) and len(text) > 5
            and text[4].isascii() and text[4].isalpha() and text[5] == ':'):
        return text[len(_EXTENDED_PREFIX):]
    return text


def _lock_path_for(path: Path) -> tuple[Path, Path]:
    """Sidecar lock named from the record path, never from its inode.

    ``os.replace`` gives a record a new inode, so a lock attached to the file
    object would not serialise anything.  The name is a hash of the normalized
    real path, and lock files are never deleted (removing one re-opens the race).

    Returns the lock file together with the repository root that owns it, so the
    caller can check the boundary *before* ``mkdir`` creates anything: a linked
    ``.project-memory/cache`` would otherwise take the lock outside the repository.
    """
    key = hashlib.sha256(os.path.normcase(canonical_realpath(path)).encode('utf-8')).hexdigest()[:16]
    for parent in Path(os.path.abspath(path)).parents:
        if parent.name == '.project-memory':
            return parent / 'cache' / 'locks' / f'{key}.lock', parent.parent
    own_dir = Path(os.path.abspath(path)).parent
    return own_dir / f'.pm-lock-{key}.lock', own_dir


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

    This is a convention between cooperating processes of one user on one
    machine.  It is not a defence against a same-user process that deliberately
    ignores the lock, and it says nothing about two machines writing the same
    files.
    """
    lock_file, lock_root = _lock_path_for(path)
    # The sidecar is a write like any other: if .project-memory, cache or locks
    # is a directory link out of the repository, the mkdir and open below would
    # put lock files outside the repo.  Refuse before anything is created.
    ensure_inside_repo(lock_root, lock_file, '记录锁路径')
    key = os.path.normcase(canonical_realpath(lock_file))
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
        _lock_fds[key] = fd
        try:
            yield
        finally:
            held[key] -= 1
            if not held[key]:
                del held[key]
    finally:
        _lock_fds.pop(key, None)
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


_MOUNT_POINT_TAG = 0xA0000003


def link_kind(path: Path) -> str | None:
    """Name a link-like path component; junctions are reparse points, not symlinks."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return '符号链接'
    tag = getattr(info, 'st_reparse_tag', 0)
    if not tag:
        return None
    if tag == _MOUNT_POINT_TAG:
        return '目录联接或挂载点'
    return f'重解析点（tag 0x{tag:X}）'


def normalize_repo_relative(value, label: str) -> str:
    """Accept only a normalized repository-relative posix path; fail closed."""
    text = str(value if value is not None else '').strip().replace('\\', '/')
    if not text:
        raise PMError(f'{label} 不能为空')
    if text.startswith('/') or re.match(r'^[A-Za-z]:', text):
        raise PMError(f'{label} 必须是仓库内相对路径，不能是绝对路径或带盘符路径：{value!r}')
    parts = text.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise PMError(f'{label} 不能包含空段、. 或 ..：{value!r}')
    return text


def ensure_inside_repo(repo: Path, path: Path, label: str = '写入路径') -> Path:
    """Reject a target that leaves the repository *before* any write happens.

    Checks the lexical join and every existing parent component, so a linked
    directory inside the repo that points outside is refused.  A link that stays
    inside the repository is allowed: it does not cross the boundary.  This cannot
    remove a check/write race against a same-user process that swaps a component
    afterwards; it only closes the deterministic escape.
    """
    root = Path(os.path.abspath(repo))
    real_root = Path(canonical_realpath(root))
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        raise PMError(f'{label} 必须位于仓库之内：{path}') from None
    if not relative.parts:
        raise PMError(f'{label} 不能是仓库根目录本身')
    current = root
    for part in relative.parts:
        current = current / part
        kind = link_kind(current)
        if kind:
            target = Path(canonical_realpath(current))
            try:
                target.relative_to(real_root)
            except ValueError:
                raise PMError(f'{label} 经过{kind}指向仓库之外：{current}') from None
    resolved = Path(canonical_realpath(candidate))
    try:
        resolved.relative_to(real_root)
    except ValueError:
        raise PMError(f'{label} 解析后位于仓库之外：{path}') from None
    return candidate


def validate_identifier(value: str, label: str = 'id') -> str:
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}', value):
        raise PMError(f'{label} 不合法：{value!r}')
    return value


def path_component(value) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value).strip())
    if text in ('', '.', '..'):
        text = '_'
    return text[:120]
