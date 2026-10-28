"""Entry point for ``python -m project_memory``.

A same-named package earlier on ``sys.path`` runs before this module, so the
checks below are defence in depth, not the primary control: the trusted entry is
the ``project-memory`` console script / launcher (ADR-0005).
"""
from __future__ import annotations

import sys
from pathlib import Path

UNTRUSTED_EXIT = 3


def _trusted_package() -> Path:
    return Path(__file__).resolve().parent


def _isolated() -> bool:
    return bool(getattr(sys.flags, 'isolated', False)
                and getattr(sys.flags, 'safe_path', False))


def _shadowed_paths() -> list[str]:
    package_dir = _trusted_package()
    shadows = []
    for entry in sys.path:
        if not entry:
            continue
        try:
            base = Path(entry).resolve()
        except OSError:
            continue
        candidate = base / 'project_memory' / '__init__.py'
        if not candidate.is_file():
            continue
        try:
            if candidate.parent.resolve() == package_dir:
                continue
        except OSError:
            continue
        shadows.append(str(candidate.parent))
    return shadows


def _refuse(message: str) -> int:
    from .common import ensure_utf8_stdio
    ensure_utf8_stdio()
    print(f'project-memory：{message}', file=sys.stderr)
    return UNTRUSTED_EXIT


def main() -> int:
    if not Path(__file__).is_absolute():
        return _refuse('启动路径不可信（包路径不是绝对路径）；请使用 project-memory 启动器')
    if not _isolated():
        shadows = _shadowed_paths()
        if shadows:
            return _refuse('检测到同名 project_memory 包位于不可信路径：'
                           + ', '.join(shadows)
                           + '；拒绝以未隔离方式启动，请使用 project-memory 启动器')
    from .cli import main as cli_main
    return cli_main()


raise SystemExit(main())
