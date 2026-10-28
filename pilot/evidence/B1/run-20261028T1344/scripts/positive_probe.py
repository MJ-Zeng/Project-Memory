"""Run the AC-1 positive fixture (human-signed record) against a code tree.

Executed inside WSL as root so the CLI can be dropped to uid 1000 against the
root-owned trust anchor, the same shape the original probe uses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

AGENT_UID = 1000
AGENT_GID = 1000
ANCHOR = Path('/etc/pm-rc3-review/anchor-a.json')
CHECKED = ('VER-positive.json', 'template-repo.tar.gz', 'anchor-a.json', 'pub-a.pem')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chown_tree(root: Path) -> None:
    for item in [root, *root.rglob('*')]:
        os.chown(item, AGENT_UID, AGENT_GID)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--fixture', required=True)
    ap.add_argument('--scratch', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--label', required=True)
    args = ap.parse_args()

    code = Path(args.code)
    fixture = Path(args.fixture)
    scratch = Path(args.scratch)
    out = Path(args.out)
    report: dict = {'label': args.label, 'code': str(code), 'anchor': str(ANCHOR),
                    'fixture_hashes': {}, 'hash_mismatches': [], 'steps': []}

    expected = {}
    for line in (fixture / 'sha256sums.txt').read_text(encoding='utf-8').splitlines():
        digest, _, name = line.partition('*')
        expected[name.strip()] = digest.strip()
    for name in CHECKED:
        actual = sha256(fixture / name)
        report['fixture_hashes'][name] = actual
        if expected.get(name) != actual:
            report['hash_mismatches'].append({'file': name, 'expected': expected.get(name),
                                              'actual': actual})
    report['anchor_matches_fixture_copy'] = sha256(ANCHOR) == sha256(fixture / 'anchor-a.json')

    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    unpacked = scratch / 'tar'
    unpacked.mkdir()
    with tarfile.open(fixture / 'template-repo.tar.gz') as handle:
        handle.extractall(unpacked)
    template = unpacked / 'repo'
    run_copy = scratch / 'run-copy'
    shutil.copytree(template, run_copy, symlinks=True)
    chown_tree(scratch)

    record_path = None
    for candidate in run_copy.rglob('VER-positive.json'):
        record_path = candidate
    report['record_path'] = str(record_path)
    report['record_sha256_before'] = sha256(record_path) if record_path else None

    env = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
           'HOME': str(scratch / 'home'), 'PYTHONPATH': str(code), 'PYTHONUTF8': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
           'PROJECT_MEMORY_TRUST_ANCHOR': str(ANCHOR)}
    os.makedirs(env['HOME'], exist_ok=True)
    os.chown(env['HOME'], AGENT_UID, AGENT_GID)

    def agent(argv, cwd):
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', env=env,
                              user=AGENT_UID, group=AGENT_GID, extra_groups=[])
        report['steps'].append({'argv': argv[:1] + argv[2:4] if argv[0] == 'git' else argv,
                               'cwd': str(cwd), 'exit_code': proc.returncode,
                               'stdout': (proc.stdout or '')[-4000:],
                               'stderr': (proc.stderr or '')[-2000:]})
        return proc

    agent(['git', '-C', str(run_copy), 'config', 'core.autocrlf', 'true'], run_copy)
    agent(['git', '-C', str(run_copy), 'config', 'core.fileMode', 'false'], run_copy)
    cli = agent([sys.executable, '-m', 'project_memory', 'goal', 'evidence',
                 '--repo', '.', '--id', 'G-B1', '--criterion', 'C1',
                 '--kind', 'verification', '--ref', 'VER-positive'], run_copy)
    report['goal_evidence_exit'] = cli.returncode
    report['goal_evidence_stdout'] = (cli.stdout or '')[-4000:]
    report['goal_evidence_stderr'] = (cli.stderr or '')[-2000:]
    report['goal_evidence_accepted'] = cli.returncode == 0
    report['record_sha256_after'] = sha256(record_path) if record_path else None
    report['record_unchanged'] = (report['record_sha256_before']
                                  == report['record_sha256_after'])
    goal_path = run_copy / '.project-memory/goals/G-B1.json'
    if goal_path.is_file():
        report['goal_status_after'] = json.loads(goal_path.read_text(encoding='utf-8'))['status']

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in
                      ('label', 'goal_evidence_exit', 'goal_evidence_accepted',
                       'record_unchanged', 'anchor_matches_fixture_copy', 'hash_mismatches')},
                     ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
