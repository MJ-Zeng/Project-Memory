"""Trusted CLI launcher: start Python isolated before importing ``project_memory``.

A same-named package earlier on ``sys.path`` (cwd or ``PYTHONPATH``) executes
before ``project_memory/__main__.py`` and before any console-script import.  The
only place that can still win is a process started with an interpreter that is
both isolated and safe-path, which is what this module does before touching the
package.  See docs/decisions/ADR-0005-cli-bootstrap.md.

This module deliberately lives outside the package so that shadowing
``project_memory`` does not shadow the launcher itself.  Shadowing this module
name, rewriting it, or replacing the interpreter is equivalent to replacing the
whole process and is outside what any in-process control can defend.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_PYTHON_PATH_VARS = ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP',
                     'PYTHONUSERBASE', 'PYTHONSAFEPATH', 'PYTHONNOUSERSITE')
_UNTRUSTED_EXIT = 3


def _trusted_root() -> Path:
    return Path(__file__).resolve().parent


def _trusted_env() -> dict:
    env = {key: value for key, value in os.environ.items()
           if key not in _PYTHON_PATH_VARS}
    env.update({'PYTHONNOUSERSITE': '1', 'PYTHONSAFEPATH': '1'})
    return env


def _child_command(python: str, argv: list[str]) -> list[str]:
    root = _trusted_root()
    if (root / 'project_memory' / '__init__.py').is_file():
        code = ('import sys; sys.path.insert(0, sys.argv[1]); '
                'from project_memory.cli import main; '
                'raise SystemExit(main(sys.argv[2:]))')
        return [python, '-I', '-P', '-c', code, str(root), *argv]
    return [python, '-I', '-P', '-m', 'project_memory', *argv]


def _say(message: str) -> None:
    for stream in (sys.stderr,):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except (OSError, ValueError):
                pass
    print(message, file=sys.stderr)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    python = sys.executable
    if not python or not Path(python).is_absolute():
        _say('project-memory：无法确认受信解释器；拒绝启动')
        return _UNTRUSTED_EXIT
    command = _child_command(python, argv)
    try:
        return subprocess.call(command, env=_trusted_env(), close_fds=True)
    except OSError as exc:
        _say(f'project-memory：隔离启动失败：{exc}')
        return _UNTRUSTED_EXIT


if __name__ == '__main__':
    raise SystemExit(main())
