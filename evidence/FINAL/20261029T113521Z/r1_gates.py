"""R1 gate demonstration through the real CLI in a throwaway repo.

Covers AC-1..AC-4: a Goal whose required set is emptied by hand must fail
closed in evaluate (exit 0 but satisfied=false with no_required_criteria),
stay readable in show, be refused by transition --to achieved (with an audit
entry), and goal create must still reject goals without required criteria.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
PY = sys.executable
WORK = Path(tempfile.mkdtemp(prefix='final-r1-'))
REPO = WORK / 'repo'
REPO.mkdir()
STEPS = []


def emit(name, **data):
    record = {'step': name, **data}
    STEPS.append(record)
    print(json.dumps(record, ensure_ascii=False))


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], check=True,
                          capture_output=True, text=True, encoding='utf-8')


def cli(*argv):
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT)
    env['PYTHONUTF8'] = '1'
    env.pop('PROJECT_MEMORY_TRUST_ANCHOR', None)
    proc = subprocess.run([PY, '-m', 'project_memory', *argv, '--repo', str(REPO)],
                          cwd=str(REPO), env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=120)
    return proc


def goal_path(goal):
    return REPO / f'.project-memory/goals/{goal}.json'


def edit(goal, mutate):
    path = goal_path(goal)
    data = json.loads(path.read_text(encoding='utf-8'))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def audit_entries():
    path = REPO / '.project-memory/audit/verification_attempts.jsonl'
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip()]


def scenario(name, goal, mutate):
    create = cli('goal', 'create', '--id', goal, '--title', name, '--outcome', 'o',
                 '--owner', 'owner@example.com', '--criterion', '模块通过测试')
    edit(goal, mutate)
    evaluated = cli('goal', 'evaluate', '--id', goal)
    payload = json.loads(evaluated.stdout) if evaluated.stdout.strip() else {}
    shown = cli('goal', 'show', '--id', goal)
    shown_payload = json.loads(shown.stdout) if shown.stdout.strip() else {}
    approvals = []
    for target in ('approved', 'active', 'evaluating'):
        proc = cli('goal', 'transition', '--id', goal, '--to', target,
                   '--approved-by', 'lead@example.com')
        approvals.append({'target': target, 'exit_code': proc.returncode})
    request = REPO / '.project-memory/audit/head.request.json'
    before_request = request.exists()
    refused = cli('goal', 'transition', '--id', goal, '--to', 'achieved',
                  '--approved-by', 'lead@example.com')
    status_after = json.loads(goal_path(goal).read_text(encoding='utf-8'))['status']
    entries = audit_entries()
    last = entries[-1] if entries else {}
    emit(name,
         create_exit=create.returncode,
         evaluate_exit=evaluated.returncode,
         satisfied=payload.get('satisfied'),
         evaluation_status=payload.get('evaluation_status'),
         no_required_criteria=payload.get('no_required_criteria'),
         status_problems=payload.get('status_problems'),
         shown_effective_status=shown_payload.get('effective_status'),
         shown_problems=shown_payload.get('status_problems'),
         transitions=approvals,
         achieved_exit=refused.returncode,
         achieved_stderr=refused.stderr.strip()[:300],
         goal_status_after=status_after,
         checkpoint_request_before=before_request,
         checkpoint_request_after=request.exists(),
         audit_last_outcome=last.get('outcome'),
         audit_last_reason=last.get('reason'),
         audit_last_no_required=last.get('no_required_criteria'),
         audit_last_evaluation_status=last.get('evaluation_status'))


git('init', '-q')
git('config', 'user.email', 'r1@example.invalid')
git('config', 'user.name', 'R1')
(REPO / 'README.md').write_text('hello\n', encoding='utf-8')
git('add', 'README.md')
git('commit', '-qm', 'base')
emit('cli-init', exit_code=cli('init', '--install', 'none').returncode)

# AC-1/2/3: flip the only required criterion to optional.
def flip(goal):
    goal['success_criteria'][0]['required'] = False


scenario('flipped-required-false', 'G-FLIP', flip)

# AC-2 variant: delete the required criterion entirely.
def delete(goal):
    goal['success_criteria'] = []


scenario('deleted-required-criterion', 'G-DEL', delete)

# AC-4: create without any required criterion is still refused.
proc = cli('goal', 'create', '--id', 'G-NONE', '--title', 'none', '--outcome', 'o',
           '--owner', 'owner@example.com')
emit('create-without-any-criterion', exit_code=proc.returncode,
     stderr=proc.stderr.strip()[:300],
     created=goal_path('G-NONE').exists())

# goal create with only optional criteria cannot be expressed via --criterion
# (CLI criteria are required), so exercise the library rule directly.
sys.path.insert(0, str(ROOT))
from project_memory.common import PMError  # noqa: E402
from project_memory.coordination import create_goal  # noqa: E402

try:
    create_goal(REPO, 'G-OPT', 'optional only', '', 'o', 'owner@example.com',
                [{'id': 'C1', 'statement': 'x', 'required': False, 'evidence': []}])
    optional_only = 'CREATED (unexpected)'
except PMError as exc:
    optional_only = str(exc)
emit('create-optional-only-criterion', result=optional_only,
     created=goal_path('G-OPT').exists())

(OUT / 'r1-gates-summary.json').write_text(
    json.dumps({'temp_repo': str(REPO), 'steps': STEPS}, ensure_ascii=False, indent=2),
    encoding='utf-8')
print(f'SUMMARY_WRITTEN {OUT / "r1-gates-summary.json"}')
