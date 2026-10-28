"""Run one command, capture its log, and append a line to commands.jsonl.

Used only to build the B1 evidence package; it does not touch product code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent
ROOT = RUN.parents[3]
JOURNAL = RUN / 'commands.jsonl'


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def next_seq() -> int:
    if not JOURNAL.exists():
        return 1
    return sum(1 for line in JOURNAL.read_text(encoding='utf-8').splitlines()
               if line.strip()) + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', required=True)
    ap.add_argument('--cwd', default=str(ROOT))
    ap.add_argument('--env-note', default='')
    ap.add_argument('--set-env', action='append', default=[])
    ap.add_argument('command', nargs=argparse.REMAINDER)
    args = ap.parse_args()

    argv = list(args.command)
    while argv[:1] == ['--']:
        argv = argv[1:]
    if not argv:
        print('no command given', file=sys.stderr)
        return 2
    child_env = dict(os.environ)
    for item in args.set_env:
        key, _, value = item.partition('=')
        child_env[key] = value
    command = ' '.join(shlex.quote(a) for a in argv)
    started = now()
    proc = subprocess.run(argv, cwd=args.cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=child_env)
    finished = now()

    log_dir = RUN / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (args.label + '.log')
    log_path.write_text(
        'COMMAND: ' + command + '\n'
        + 'CWD: ' + str(args.cwd) + '\n'
        + 'ENV: ' + (args.env_note or 'inherited') + '\n'
        + 'EXIT: ' + str(proc.returncode) + '\n'
        + '--- stdout ---\n' + (proc.stdout or '')
        + '--- stderr ---\n' + (proc.stderr or ''), encoding='utf-8')
    record = {
        'seq': next_seq(),
        'started_at': started,
        'finished_at': finished,
        'cwd': str(args.cwd),
        'command': command,
        'exit_code': proc.returncode,
        'env': args.env_note or 'inherited',
        'log': str(log_path.relative_to(ROOT)).replace('\\', '/'),
        'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
        'stdout_tail': (proc.stdout or '')[-400:],
        'stderr_tail': (proc.stderr or '')[-400:],
    }
    with open(JOURNAL, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    sys.stdout.write(f"seq={record['seq']} exit={proc.returncode} log={record['log']}\n")
    sys.stdout.write((proc.stdout or '')[-1500:])
    if proc.returncode != 0:
        sys.stdout.write((proc.stderr or '')[-1500:])
    return 0


if __name__ == '__main__':
    sys.exit(main())
