"""Collect the B1 evidence package: copies, environment.txt, diffstat.txt, sha256sums.txt.

Authored for the evidence directory only; it does not touch product code.
Run it from the repository root with the Windows interpreter.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
ROOT = RUN.parents[3]
BASELINE = '25a919d63c7181fd4083e0fc1af33734d74c5515'
CANDIDATE = '89ea4bd7fdbddaf90f640d4cc1b71d66fd1a63e3'
ANCHOR = '/etc/pm-rc3-review/anchor-a.json'
SCRATCH = ['work/before', 'work/after', 'work/chain-before', 'work/chain-after',
           'work/positive-before-scratch', 'work/positive-after-scratch']


def git(*args: str) -> str:
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True,
                          text=True, encoding='utf-8', check=True).stdout


def wsl(*args: str) -> str:
    proc = subprocess.run(['wsl.exe', '-u', 'root', '-e', *args],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace')
    return (proc.stdout or proc.stderr or '').strip()


def main() -> int:
    (RUN / 'pytest.log').write_bytes((RUN / 'logs/22-full-suite-candidate.log').read_bytes())
    shutil.copyfile(RUN / 'work/positive-before.json', RUN / 'positive-before.json')
    shutil.copyfile(RUN / 'work/positive-after.json', RUN / 'positive-after.json')
    before = json.loads((RUN / 'positive-before.json').read_text(encoding='utf-8'))
    after = json.loads((RUN / 'positive-after.json').read_text(encoding='utf-8'))
    (RUN / 'positive.json').write_text(json.dumps({
        'note': 'Index of the two positive-fixture runs. The full machine-readable '
                'output of each run is positive-before.json / positive-after.json.',
        'fixture': 'pilot/kit/b1/positive (unmodified)',
        'before_fix': before,
        'after_fix': after,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    environment = [
        'B1 evidence environment',
        'captured_at: ' + datetime.now().astimezone().isoformat(timespec='seconds'),
        'run_id: ' + RUN.name,
        'branch: ' + git('rev-parse', '--abbrev-ref', 'HEAD').strip(),
        'candidate_sha: ' + CANDIDATE,
        'baseline_sha: ' + BASELINE,
        '',
        '[windows]',
        'platform: ' + ' '.join(part for part in (
            platform.system(), platform.release(), platform.version(),
            platform.machine())),
        'python: ' + sys.version.replace('\n', ' '),
        'python_path: ' + sys.executable,
        'git: ' + git('--version').strip(),
        'cwd: ' + str(ROOT),
        'whoami: ' + os.environ.get('USERNAME', '?'),
        '',
        '[wsl (probe harness)]',
        'wsl_uname: ' + wsl('uname', '-a'),
        'wsl_python3: ' + wsl('python3', '--version'),
        'wsl_openssl: ' + wsl('openssl', 'version'),
        'anchor_stat: ' + wsl('stat', '-c', '%U:%G %a %n', ANCHOR),
        'anchor_dir_stat: ' + wsl('stat', '-c', '%U:%G %a %n', os.path.dirname(ANCHOR)),
        'private_key: /etc/pm-rc3-review/key-a.pem was never read or used by PM-02; '
        'the fixture signature comes from pilot/kit/b1/positive (human-signed), '
        'and PM-02 holds no signing key.',
        'probe_sha256: ' + hashlib.sha256(
            (ROOT / 'pilot/kit/b1/openssl_substitution.py').read_bytes()).hexdigest(),
        '',
        '[project_memory.authority]',
        'baseline_authority_sha256: 4805b06b45e208013013a872cce0e6b5f5e2c67794f8ea237eb1e07ff384a88d',
        'candidate_authority_sha256: ' + hashlib.sha256(
            (ROOT / 'project_memory/authority.py').read_bytes()).hexdigest(),
        '',
        '[notes]',
        'PROJECT_MEMORY_OPENSSL is no longer read by authority.py; the env var is dead.',
        'The probe working dirs listed below are throwaway fixtures (each contains a',
        'temporary git repo used by the probe) and are not part of the evidence set:',
    ] + ['  - ' + item for item in SCRATCH]
    (RUN / 'environment.txt').write_text('\n'.join(environment) + '\n', encoding='utf-8')

    diffstat = (
        'git diff --stat ' + BASELINE[:7] + '..' + CANDIDATE[:7] + '\n'
        + git('diff', '--stat', BASELINE, CANDIDATE)
        + '\ngit diff --name-status ' + BASELINE[:7] + '..' + CANDIDATE[:7] + '\n'
        + git('diff', '--name-status', BASELINE, CANDIDATE)
        + '\ngit log --oneline ' + BASELINE[:7] + '..' + CANDIDATE[:7] + '\n'
        + git('log', '--oneline', BASELINE + '..' + CANDIDATE)
        + '\ngit diff --stat ' + BASELINE[:7] + '..' + CANDIDATE[:7] + ' -- project_memory tests docs\n'
        + git('diff', '--stat', BASELINE, CANDIDATE, '--', 'project_memory', 'tests', 'docs'))
    (RUN / 'diffstat.txt').write_text(diffstat, encoding='utf-8')

    excluded = [RUN / item for item in SCRATCH] + [RUN / 'sha256sums.txt']

    def keep(path: Path) -> bool:
        return path.is_file() and not any(path == item or item in path.parents
                                          for item in excluded)

    lines = []
    for path in sorted(p for p in RUN.rglob('*') if keep(p)):
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  '
                     + str(path.relative_to(RUN)).replace('\\', '/'))
    (RUN / 'sha256sums.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('evidence files:', len(lines))
    print('environment.txt sha256:',
          hashlib.sha256((RUN / 'environment.txt').read_bytes()).hexdigest())
    return 0


if __name__ == '__main__':
    sys.exit(main())
