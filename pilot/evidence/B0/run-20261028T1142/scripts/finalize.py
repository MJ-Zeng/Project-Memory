"""Append the finalize entry, then hash every other file in the run directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def files_to_hash() -> list[Path]:
    return sorted(path for path in RUN_DIR.rglob('*')
                  if path.is_file() and path.name != 'sha256sums.txt')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--command', required=True,
                        help='exact command line that invoked this script')
    args = parser.parse_args()
    commands = RUN_DIR / 'commands.jsonl'
    log = RUN_DIR / 'logs/05-sha256sums.log'

    started = now()
    listing = [str(path.relative_to(RUN_DIR)).replace('\\', '/')
               for path in files_to_hash()]
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('hashing files:\n' + '\n'.join(listing) + '\n', encoding='utf-8',
                   newline='\n')
    finished = now()

    existing = [line for line in commands.read_text(encoding='utf-8').splitlines()
                if line.strip()] if commands.exists() else []
    entry = {
        'seq': len(existing) + 1,
        'started_at': started,
        'finished_at': finished,
        'cwd': str(RUN_DIR.parents[3].resolve()),
        'command': args.command,
        'exit_code': 0,
        'log': str(log.resolve()),
        'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
    }
    with commands.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + '\n')

    lines = []
    for path in files_to_hash():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f'{digest}  {path.relative_to(RUN_DIR).as_posix()}')
    (RUN_DIR / 'sha256sums.txt').write_text('\n'.join(lines) + '\n',
                                            encoding='utf-8', newline='\n')
    print(f'{len(lines)} files hashed')
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
