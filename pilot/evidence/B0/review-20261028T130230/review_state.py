"""Create the PM-03 review state for B0.1 with the base (73be8e3) tooling."""
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[4]
BASE = WORKSPACE / '.pilot' / 'base'
STATE = WORKSPACE / '.pilot' / 'review-state-b01'
SNAPSHOT = WORKSPACE / 'pilot' / 'review' / 'B0' / 'state-snapshot-b0.1'

sys.path.insert(0, str(BASE))
from project_memory.coordination import (create_goal, finish_run,  # noqa: E402
                                         start_run)

RUN = 'run-review-20261028T130230'
CRITERIA = ['F-2 跨路径 mapping 正例与负例',
            'F-3 远程身份归一化',
            'AC-1(b) 已签名 goal evidence',
            '回归与上一轮 AC 无退化']


def git(*args):
    proc = subprocess.run(['git', '-C', str(STATE), *args],
                          capture_output=True, text=True, encoding='utf-8')
    if proc.returncode != 0:
        raise SystemExit(f'git {args} failed: {proc.stdout}\n{proc.stderr}')
    return proc.stdout.strip()


def main():
    if not STATE.exists():
        STATE.mkdir(parents=True)
        git('init', '-q')
        git('config', 'user.email', 'pm03@pilot.invalid')
        git('config', 'user.name', 'PM-03 Reviewer')
        (STATE / 'README.md').write_text(
            'Independent PM-03 review state for B0.1.\n', encoding='utf-8')
        git('add', 'README.md')
        git('commit', '-qm', 'review state baseline')

    create_goal(STATE, 'G-B0-REVIEW', 'B0.1 independent review',
                'PM-03 independent session; candidate 8506dd4',
                'programmatic verdict on B0.1 remediation', 'PM-03 Reviewer',
                CRITERIA)
    start_run(STATE, 'G-B0-REVIEW', 'B0', RUN, 'pm03-reviewer', 'qoder',
              'pm03-reviewer', session_id='pm03-pilot-03-20261028T130230',
              role='verifier')
    finish_run(
        STATE, 'B0', RUN,
        completed=['F-2 cross-path mapping accepted, negatives rejected',
                   'F-3 ssh:22/scp/https identical, :2222 distinct',
                   'F-1 rename R100 with unchanged content',
                   'AC-1(b) signed goal evidence exit 0 in copied checkout',
                   'full suite 164 passed / 2 skipped',
                   'prior ACs (cross-path, cross-repo, legacy, tamper) no regression'],
        remaining=['PR #5 comment blocked: no gh/token in this environment'],
        tests=[])

    for kind, pattern in (('goals', 'goals/*.json'),
                          ('runs', 'runs/B0/*.json'),
                          ('handoffs', 'handoffs/B0/*.json')):
        for source in (STATE / '.project-memory').glob(pattern):
            target = SNAPSHOT / kind / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding='utf-8'),
                              encoding='utf-8', newline='\n')
    print(json.dumps({'state': str(STATE), 'run': RUN,
                      'snapshot': str(SNAPSHOT)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
