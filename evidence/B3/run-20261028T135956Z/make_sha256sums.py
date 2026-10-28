"""Regenerate sha256sums.txt for this evidence pack.

Pack files are hashed over LF-normalized bytes (CRLF -> LF) so the manifest is
checkout-independent.  External fixture records are hashed raw because they are
never checked in and are expected to stay byte-identical to the fixtures.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

RUN = Path(__file__).resolve().parent
MANIFEST = RUN / 'sha256sums.txt'

FIXTURES = Path('C:/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b2')
EXTERNAL = [
    FIXTURES / 'genuine-trusted/repo/.project-memory/verifications/325/VER-B2-genuine-trusted.json',
    FIXTURES / 'exception/repo/.project-memory/verifications/325/VER-B2-exception.json',
    FIXTURES / 'forged-untrusted/repo/.project-memory/verifications/325/VER-B2-forged-untrusted.json',
    FIXTURES / 'forged-claimed-trusted/repo/.project-memory/verifications/325/VER-B2-forged-claimed-trusted.json',
]


def _digest(path: Path, normalize: bool) -> str:
    data = path.read_bytes()
    if normalize:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    files = sorted(p for p in RUN.rglob('*') if p.is_file() and p != MANIFEST)
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
    main()
