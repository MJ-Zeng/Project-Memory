"""Regenerate sha256sums.txt for this evidence pack.

Pack files are hashed over LF-normalized bytes (CRLF -> LF) so the manifest is
checkout-independent.  External fixture files are hashed raw because they are
never checked in and must stay byte-identical to the read-only fixtures.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

RUN = Path(__file__).resolve().parent
MANIFEST = RUN / 'sha256sums.txt'

FIXTURES = Path('C:/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b5a')
EXTERNAL = [
    FIXTURES / 'shadow/project_memory/__init__.py',
    FIXTURES / 'shadow/project_memory/__main__.py',
    FIXTURES / 'cwd-shadow/project_memory/__init__.py',
    FIXTURES / 'cwd-shadow/project_memory/__main__.py',
]


def _digest(path: Path, normalize: bool) -> str:
    data = path.read_bytes()
    if normalize:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def _local_files() -> list[Path]:
    return sorted(
        path for path in RUN.rglob('*')
        if path.is_file()
        and path != MANIFEST
        and '__pycache__' not in path.parts
    )


def main() -> int:
    files = _local_files()
    lines = ['# sha256 over LF-normalized content (CRLF -> LF); verify with verify_hashes.py']
    for path in files:
        lines.append(f'{_digest(path, True)} *./{path.relative_to(RUN).as_posix()}')
    lines.append('# external read-only fixtures (unmodified; hashed raw, checked only when present)')
    for path in EXTERNAL:
        if not path.is_file():
            raise SystemExit(f'external fixture missing: {path}')
        lines.append(f'{_digest(path, False)} *{path.as_posix()}')
    MANIFEST.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'wrote {MANIFEST.name}: {len(files)} local + {len(EXTERNAL)} external entries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
