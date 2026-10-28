"""Run the original B1 probe under WSL as root against a given code tree.

Paths are given as Windows paths and translated here so no shell-level path
mangling happens. The probe itself is used unmodified from pilot/kit/b1/.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
KIT = ROOT / 'pilot' / 'kit' / 'b1' / 'openssl_substitution.py'


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
    ap.add_argument('--capture-dir', default='')
    args = ap.parse_args()
    out_path = Path(args.out).resolve()
    argv = ['wsl.exe', '-u', 'root', '-e', 'python3', to_wsl(KIT),
            to_wsl(Path(args.code)), to_wsl(Path(args.work)), to_wsl(out_path)]
    proc = subprocess.run(argv, capture_output=True)
    stdout, stderr = decode(proc.stdout), decode(proc.stderr)
    if args.capture_dir:
        capture = Path(args.capture_dir).resolve()
        capture.mkdir(parents=True, exist_ok=True)
        (capture / 'probe-stdout.txt').write_text(stdout, encoding='utf-8')
        (capture / 'probe-stderr.txt').write_text(stderr, encoding='utf-8')
        (capture / 'probe-argv.txt').write_text('\n'.join(argv) + '\n', encoding='utf-8')
        (capture / 'probe-wsl-exit.txt').write_text(str(proc.returncode) + '\n', encoding='utf-8')
    summary = {'wsl_exit_code': proc.returncode,
               'probe_stdout_results': None,
               'output_present': out_path.is_file(),
               'stderr_wsl_notice': stderr.strip()[:200]}
    if out_path.is_file():
        summary['probe_stdout_results'] = json.loads(
            out_path.read_text(encoding='utf-8')).get('results')
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
