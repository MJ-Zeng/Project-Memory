"""Verify this evidence pack against sha256sums.txt.

Hashes for files inside the pack are computed over LF-normalized bytes
(CRLF -> LF) so the manifest verifies on both a Windows checkout (CRLF working
tree) and a Linux checkout (LF).  External fixture files outside the
repository are hashed raw and only checked when they are present.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
MANIFEST = RUN / 'sha256sums.txt'
EXTERNAL = re.compile(r'^[A-Za-z]:[\\/]')


def _digest(path: Path, normalize: bool) -> str:
    data = path.read_bytes()
    if normalize:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def _entries(path: Path):
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        digest, _, name = line.partition(' ')
        yield digest, name.lstrip('*').strip()


def main() -> int:
    failures = []
    external_missing = []
    checked = 0
    for digest, name in _entries(MANIFEST):
        external = bool(EXTERNAL.match(name))
        target = Path(name) if external else RUN / name
        if not target.is_file():
            if external:
                external_missing.append(name)
            else:
                failures.append(f'MISSING  {name}')
            continue
        checked += 1
        actual = _digest(target, normalize=not external)
        if actual != digest:
            failures.append(f'MISMATCH {name}\n'
                            f'  expected {digest}\n'
                            f'  actual   {actual}')
    for line in failures:
        print(line)
    if failures:
        print(f'FAILED: {len(failures)} entry/entries did not verify')
        return 1
    print(f'OK: {checked} entries verified (LF-normalized); '
          f'{len(external_missing)} external fixture record(s) not present')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
