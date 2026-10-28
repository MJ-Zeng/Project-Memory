"""Launch chain_probe.py inside WSL as root, translating Windows paths.

Same launcher shape as run_probe.py: paths are given as Windows paths and
converted here, so no shell-level path mangling happens.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]


def to_wsl(path: Path) -> str:
    absolute = str(path.resolve()).replace('\\', '/')
    match = re.match(r'^([A-Za-z]):/(.*)$', absolute)
    if not match:
        raise SystemExit(f'not a Windows path: {absolute}')
    return f'/mnt/{match.group(1).lower()}/{match.group(2)}'


def decode(raw: bytes) -> str:
    for encoding in ('utf-8', 'utf-16-le', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    chain = Path(__file__).resolve().with_name('chain_probe.py')
    kit = ROOT / 'pilot' / 'kit' / 'b1' / 'openssl_substitution.py'
    argv = ['wsl.exe', '-u', 'root', '-e', 'python3', to_wsl(chain),
            to_wsl(Path(args.code)), to_wsl(Path(args.work)), to_wsl(Path(args.out)),
            to_wsl(kit)]
    proc = subprocess.run(argv, capture_output=True,
                          env={**os.environ, 'B1_KIT': to_wsl(kit)})
    stdout, stderr = decode(proc.stdout), decode(proc.stderr)
    print(json.dumps({'wsl_exit_code': proc.returncode,
                      'stdout': stdout[-4000:],
                      'stderr': stderr[-800:]}, ensure_ascii=True, indent=2))
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
