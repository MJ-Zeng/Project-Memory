"""WSL2 namespace launcher for trusted test execution (fail-closed).

Trusted execution is only provided by this launcher.  Windows/local execution
stays available but is labelled ``local_untrusted`` and never claims to be a
sandbox.

The launcher copies the immutable snapshot into a private tmpfs, masks Windows
drives and the user's host paths, creates user/mount/PID/network namespaces,
mounts a fresh /proc, runs the command with an explicit environment allowlist,
and only then writes an attestation file.  If any preflight check fails, no
receipt is produced and the caller receives PMError; there is no fallback to a
plain subprocess.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .common import PMError

WSL_EXE_ENV = 'PROJECT_MEMORY_WSL_EXE'
WSL_DISTRO_ENV = 'PROJECT_MEMORY_WSL_DISTRO'
DISABLE_ENV = 'PROJECT_MEMORY_DISABLE_WSL'
MODE = 'wsl2-user-mount-pid-net-namespace'
_DISTRO_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
_CACHE: dict[tuple, tuple[bool, str]] = {}


def _wsl_exe() -> str:
    return os.environ.get(WSL_EXE_ENV, '').strip() or 'wsl.exe'


def _distro(distro: str | None) -> str:
    value = (distro or os.environ.get(WSL_DISTRO_ENV, '') or '').strip()
    if value and not _DISTRO_RE.match(value):
        raise PMError(f'非法的 WSL 发行版名称：{value}')
    return value


def _wsl_args(distro: str | None) -> list[str]:
    args = [_wsl_exe()]
    if distro:
        args.extend(['-d', distro])
    return args


def clean_stderr(text: str) -> str:
    """Drop the WSL localhost/NAT banner; keep real command stderr."""
    kept = []
    for line in (text or '').splitlines():
        lowered = line.casefold()
        if lowered.startswith('wsl:') or ('localhost' in lowered and ('nat' in lowered or 'wsl' in lowered)):
            continue
        kept.append(line)
    return '\n'.join(kept)


def run_wsl(args: list[str], *, timeout: int = 60, input_text: str | None = None,
            distro: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([*_wsl_args(distro), *args], capture_output=True,
                              text=True, encoding='utf-8', errors='replace',
                              timeout=timeout, input=input_text)
    except subprocess.TimeoutExpired:
        raise PMError(f'WSL 命令超时：{" ".join(args[:3])}')
    except OSError as exc:
        raise PMError(f'无法启动 WSL：{exc}')


def to_wsl_path(path: Path | str, distro: str | None = None) -> str:
    value = str(path)
    result = run_wsl(['-e', 'wslpath', '-a', value], timeout=30, distro=distro)
    if result.returncode == 0:
        text = (result.stdout or '').strip().splitlines()
        if text and text[-1].startswith('/'):
            return text[-1]
    # Fallback: drive-letter translation.  Anything else is refused.
    match = re.match(r'^([A-Za-z]):[\\/](.*)$', value)
    if not match:
        raise PMError(f'无法把路径转换为 WSL 路径：{value}')
    tail = match.group(2).replace('\\', '/')
    return f'/mnt/{match.group(1).lower()}/{tail}'


def wsl_available(distro: str | None = None) -> tuple[bool, str]:
    if os.environ.get(DISABLE_ENV, '').strip() == '1':
        return False, '已通过 PROJECT_MEMORY_DISABLE_WSL=1 禁用'
    distro_name = _distro(distro)
    key = (_wsl_exe(), distro_name, os.environ.get(DISABLE_ENV, ''))
    if key in _CACHE:
        return _CACHE[key]
    try:
        probe = run_wsl(['-e', 'sh', '-lc',
                         'for x in unshare timeout base64 sha256sum stat awk python3; do '
                         'command -v "$x" >/dev/null || { echo "missing:$x"; exit 41; }; done; '
                         'echo PM_WSL_OK'], timeout=45, distro=distro_name)
    except PMError as exc:
        return False, str(exc)
    if probe.returncode != 0 or 'PM_WSL_OK' not in (probe.stdout or ''):
        return False, f'WSL 基础探测失败：{(probe.stderr or probe.stdout or "").strip()[:300]}'
    try:
        ns = run_wsl(['-e', 'sh', '-lc',
                      'unshare --user --map-root-user --mount --pid --net --fork --mount-proc '
                      'sh -c \'[ "$(id -u)" = 0 ] && echo PM_NS_OK\''], timeout=45,
                     distro=distro_name)
    except PMError as exc:
        return False, str(exc)
    if ns.returncode != 0 or 'PM_NS_OK' not in (ns.stdout or ''):
        return False, f'WSL2 namespace 预检失败：{(ns.stderr or ns.stdout or "").strip()[:300]}'
    # Only cache success: a transient probe failure must not permanently block a
    # long-lived process, while a cached success still avoids repeated probing.
    result = (True, 'ok')
    _CACHE[key] = result
    return result


def _inner_script() -> str:
    return r'''
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
fail_early() { printf '%s\n' "$1" >&2; exit 97; }
fail() { printf '%s\n' "$1" > /opt/attest/failure 2>/dev/null || printf '%s\n' "$1" >&2; exit 97; }
mount -t tmpfs -o size=1536m,mode=700 tmpfs /opt || fail_early opt-mask-failed
mkdir -p /opt/root /opt/attest /opt/home /opt/tmp
cp -a "$SNAP"/. /opt/root/ || fail_early snapshot-copy-failed
mount --bind "$ATTEST" /opt/attest || fail_early attestation-bind-failed
mount -t tmpfs tmpfs /mnt || fail mnt-mask-failed
mount -t tmpfs tmpfs /tmp || fail tmp-mask-failed
mount -t tmpfs tmpfs /home || fail home-mask-failed
mount -t tmpfs tmpfs /root || fail root-mask-failed
if [ -d /var ]; then mount -t tmpfs tmpfs /var || fail var-mask-failed; fi
if [ -d /etc/ssh ]; then mount -t tmpfs tmpfs /etc/ssh || fail ssh-mask-failed; fi
if [ -d /etc/ssl/private ]; then mount -t tmpfs tmpfs /etc/ssl/private || fail ssl-private-mask-failed; fi
mount -t tmpfs tmpfs /run 2>/dev/null || true
mount -t tmpfs tmpfs /dev/shm 2>/dev/null || true
mount -t tmpfs tmpfs /media 2>/dev/null || true
[ -d /opt/root ] || fail snapshot-missing
[ "$(stat -f -c %T /mnt)" = tmpfs ] || fail mnt-not-tmpfs
[ -z "$(ls -A /mnt)" ] || fail mnt-not-empty
[ "$(stat -f -c %T /tmp)" = tmpfs ] || fail tmp-not-tmpfs
[ "$(stat -f -c %T /home)" = tmpfs ] || fail home-not-tmpfs
[ -z "$(ls -A /home)" ] || fail home-not-empty
[ "$(stat -f -c %T /root)" = tmpfs ] || fail root-not-tmpfs
[ -z "$(ls -A /root)" ] || fail root-not-empty
if [ -d /var ]; then
  [ "$(stat -f -c %T /var)" = tmpfs ] || fail var-not-tmpfs
  [ -z "$(ls -A /var)" ] || fail var-not-empty
fi
[ ! -e "$CANARY" ] || fail original-visible
if ( : > "$CANARY" ) 2>/dev/null; then fail original-writable; fi
# This shell is the init process of a fresh PID namespace.  On this WSL2
# kernel NSpid lists only the innermost level for PID 1 (one field), so
# require $$ == 1 plus a mounted /proc/1 rather than counting NSpid levels.
[ "$$" = "1" ] || fail pid-namespace-missing
ns=$(awk '/^NSpid:/{print NF-1}' /proc/self/status)
[ "${ns:-0}" -ge 1 ] || fail pid-namespace-missing
[ "$(cat /proc/1/comm 2>/dev/null)" != "" ] || fail proc-not-mounted
if grep -qE '^[^[:space:]]+[[:space:]]+00000000[[:space:]]' /proc/net/route; then
  fail default-route-present
fi
extra=$(awk -F: 'NR>2 {gsub(/ /,"",$1); if ($1 != "" && $1 != "lo") print $1}' /proc/net/dev)
[ -z "$extra" ] || fail network-interface-present
env -i PATH="$PATH" HOME=/opt/home TMPDIR=/opt/tmp LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  PYTHONPATH=/opt/root PYTHONDONTWRITEBYTECODE=1 sh -c 'env | cut -d= -f1' \
  > /opt/attest/env_names
if grep -Eiq '(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY|CREDENTIAL|QODER|GITHUB|GH_|OPENAI|ANTHROPIC|DEEPSEEK|HF_|AWS_|AZURE|SSH_AUTH_SOCK|KRB5)' \
  /opt/attest/env_names; then
  fail sensitive-env
fi
env_count=$(wc -l < /opt/attest/env_names)
cmd_sha=$(printf '%s' "$CMD_B64" | base64 -d | sha256sum | awk '{print $1}')
uid_value=$(id -u)
kernel=$(uname -r)
cd /opt/root
set +e
timeout "$TIMEOUT" env -i PATH="$PATH" HOME=/opt/home TMPDIR=/opt/tmp \
  LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONPATH=/opt/root PYTHONDONTWRITEBYTECODE=1 \
  sh -c "$(printf '%s' "$CMD_B64" | base64 -d)" < /dev/null
rc=$?
set -e
printf '%s' "$rc" > /opt/attest/exit_code
printf '%s\n' \
  '{"ok":true,' \
  "\"mode\":\"$MODE\"," \
  "\"receipt_id\":\"$RECEIPT_ID\"," \
  "\"snapshot\":\"$SNAP\"," \
  "\"canary\":\"$CANARY\"," \
  "\"uid\":$uid_value," \
  "\"pid\":$$," \
  "\"pid_ns_levels\":$ns," \
  "\"env_count\":$env_count," \
  "\"command_sha256\":\"$cmd_sha\"," \
  "\"kernel\":\"$kernel\"," \
  "\"distro\":\"$DISTRO\"," \
  "\"created_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
  > /opt/attest/attest.json
exit 0
'''


def run_trusted(repo: Path, snapshot_tree: Path, receipt_id: str, command_text: str, *,
                timeout: int, distro: str | None = None,
                extra_env: dict | None = None) -> dict:
    """Run a command inside the WSL2 namespace sandbox.  Never falls back."""
    if extra_env:
        raise PMError('可信执行不接受 extra_env：环境变量只能来自启动器 allowlist')
    distro_name = _distro(distro)
    available, reason = wsl_available(distro_name)
    if not available:
        raise PMError(f'可信执行不可用（fail-closed，不回退普通子进程）：{reason}')
    snapshot_wsl = to_wsl_path(snapshot_tree, distro_name)
    attest_dir = repo / '.project-memory' / 'attest' / receipt_id
    try:
        attest_dir.resolve().relative_to(repo.resolve())
    except (ValueError, OSError):
        raise PMError('attestation 目录逃逸仓库')
    if attest_dir.exists():
        shutil.rmtree(attest_dir)
    attest_dir.mkdir(parents=True, exist_ok=True)
    for stale in ('attest.json', 'exit_code', 'failure', 'env_names'):
        (attest_dir / stale).unlink(missing_ok=True)
    attest_wsl = to_wsl_path(attest_dir, distro_name)
    canary = repo / '.git' / 'HEAD'
    if not canary.is_file():
        canary = repo / 'README.md' if (repo / 'README.md').is_file() else repo
    canary_wsl = to_wsl_path(canary, distro_name)
    if len(command_text.encode('utf-8')) > 60000:
        raise PMError('可信执行命令过长；请写入脚本后执行')
    command_b64 = base64.b64encode(command_text.encode('utf-8')).decode('ascii')
    variables = {
        'SNAP': snapshot_wsl, 'ATTEST': attest_wsl, 'CANARY': canary_wsl,
        'CMD_B64': command_b64, 'TIMEOUT': str(timeout),
        'RECEIPT_ID': receipt_id, 'MODE': MODE,
        'DISTRO': distro_name or 'default',
    }
    exports = '\n'.join(f'export {key}={shlex_quote(value)}' for key, value in variables.items())
    outer = '#!/bin/sh\nset -eu\n' + exports + '\n' + \
            "unshare --user --map-root-user --mount --pid --net --fork --mount-proc sh -s <<'PM_INNER_SCRIPT'\n" + \
            _inner_script() + '\nPM_INNER_SCRIPT\n'
    encoded = base64.b64encode(outer.encode('utf-8')).decode('ascii')
    try:
        result = run_wsl(['-e', 'sh', '-lc', f'printf %s {shlex_quote(encoded)} | base64 -d | sh'],
                         timeout=timeout + 90, distro=distro_name)
    except PMError:
        raise
    failure = ''
    failure_path = attest_dir / 'failure'
    if failure_path.is_file():
        failure = failure_path.read_text(encoding='utf-8', errors='replace').strip()
    attestation = None
    attest_path = attest_dir / 'attest.json'
    if attest_path.is_file():
        try:
            attestation = json.loads(attest_path.read_text(encoding='utf-8'))
        except Exception as exc:  # noqa: BLE001
            raise PMError(f'可信执行 attestation 不是合法 JSON：{exc}')
    exit_path = attest_dir / 'exit_code'
    exit_code = None
    if exit_path.is_file():
        raw = exit_path.read_text(encoding='utf-8', errors='replace').strip()
        if raw.lstrip('-').isdigit():
            exit_code = int(raw)
    if result.returncode != 0 or not isinstance(attestation, dict) or exit_code is None:
        detail = failure or clean_stderr(result.stderr)[-500:] or (result.stdout or '')[-500:]
        raise PMError(f'可信执行隔离预检失败（没有生成收据）：{detail.strip()}')
    expected = {
        'ok': True, 'mode': MODE, 'receipt_id': receipt_id,
        'snapshot': snapshot_wsl, 'canary': canary_wsl,
    }
    for key, want in expected.items():
        if attestation.get(key) != want:
            raise PMError(f'可信执行 attestation 不一致：{key}={attestation.get(key)!r} != {want!r}')
    if attestation.get('uid') != 0 or int(attestation.get('pid') or 0) != 1:
        raise PMError('可信执行 attestation 没有证明 PID namespace init')
    if int(attestation.get('pid_ns_levels') or 0) < 1:
        raise PMError('可信执行 attestation 没有证明 PID namespace')
    if int(attestation.get('env_count') or 0) < 1:
        raise PMError('可信执行 attestation 没有证明环境 allowlist')
    return {
        'stdout': result.stdout or '',
        'stderr': clean_stderr(result.stderr),
        'exit_code': exit_code,
        'attestation': attestation,
        'attestation_path': str(attest_path.relative_to(repo).as_posix()),
        'attest_dir': str(attest_dir),
        'distro': distro_name or 'default',
    }


def shlex_quote(value: str) -> str:
    import shlex
    return shlex.quote(value)
