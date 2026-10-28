#!/usr/bin/env python3
"""Assemble PM-03 B2 anchor-a E2E evidence.

Reads the captured stdout/stderr/exit files and the PM-01 result.json files,
then writes environment.txt, commands.jsonl and results.json.  No fixture is
modified; everything here is read-only against /mnt/c.
"""
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

EVID = Path(__file__).resolve().parent.parent
ROOT = Path('/mnt/c/Documents/02_Research/Code/project-memory-verification-lab')
FIX = ROOT / 'fixtures/b2'
RUNNER = ROOT / 'import-workspace/pm-pilot-03'
CAND = RUNNER / '.pilot/candidate'
ANCHOR = Path('/etc/pm-rc3-review/anchor-a.json')
CASES = ['forged-untrusted', 'forged-claimed-trusted', 'genuine-trusted',
         'exception']


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True,
                          check=True).stdout.strip()


def read(path):
    return path.read_text(encoding='utf-8')


sys.path.insert(0, str(CAND))
os.environ.setdefault('PROJECT_MEMORY_TRUST_ANCHOR', str(ANCHOR))
import project_memory                                      # noqa: E402
import project_memory.authority as authority               # noqa: E402


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


anchor_doc, anchor_why = authority.load_anchor(Path('/tmp/b2-genuine-trusted'))
st = ANCHOR.stat()
env = [
    'run_id=20261028T213532Z',
    f'captured_at={sh("date", "-Iseconds")}',
    f'uid={sh("id", "-u")} user={sh("id", "-un")}',
    f'python={sh("python3", "--version")}',
    f'git={sh("git", "--version")}',
    f'host={sh("uname", "-srm")}',
    f'anchor={ANCHOR} mode={oct(stat.S_IMODE(st.st_mode))} '
    f'owner={st.st_uid}:{st.st_gid} writable_by_runner={os.access(ANCHOR, os.W_OK)}',
    f'anchor_id={(anchor_doc or {}).get("anchor_id")} load_anchor={anchor_why}',
    f'candidate_commit={sh("git", "-C", str(RUNNER), "rev-parse", "004a35b^{commit}")}',
    f'candidate_module={project_memory.__file__}',
    f'fixture_root={FIX}',
]
for case in CASES:
    head = sh('git', '-C', str(FIX / case / 'repo'), 'rev-parse', 'HEAD')
    env.append(f'fixture_head[{case}]={head}')
for rel in ('project_memory/authority.py', 'project_memory/coordination.py',
            'project_memory/execution.py'):
    blob = subprocess.run(
        ['git', '-C', str(RUNNER), 'cat-file', 'blob', f'004a35b:{rel}'],
        capture_output=True, check=True).stdout
    env.append(f'candidate_blob_sha256[{rel}]={hashlib.sha256(blob).hexdigest()}')
(EVID / 'environment.txt').write_text('\n'.join(env) + '\n', encoding='utf-8')

summary = json.loads(read(FIX / 'summary.json'))
expected_by_case = {r['case']: r for r in summary['results']}
cmd_lines = [json.dumps({
    'step': 'probe', 'cwd': '/tmp/b2-genuine-trusted', 'uid': 1000,
    'env': {'PROJECT_MEMORY_TRUST_ANCHOR': str(ANCHOR), 'PYTHONPATH': str(CAND)},
    'argv': ['python3', '-c',
             'import project_memory; project_memory.authority.load_anchor(Path("."))'],
    'result': 'module from candidate worktree; anchor_id=anchor-rc3-a',
}, ensure_ascii=False)]

results = []
for case in CASES:
    expected = expected_by_case[case]
    exit_code = int(read(EVID / f'{case}.exit').strip())
    stdout = read(EVID / f'{case}.stdout')
    stderr = read(EVID / f'{case}.stderr')
    head = read(EVID / f'{case}.head_after').strip()
    argv = ['python3', '-m', 'project_memory', 'goal', 'evidence',
            '--repo', '.', '--id', 'G-B2', '--criterion', 'C1',
            '--kind', 'verification', '--ref', f'VER-B2-{case}']
    cmd_lines.append(json.dumps({
        'step': 'case', 'case': case, 'cwd': f'/tmp/b2-{case}', 'uid': 1000,
        'env': {'PROJECT_MEMORY_TRUST_ANCHOR': str(ANCHOR),
                'PYTHONPATH': str(CAND)},
        'argv': argv, 'exit': exit_code,
    }, ensure_ascii=False))

    gate_message = ('执行来源不可信' in stderr and '人类例外缺失' in stderr)
    accepted = (exit_code == 0 and '"kind": "goal_evidence_result"' in stdout
                and stderr.strip() == '')
    if expected['expected'] == 'reject':
        case_ok = exit_code == 1 and gate_message \
            and '找不到验证记录' not in stderr
    else:
        case_ok = accepted
    results.append({
        'case': case,
        'expected': expected['expected'],
        'head': head,
        'expected_head': expected['head'],
        'head_match': head == expected['head'],
        'exit': exit_code,
        'expected_exit': expected['goal_evidence_exit'],
        'exit_match': exit_code == expected['goal_evidence_exit'],
        'stderr': stderr,
        'gate_message': gate_message,
        'stdout_has_goal_evidence_result': '"kind": "goal_evidence_result"' in stdout,
        'case_ok': bool(case_ok),
    })

out = {
    'run_id': '20261028T213532Z',
    'reviewer': 'PM-03',
    'candidate': '004a35bd7c6b6584a9054d7b61eca88b44ec25e6',
    'anchor': str(ANCHOR),
    'anchor_id': (anchor_doc or {}).get('anchor_id'),
    'uid': int(sh('id', '-u')),
    'cases': results,
    'all_match': all(r['case_ok'] and r['head_match'] for r in results),
}
out['verdict'] = 'PASS' if out['all_match'] else 'FAIL'
(EVID / 'results.json').write_text(
    json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(EVID / 'commands.jsonl').write_text(
    '\n'.join(cmd_lines) + '\n', encoding='utf-8')
print(json.dumps({'verdict': out['verdict'],
                  'cases': {r['case']: r['case_ok'] for r in results}},
                 ensure_ascii=False))
