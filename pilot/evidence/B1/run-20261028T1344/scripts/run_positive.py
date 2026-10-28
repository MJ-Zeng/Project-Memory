"""Launch positive_probe.py inside WSL as root, translating Windows paths."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

def to_wsl(path: Path) -> str:
    absolute = str(path.resolve()).replace('\\', '/')
    match = re.match(r'^([A-Za-z]):/(.*)$', absolute)
    if not match:
        raise SystemExit(f'not a Windows path: {absolute}')
    return f'/mnt/{match.group(1).lower()}/{match.group(2)}'


def decode(raw: bytes) -> str:
    for encoding in ('utf-8', 'utf-16-le'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--fixture', default='pilot/kit/b1/positive')
    ap.add_argument('--scratch', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--label', required=True)
    args = ap.parse_args()
    runner = Path(__file__).resolve().with_name('positive_probe.py')
    argv = ['wsl.exe', '-u', 'root', '-e', 'python3', to_wsl(runner),
            '--code', to_wsl(Path(args.code)), '--fixture', to_wsl(Path(args.fixture)),
            '--scratch', to_wsl(Path(args.scratch)), '--out', to_wsl(Path(args.out)),
            '--label', args.label]
    proc = subprocess.run(argv, capture_output=True)
    print(json.dumps({'wsl_exit_code': proc.returncode,
                      'stdout': decode(proc.stdout)[-3000:],
                      'stderr': decode(proc.stderr)[-1500:]}, ensure_ascii=True, indent=2))
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
