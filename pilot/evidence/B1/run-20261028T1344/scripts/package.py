"""Make the B1 evidence package byte-stable: LF everywhere, then hash it.

The wrapper scripts above wrote logs with the platform newline (CRLF on
Windows).  The repository pins ``pilot/** text eol=lf`` in .gitattributes, so a
CRLF file on disk would not match the blob git stores and ``sha256sum -c`` would
fail for anyone checking out the candidate.  This step converts CRLF to LF in the
already-produced evidence files -- line endings only, no content change --
repairs each journal entry's ``log_sha256`` while keeping the pre-conversion
digest, journals itself the way the other steps are journaled, and only then
writes sha256sums.txt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
ROOT = RUN.parents[3]
SCRATCH = ['work/before', 'work/after', 'work/chain-before', 'work/chain-after',
           'work/positive-before-scratch', 'work/positive-after-scratch']


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def kept(path: Path) -> bool:
    excluded = [RUN / item for item in SCRATCH]
    return path.is_file() and not any(path == item or item in path.parents
                                      for item in excluded)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', required=True)
    ap.add_argument('--command', required=True, help='exact invocation, for the journal')
    ap.add_argument('--env-note', default='')
    args = ap.parse_args()

    started = now()
    report = []
    for path in sorted(p for p in RUN.rglob('*') if kept(p) and p.name != 'sha256sums.txt'):
        raw = path.read_bytes()
        normalized = raw
        while b'\r\n' in normalized:
            normalized = normalized.replace(b'\r\n', b'\n')
        if normalized == raw:
            continue
        path.write_bytes(normalized)
        report.append((str(path.relative_to(RUN)).replace('\\', '/'),
                       hashlib.sha256(raw).hexdigest(),
                       hashlib.sha256(normalized).hexdigest()))
    converted = {item[1]: item[2] for item in report}

    journal = RUN / 'commands.jsonl'
    entries = [json.loads(line) for line in
               journal.read_text(encoding='utf-8').splitlines() if line.strip()]
    repaired = 0
    for entry in entries:
        old = entry.get('log_sha256')
        new = converted.get(old)
        if new:
            entry['log_sha256'] = new
            entry['log_sha256_before_eol_normalization'] = old
            repaired += 1
    journal.write_text(''.join(json.dumps(entry, ensure_ascii=False) + '\n'
                               for entry in entries), encoding='utf-8', newline='\n')

    log_dir = RUN / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (args.label + '.log')
    body = ['COMMAND: ' + args.command,
            'CWD: ' + str(ROOT),
            'ENV: ' + (args.env_note or 'inherited'),
            'EXIT: 0',
            'files converted CRLF -> LF: %d (line endings only, content unchanged)' % len(report),
            'journal entries whose log_sha256 was re-pointed: %d' % repaired,
            'pre-conversion digests are kept per entry as log_sha256_before_eol_normalization',
            '--- table: path / sha256 before / sha256 after ---']
    body += ['%s  %s  %s' % item for item in report]
    log_path.write_text('\n'.join(body) + '\n', encoding='utf-8', newline='\n')

    entries.append({
        'seq': len(entries) + 1,
        'started_at': started,
        'finished_at': now(),
        'cwd': str(ROOT),
        'command': args.command,
        'exit_code': 0,
        'env': args.env_note or 'inherited',
        'log': str(log_path.relative_to(ROOT)).replace('\\', '/'),
        'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
        'stdout_tail': 'converted=%d repaired=%d' % (len(report), repaired),
        'stderr_tail': '',
    })
    journal.write_text(''.join(json.dumps(entry, ensure_ascii=False) + '\n'
                               for entry in entries), encoding='utf-8', newline='\n')

    lines = [hashlib.sha256(path.read_bytes()).hexdigest() + '  '
             + str(path.relative_to(RUN)).replace('\\', '/')
             for path in sorted(p for p in RUN.rglob('*') if kept(p)
                                and p.name != 'sha256sums.txt')]
    (RUN / 'sha256sums.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')

    print('converted CRLF->LF:', len(report))
    print('journal entries re-pointed:', repaired)
    print('journal lines:', len(entries))
    print('hashed files:', len(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
