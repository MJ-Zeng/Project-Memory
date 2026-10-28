"""B0 evidence driver.

Runs, in order:

1. a baseline (73be8e3) export and the pre-fix reproduction against it;
2. ``cross_path.py`` (AC-1);
3. ``cross_repo.py`` (AC-2 and AC-4);
4. the full pytest suite;

and writes ``commands.jsonl``, ``environment.txt`` and ``diffstat.txt`` next to
the JSON reports.  Run from a clean candidate tree; nothing is written outside
the evidence directory and a temporary work directory.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE_SHA = '73be8e3ac4efc04c1811c122eb665344fe8ce4c3'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def run(argv, cwd, log_path, env):
    started = now()
    result = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env=env)
    finished = now()
    stdout = result.stdout.replace('\r\n', '\n').replace('\r', '\n')
    stderr = result.stderr.replace('\r\n', '\n').replace('\r', '\n')
    body = (f'$ {subprocess.list2cmdline(argv)}\n'
            f'[cwd={cwd}]\n[exit_code={result.returncode}]\n'
            f'--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n')
    log_path.write_text(body, encoding='utf-8', newline='\n')
    return result, {
        'started_at': started,
        'finished_at': finished,
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
    shutil.rmtree(log_dir, ignore_errors=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f'b0-{args.run_id}-'))
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    py = sys.executable
    commands = []

    def record(record_dict):
        commands.append({'seq': len(commands) + 1, **record_dict})

    # 1. baseline export + pre-fix reproduction
    baseline = work / 'baseline'
    baseline.mkdir()
    archive = work / 'base.tar'
    result, entry = run(['git', '-C', str(repo), 'archive', BASE_SHA,
                         '--format=tar', f'--output={archive}'],
                        repo, log_dir / '01-baseline-archive.log', env)
    record(entry)
    with tarfile.open(archive, 'r') as handle:
        try:
            handle.extractall(baseline, filter='data')
        except TypeError:  # Python < 3.12
            handle.extractall(baseline)
    archive.unlink()

    result, entry = run([py, str(evidence / 'scripts/repro_baseline.py'),
                         '--out', str(evidence / 'pre_fix.json'),
                         '--base-sha', BASE_SHA],
                        baseline, log_dir / '02-pre-fix-baseline.log', env)
    record(entry)
    pre_fix_code = result.returncode

    # 2. cross-path positive
    result, entry = run([py, str(evidence / 'scripts/cross_path.py'),
                         '--code-root', str(repo),
                         '--work', str(work / 'cross-path'),
                         '--out', str(evidence / 'cross_path.json'),
                         '--log-dir', str(log_dir)],
                        repo, log_dir / '03-cross-path-driver.log', env)
    record(entry)
    cross_path_code = result.returncode

    # 3. cross-repo negatives
    result, entry = run([py, str(evidence / 'scripts/cross_repo.py'),
                         '--code-root', str(repo),
                         '--work', str(work / 'cross-repo'),
                         '--out', str(evidence / 'cross_repo.json'),
                         '--log-dir', str(log_dir),
                         '--checker', str(evidence / 'scripts/check_receipt.py')],
                        repo, log_dir / '04-cross-repo-driver.log', env)
    record(entry)
    cross_repo_code = result.returncode

    # 4. full test suite
    result, entry = run([py, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
                        repo, evidence / 'pytest.log', env)
    record(entry)
    pytest_code = result.returncode
    pytest_tail = '\n'.join(result.stdout.strip().splitlines()[-3:])

    # environment.txt
    def capture(argv):
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', env=env)
        return (proc.stdout or proc.stderr).strip()

    head = capture(['git', '-C', str(repo), 'rev-parse', 'HEAD'])
    branch = capture(['git', '-C', str(repo), 'rev-parse', '--abbrev-ref', 'HEAD'])
    environment = '\n'.join([
        f'run_id: {args.run_id}',
        f'generated_at: {now()}',
        f'base_sha: {BASE_SHA}',
        f'head_sha: {head}',
        f'branch: {branch}',
        f'cwd: {repo}',
        f'python: {sys.version.splitlines()[0]}',
        f'python_executable: {py}',
        f'platform: {platform.platform()}',
        f'machine: {platform.machine()}',
        f'git: {capture(["git", "--version"])}',
        f'pytest: {capture([py, "-m", "pytest", "--version"])}',
        '',
    ])
    (evidence / 'environment.txt').write_text(environment, encoding='utf-8', newline='\n')

    # diffstat.txt is generated by finalize.py after README.md is written, so it
    # covers the complete evidence directory.

    with (evidence / 'commands.jsonl').open('w', encoding='utf-8', newline='\n') as handle:
        for item in commands:
            handle.write(json.dumps(item, ensure_ascii=False) + '\n')

    summary = {
        'pre_fix_reproduced': pre_fix_code == 0,
        'cross_path_ok': cross_path_code == 0,
        'cross_repo_ok': cross_repo_code == 0,
        'pytest_exit': pytest_code,
        'pytest_tail': pytest_tail,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    shutil.rmtree(work, ignore_errors=True)
    return 0 if all((pre_fix_code == 0, cross_path_code == 0,
                     cross_repo_code == 0, pytest_code == 0)) else 1


if __name__ == '__main__':
    sys.exit(main())
