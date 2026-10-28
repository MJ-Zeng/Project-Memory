"""Execute one command, archive its output, and append a commands.jsonl entry."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('--commands', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('缺少命令')
    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    started = now()
    result = subprocess.run(command, cwd=args.cwd, capture_output=True)
    finished = now()
    payload = (result.stdout + result.stderr).replace(b'\r\n', b'\n')
    log.write_bytes(payload)
    entry = {
        'seq': 1,
        'started_at': started,
        'finished_at': finished,
        'cwd': str(Path(args.cwd).resolve()),
        'command': subprocess.list2cmdline(command),
        'exit_code': result.returncode,
        'log': str(log.resolve()),
        'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
    }
    lines = Path(args.commands).read_text(encoding='utf-8').splitlines() \
        if Path(args.commands).exists() else []
    entry['seq'] = len([line for line in lines if line.strip()]) + 1
    with Path(args.commands).open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
