"""Assemble environment.txt, diffstat.txt and ac1b_compare.json for this run."""
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EV = Path(__file__).resolve().parent
WORKSPACE = EV.parents[3]
CANDIDATE = WORKSPACE / '.pilot' / 'candidate'
PREV = WORKSPACE / '.pilot' / 'prev'
BASE = WORKSPACE / '.pilot' / 'base'
FIXTURE = Path('C:/Documents/02_Research/Code/project-memory-verification-lab/'
               'fixtures/b0-positive')
BASE_SHA = '73be8e3ac4efc04c1811c122eb665344fe8ce4c3'
PREV_SHA = '14cc8fcba367dc36db0706041a21f22e10e3264e'
CAND_SHA = '8506dd4db225ac9d04db1983d7bcfca9db13ee70'
PR_HEAD = '8f7a63e7c049638083436fb070fc56d2e56b411b'


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git(*args):
    return run(['git', *args], cwd=WORKSPACE)


def write(name, text):
    (EV / name).write_text(text.rstrip('\n') + '\n', encoding='utf-8',
                           newline='\n')


def main():
    ac1b_env = (EV / 'ac1b_environment.txt').read_text(encoding='utf-8').strip()
    lines = [
        f'run_id: {EV.name}',
        f'generated_at: {datetime.now(timezone.utc).isoformat()}',
        'reviewer: PM-03 Independent Reviewer (independent session)',
        f'host: {platform.platform()} / {platform.machine()}',
        'shell: Git Bash (win32)',
        f'windows_python: {sys.executable} {platform.python_version()}',
    ]
    code, out, _ = run(['C:/SoftWare/Anconda/python.exe', '-m', 'pytest',
                        '--version'], cwd=CANDIDATE)
    lines.append(f'pytest: {out.splitlines()[0] if out else "unknown"}')
    code, out, _ = git('--version')
    lines.append(f'git: {out}')
    for label, path, sha in (('base_worktree', BASE, BASE_SHA),
                             ('prev_worktree', PREV, PREV_SHA),
                             ('candidate_worktree', CANDIDATE, CAND_SHA)):
        code, head, _ = run(['git', '-C', str(path), 'rev-parse', 'HEAD'])
        code, status, _ = run(['git', '-C', str(path), 'status', '--porcelain'])
        lines.append(f'{label}: {path} @ {head} '
                     f'(expected {sha}, clean={not status})')
    code, head, _ = run(['git', '-C', str(FIXTURE / 'repo'), 'rev-parse', 'HEAD'])
    code, remote, _ = run(['git', '-C', str(FIXTURE / 'repo'), 'remote', 'get-url',
                           'origin'])
    lines += [
        f'fixture_repo: {FIXTURE / "repo"} @ {head}',
        f'fixture_remote: {remote}',
        'fixture_record_sha256: '
        '4ca8ec5d7a0026846061250996ff6b38a915534dc9ccfa0180d143618db3eb30',
        f'pr_head: {PR_HEAD}',
        'task_card_sha256: '
        '81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0',
        'wsl (from ac1b_environment.txt):',
        *[f'  {line}' for line in ac1b_env.splitlines()],
    ]
    write('environment.txt', '\n'.join(lines))

    sections = []
    for title, args in (
            ('diffstat 73be8e3..8506dd4', ['diff', '--stat', BASE_SHA, CAND_SHA]),
            ('name-status 73be8e3..8506dd4',
             ['diff', '--name-status', BASE_SHA, CAND_SHA]),
            ('diffstat 14cc8fc..8506dd4',
             ['diff', '--stat', PREV_SHA, CAND_SHA]),
            ('name-status 14cc8fc..8506dd4',
             ['diff', '--name-status', PREV_SHA, CAND_SHA]),
            ('summary -M 14cc8fc..8506dd4',
             ['diff', '--summary', '-M', PREV_SHA, CAND_SHA]),
            ('name-status 8506dd4..8f7a63e',
             ['diff', '--name-status', CAND_SHA, PR_HEAD]),
            ('authority.py diff 73be8e3..8506dd4',
             ['diff', BASE_SHA, CAND_SHA, '--', 'project_memory/authority.py']),
            ('deleted files 73be8e3..8506dd4',
             ['diff', '--diff-filter=D', '--name-only', BASE_SHA, CAND_SHA]),
            ('candidate worktree status',
             ['-C', str(CANDIDATE), 'status', '--porcelain'])):
        code, out, err = git(*args)
        sections.append(f'=== {title} (exit {code}) ===\n'
                        + (out or '(empty)')
                        + (f'\n[stderr]\n{err}' if err else ''))
    write('diffstat.txt', '\n\n'.join(sections))

    raw = (FIXTURE / 'goal-evidence-result.json').read_bytes()
    text = raw.decode('utf-16')
    start = text.find('{')
    expected, _ = json.JSONDecoder().raw_decode(text[start:])
    actual = json.loads((EV / 'ac1b_goal_evidence.json').read_text(encoding='utf-8'))
    fields = ['kind', 'goal_id', 'criterion', 'schema_version']
    compare = {field: {'actual': actual.get(field),
                       'expected': expected.get(field),
                       'ok': actual.get(field) == expected.get(field)}
               for field in fields}
    exit_code = int((EV / 'ac1b_exit_code.txt').read_text().strip())
    stderr_size = (EV / 'ac1b_stderr.txt').stat().st_size
    before = (EV / 'ac1b_record_hash_before.txt').read_text(encoding='utf-8')
    after = (EV / 'ac1b_record_hashes_after.txt').read_text(encoding='utf-8')
    record_before = before.split()[0]
    record_after = after.splitlines()[0].split()[0]
    payload = {
        'run_id': EV.name,
        'command': ('wsl -u zmj: python3 -m project_memory goal evidence '
                    '--repo . --id G-B0 --criterion C1 --kind verification '
                    '--ref VER-B0-XP'),
        'cwd': '/tmp/pm03-ac1b-run/repo-copy (copy of the fixture; WSL uid 1000)',
        'env': {'PROJECT_MEMORY_TRUST_ANCHOR':
                '/etc/pm-rc3-review/anchor-a.json',
                'PYTHONPATH': ('/mnt/c/Documents/02_Research/Code/'
                               'project-memory-verification-lab/import-workspace/'
                               'pm-pilot-03/.pilot/candidate'),
                'PYTHONDONTWRITEBYTECODE': '1'},
        'exit_code': exit_code,
        'stderr_bytes': stderr_size,
        'fields': compare,
        'goal_status_after': (actual.get('goal') or {}).get('status'),
        'record_sha256_before': record_before,
        'record_sha256_after': record_after,
        'record_unchanged': record_before == record_after,
        'ok': (exit_code == 0 and stderr_size == 0
               and all(item['ok'] for item in compare.values())
               and record_before == record_after),
    }
    write('ac1b_compare.json',
          json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({'ok': payload['ok'], 'fields': compare,
                      'exit_code': exit_code, 'stderr_bytes': stderr_size,
                      'record_unchanged': payload['record_unchanged']},
                     ensure_ascii=False, indent=2))
    return 0 if payload['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
