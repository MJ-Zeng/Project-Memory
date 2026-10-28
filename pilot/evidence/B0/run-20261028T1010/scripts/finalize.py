"""Package an evidence directory: complete diffstat, command log, checksums.

Must run *after* ``run_evidence.py`` and after ``README.md`` is written, because
the diffstat covers the whole evidence directory.  It marks the evidence files
as intent-to-add so ``git diff`` shows the new files, appends its own commands to
``commands.jsonl``, and writes ``sha256sums.txt`` last.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_SHA = '73be8e3ac4efc04c1811c122eb665344fe8ce4c3'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def run(argv, cwd, log_path, env):
    started = now()
    result = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env=env)
    stdout = result.stdout.replace('\r\n', '\n').replace('\r', '\n')
    stderr = result.stderr.replace('\r\n', '\n').replace('\r', '\n')
    body = (f'$ {subprocess.list2cmdline(argv)}\n'
            f'[cwd={cwd}]\n[exit_code={result.returncode}]\n'
            f'--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n')
    log_path.write_text(body, encoding='utf-8', newline='\n')
    return result, {
        'started_at': started,
        'finished_at': now(),
        'cwd': str(cwd),
        'command': subprocess.list2cmdline(argv),
        'exit_code': result.returncode,
        'log': str(log_path),
        'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[5]
    evidence = Path(__file__).resolve().parents[1]
    log_dir = evidence / 'logs'
    env = dict(os.environ, PYTHONIOENCODING='utf-8')

    existing = (evidence / 'commands.jsonl').read_text(encoding='utf-8').splitlines() \
        if (evidence / 'commands.jsonl').is_file() else []
    commands = [json.loads(line) for line in existing if line.strip()]

    def append(entry):
        commands.append({'seq': len(commands) + 1, **entry})

    evidence_rel = evidence.relative_to(repo).as_posix()
    intent, entry = run(['git', '-C', str(repo), 'add', '-N', '--', evidence_rel],
                        repo, log_dir / '07-intent-to-add.log', env)
    append(entry)
    diff, entry = run(['git', '-C', str(repo), 'diff', '--stat', BASE_SHA],
                      repo, log_dir / '08-diffstat.log', env)
    append(entry)
    status, entry = run(['git', '-C', str(repo), 'status', '--short', '--branch'],
                        repo, log_dir / '09-git-status.log', env)
    append(entry)

    (evidence / 'diffstat.txt').write_text(
        f'$ git diff --stat {BASE_SHA}\n{diff.stdout.replace(chr(13), "")}'
        f'$ git status --short --branch\n{status.stdout.replace(chr(13), "")}',
        encoding='utf-8', newline='\n')

    with (evidence / 'commands.jsonl').open('w', encoding='utf-8', newline='\n') as handle:
        for item in commands:
            handle.write(json.dumps(item, ensure_ascii=False) + '\n')

    lines = []
    for path in sorted(evidence.rglob('*')):
        if not path.is_file() or path.name == 'sha256sums.txt':
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f'{digest}  {path.relative_to(evidence).as_posix()}')
    (evidence / 'sha256sums.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8',
                                             newline='\n')
    print(json.dumps({'files': len(lines), 'evidence': str(evidence)}, ensure_ascii=False))
    return 0 if intent.returncode == 0 and diff.returncode == 0 and status.returncode == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
