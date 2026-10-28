"""PM-03 AC-1: the human-presigned positive fixture must still verify.

Copies the fixture out of the repo, checks its manifest, unpacks the template
repo, and runs `goal evidence` as uid 1000 against the root-owned anchor.
Written independently for the B1 review.

Usage (as root): python3 positive_reviewer.py <CODE> <POSITIVE_DIR> <OUT.json>
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

CODE = Path(sys.argv[1]).resolve()
POSITIVE = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
AGENT_UID, AGENT_GID = 1000, 1000
ANCHOR = '/etc/pm-rc3-review/anchor-a.json'
PATH_BASE = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
RECORD_REL = Path('.project-memory/verifications/4/VER-positive.json')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b''):
            digest.update(chunk)
    return digest.hexdigest()


def check_manifest(fixture: Path) -> dict:
    rows = []
    ok = 0
    for line in (fixture / 'sha256sums.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        expected, name = line.split('*', 1)
        target = fixture / name.strip()
        actual = sha256_file(target) if target.is_file() else None
        passed = actual == expected.strip()
        ok += int(passed)
        rows.append({'file': name.strip(), 'expected': expected.strip(),
                     'actual': actual, 'ok': passed})
    return {'ok': ok, 'total': len(rows), 'rows': rows}


def chown_tree(path: Path) -> None:
    os.chown(path, AGENT_UID, AGENT_GID)
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                os.chown(os.path.join(root, name), AGENT_UID, AGENT_GID, follow_symlinks=False)
            except (OSError, NotImplementedError):
                pass


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix='pm03-positive-', dir='/tmp'))
    fixture = work / 'fixture'
    shutil.copytree(POSITIVE, fixture, symlinks=True)
    summary = {'code': str(CODE), 'manifest': check_manifest(fixture)}

    extract = work / 'extract'
    extract.mkdir()
    with tarfile.open(fixture / 'template-repo.tar.gz', 'r:gz') as archive:
        archive.extractall(extract, filter='data')
    run = work / 'run'
    shutil.copytree(extract / 'repo', run, symlinks=True)
    home = work / 'home'
    home.mkdir()

    env = {'PATH': PATH_BASE, 'HOME': str(home), 'PYTHONPATH': str(CODE),
           'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM': '1', 'PROJECT_MEMORY_TRUST_ANCHOR': ANCHOR}

    def as_agent(*args) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=str(run), capture_output=True, text=True,
                              encoding='utf-8', env=env, user=AGENT_UID,
                              group=AGENT_GID, extra_groups=[])

    chown_tree(work)
    as_agent('git', 'config', 'core.autocrlf', 'true')
    as_agent('git', 'config', 'core.fileMode', 'false')

    record = run / RECORD_REL
    before = sha256_file(record)
    proc = as_agent(sys.executable, '-m', 'project_memory', 'goal', 'evidence',
                    '--repo', '.', '--id', 'G-B1', '--criterion', 'C1',
                    '--kind', 'verification', '--ref', 'VER-positive')
    after = sha256_file(record)

    expected = json.loads((fixture / 'goal-evidence-result.json').read_text(encoding='utf-8'))
    try:
        produced = json.loads(proc.stdout)
        matches_expected = produced == expected
    except Exception:
        produced = None
        matches_expected = False

    summary.update({
        'record_sha256_before': before,
        'record_sha256_after': after,
        'record_unchanged': before == after,
        'goal_evidence_exit': proc.returncode,
        'stderr_bytes': len(proc.stderr.encode('utf-8')),
        'stderr': proc.stderr[-1000:],
        'stdout_tail': proc.stdout[-2000:],
        'matches_goal_evidence_result': matches_expected,
        'expected_authority_status': (
            expected.get('goal', {}).get('success_criteria', [{}])[0]
            .get('evidence', [{}])[0].get('ref') if expected else None),
        'workdir': str(work),
    })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ('manifest', 'stdout_tail')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
