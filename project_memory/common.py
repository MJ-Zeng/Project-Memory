"""Safe local I/O and deliberately small YAML-frontmatter subset."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

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
    real_root = Path(os.path.realpath(root))
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
            target = Path(os.path.realpath(current))
            try:
                target.relative_to(real_root)
            except ValueError:
                raise PMError(f'{label} 经过{kind}指向仓库之外：{current}') from None
    resolved = Path(os.path.realpath(candidate))
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
