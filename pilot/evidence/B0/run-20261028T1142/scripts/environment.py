"""Write environment.txt for the evidence package."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[5]
RUN_DIR = Path(__file__).resolve().parents[1]
RUN_ID = RUN_DIR.name


def git(*args: str) -> str:
    return subprocess.run(['git', '-C', str(CODE_ROOT), *args], check=True,
                          capture_output=True, text=True, encoding='utf-8').stdout.strip()


def main() -> int:
    task_card = CODE_ROOT / 'pilot/rounds/B0/task.md'
    try:
        import pytest
        pytest_version = pytest.__version__
    except ImportError:
        pytest_version = 'missing'
    lines = [
        f'run_id: {RUN_ID}',
        f'generated_at: {datetime.now(timezone.utc).isoformat(timespec="seconds")}',
        'reviewed_candidate: 14cc8fcba367dc36db0706041a21f22e10e3264e',
        f'code_commit: {git("rev-parse", "HEAD")}',
        f'review_base: 73be8e3ac4efc04c1811c122eb665344fe8ce4c3',
        f'branch: {git("rev-parse", "--abbrev-ref", "HEAD")}',
        f'task_card_sha256: {hashlib.sha256(task_card.read_bytes()).hexdigest()}',
        f'cwd: {CODE_ROOT}',
        f'python: {sys.version.splitlines()[0]}',
        f'python_executable: {sys.executable}',
        f'platform: {platform.platform()}',
        f'machine: {platform.machine()}',
        f'git: {git("--version")}',
        f'pytest: {pytest_version}',
        f'openssl: {"found" if __import__("shutil").which("openssl") else "missing"}',
    ]
    (RUN_DIR / 'environment.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8',
                                              newline='\n')
    print('\n'.join(lines))
    print(json.dumps({'ok': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
