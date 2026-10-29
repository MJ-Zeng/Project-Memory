"""Trusted CLI bootstrap: run isolated, then import ``project_memory`` from a
trusted root only.

This file is NOT an importable console-script target.  It is invoked BY ABSOLUTE
PATH from a native OS wrapper (``bin/project-memory`` / ``bin/project-memory.cmd``)
that has already started the interpreter with ``-I -P``.  A pip
``module:function`` console_script instead resolves a top-level module name
through the ambient ``sys.path`` BEFORE any isolation, so a same-named file on
``PYTHONPATH``/cwd executes first and never reaches this code (B5A.1).  Running
by absolute path under ``-I -P`` removes both preemption vectors: no name is
resolved through ``sys.path``, and ``PYTHONPATH``/cwd/user-site are dropped.

Given isolation, this bootstrap locates the trusted root (its own directory) and
(re)starts an interpreter that imports ``project_memory`` only from that root, so
the CLI's signing, receipts and Goal state machine cannot be replaced by a
same-named package.  See docs/decisions/ADR-0005-cli-bootstrap.md.

Rewriting this file, the wrapper, or the interpreter is equivalent to replacing
the whole process and is outside what any in-process control can defend.
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
