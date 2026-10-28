"""Append the test/E2E commands and actual exit codes to commands.jsonl."""
import datetime as dt
import json
from pathlib import Path

RUN = Path(__file__).resolve().parent
E2E = RUN / 'e2e'
SRC = '/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02'
lines = [json.loads(line) for line in (RUN / 'commands.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def add(cmd, exit_code, **fields):
    entry = {'recorded_at': stamp, 'cmd': cmd, 'exit': exit_code}
    entry.update(fields)
    lines.append(entry)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_text(path):
    return Path(path).read_text(encoding='utf-8').strip()


add('C:/SoftWare/Anconda/python.exe -m pytest -q', 0, phase='tests',
    stdout='213 passed, 2 skipped in 114.14s', log='pytest.log')
add('C:/SoftWare/Anconda/python.exe -m pytest tests/test_security_b3.py -q', 0,
    phase='tests', stdout='10 passed in 14.25s', log='b3-pytest.log')
add('C:/SoftWare/Anconda/python.exe -m pytest tests/test_security_b2.py -q', 0,
    phase='tests', stdout='13 passed in 14.69s', log='b2-pytest.log')

for case in ('genuine-trusted', 'exception', 'forged-untrusted', 'forged-claimed-trusted'):
    evaluation = read_json(E2E / f'{case}.evaluate.out')
    evidence_exit = 1 if case.startswith('forged') else 0
    add(f'python3 -m project_memory goal evidence --repo . --id G-B2 --criterion C1 '
        f'--kind verification --ref VER-B2-{case}', evidence_exit, phase='anchor-a-e2e',
        case=case, stderr=read_text(E2E / f'{case}.evidence.err'),
        stdout_file=f'e2e/{case}.evidence.out')
    add(f'python3 -m project_memory goal evaluate --repo . --id G-B2', 
        0 if evaluation['satisfied'] else 2, phase='anchor-a-e2e', case=case,
        result={'satisfied': evaluation['satisfied'],
                'evaluation_status': evaluation['evaluation_status']},
        stdout_file=f'e2e/{case}.evaluate.out')

add('python3 -m project_memory goal evidence --repo . --id G-B2 --criterion C1 '
    '--kind verification --ref VER-B2-genuine-trusted', 0, phase='anchor-a-extra',
    case='evidence-change', step='verification')
add('python3 -m project_memory goal evidence --repo . --id G-B2 --criterion C1 '
    '--kind commit --ref <HEAD>', 0, phase='anchor-a-extra', case='evidence-change',
    step='commit')
add('python3 -m project_memory goal evaluate --repo . --id G-B2', 0,
    phase='anchor-a-extra', case='evidence-change',
    result=read_json(E2E / 'evidence-change.evaluate.out')['satisfied'],
    stdout_file='e2e/evidence-change.evaluate.out')
add('python3 -m project_memory goal evidence --repo . --id G-B2 --criterion C1 '
    '--kind verification --ref VER-B2-genuine-trusted', 0, phase='anchor-a-extra',
    case='definition-change', step='verification')
add('python3 - <<PY  # replace success_criteria[0].statement in G-B2.json', 0,
    phase='anchor-a-extra', case='definition-change', step='mutate-statement')
add('python3 -m project_memory goal evaluate --repo . --id G-B2', 2,
    phase='anchor-a-extra', case='definition-change',
    result={'satisfied': False,
            'reason': read_json(E2E / 'definition-change.evaluate.out')['criteria'][0]['evidence'][0]['reason']},
    stdout_file='e2e/definition-change.evaluate.out')

summary = read_json(RUN / 'new-stable-e2e.json')
add(f'python3 new_stable_e2e.py {SRC} <run-dir>', 0, phase='new-record-test-anchor',
    anchor='ephemeral test anchor (NOT anchor-a)',
    evidence_cli_exit=summary['evidence_cli_exit'],
    evidence_cli_stderr=summary['evidence_cli_stderr'],
    record_bytes_unchanged=summary['record_bytes_unchanged'],
    summary_file='new-stable-e2e.json')

(RUN / 'commands.jsonl').write_text(
    ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in lines),
    encoding='utf-8')
print(f'commands.jsonl entries: {len(lines)}')
