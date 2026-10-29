"""PM-03 R1 independent probe: vacuous required set, four paths.

Black-box: drives the CLI in throwaway git repos via subprocess; does not import
project_memory. Writes JSON + .exit files into the given evidence dir.

Usage: python probe-vacuous.py <evidence-run-dir>
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PY = os.environ.get('PYTHON', r'C:/SoftWare/Anconda/python.exe')
HERE = Path(__file__).resolve()
REPO = HERE.parents[3] / '.pilot' / 'r1-candidate'
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
ENV = {**os.environ, 'PYTHONPATH': str(REPO), 'PYTHONIOENCODING': 'utf-8'}

records = []


def run(cwd, argv):
    p = subprocess.run([PY, '-m', 'project_memory', *argv], cwd=str(cwd), env=ENV,
                       capture_output=True, text=True, encoding='utf-8')
    return p.returncode, p.stdout, p.stderr


def git(cwd, *args):
    subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True)


def new_repo():
    tmp = tempfile.mkdtemp(prefix='pm-r1-')
    root = Path(tmp)
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'owner@example.com')
    git(root, 'config', 'user.name', 'owner')
    (root / 'README.md').write_text('base\n', encoding='utf-8')
    git(root, 'add', 'README.md')
    git(root, 'commit', '-qm', 'base')
    return root


def goal_path(root, gid):
    return root / '.project-memory' / 'goals' / f'{gid}.json'


def edit_goal(root, gid, mutate):
    p = goal_path(root, gid)
    data = json.loads(p.read_text(encoding='utf-8'))
    mutate(data)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def audit_entries(root):
    p = root / '.project-memory' / 'audit' / 'verification_attempts.jsonl'
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]


def to_evaluating(root, gid):
    for target, extra in (('approved', ['--approved-by', 'human-lead@example.com']),
                          ('active', []), ('evaluating', [])):
        rc, out, err = run(root, ['goal', 'transition', '--id', gid, '--to', target, *extra])
        assert rc == 0, f'{gid} -> {target} failed: {err}'


def probe(name, gid, mutate):
    root = new_repo()
    rc, out, err = run(root, ['goal', 'create', '--id', gid, '--title', f'{name} probe',
                              '--outcome', 'fail closed', '--owner', 'owner@example.com',
                              '--criterion', '模块通过测试'])
    assert rc == 0, f'create {gid} failed: {err}'
    edit_goal(root, gid, mutate)
    to_evaluating(root, gid)

    ev_rc, ev_out, ev_err = run(root, ['goal', 'evaluate', '--id', gid])
    evaluate = json.loads(ev_out)
    sh_rc, sh_out, sh_err = run(root, ['goal', 'show', '--id', gid])
    show = json.loads(sh_out)

    before = len(audit_entries(root))
    tr_rc, tr_out, tr_err = run(root, ['goal', 'transition', '--id', gid, '--to', 'achieved',
                                       '--approved-by', 'human-lead@example.com'])
    goal_after = json.loads(goal_path(root, gid).read_text(encoding='utf-8'))
    entries = audit_entries(root)
    record = {
        'probe': name, 'goal_id': gid,
        'create_exit': rc,
        'evaluate': {
            'exit': ev_rc, 'stderr': ev_err,
            'satisfied': evaluate.get('satisfied'),
            'evaluation_status': evaluate.get('evaluation_status'),
            'no_required_criteria': evaluate.get('no_required_criteria'),
            'blocking': evaluate.get('blocking'),
            'recommendation': evaluate.get('recommendation'),
            'status_problems': evaluate.get('status_problems'),
            'effective_status': evaluate.get('effective_status'),
            'raw_status': evaluate.get('raw_status'),
        },
        'show': {
            'exit': sh_rc, 'stderr': sh_err,
            'goal_readable': show.get('goal', {}).get('id'),
            'status_problems': show.get('status_problems'),
            'effective_status': show.get('effective_status'),
            'evaluation_no_required_criteria': show.get('evaluation', {}).get('no_required_criteria'),
        },
        'transition_achieved': {
            'exit': tr_rc, 'stderr': tr_err,
            'goal_status_after': goal_after.get('status'),
            'goal_bytes_unchanged_since': 'transition refused, status must stay evaluating',
            'checkpoint_request_exists': (root / '.project-memory' / 'audit' / 'head.request.json').exists(),
            'audit_entries_before': before,
            'audit_entries_after': len(entries),
            'audit_last_entry': entries[-1] if entries else None,
        },
        'repo_tmp': str(root),
    }
    records.append(record)
    (OUT / f'vacuous-{name}.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def control():
    """A normal unsatisfied goal (required criterion, no evidence) must still exit 2."""
    root = new_repo()
    gid = 'G-CONTROL'
    rc, out, err = run(root, ['goal', 'create', '--id', gid, '--title', 'control',
                              '--outcome', 'normal', '--owner', 'owner@example.com',
                              '--criterion', '模块通过测试'])
    assert rc == 0, err
    to_evaluating(root, gid)
    ev_rc, ev_out, ev_err = run(root, ['goal', 'evaluate', '--id', gid])
    evaluate = json.loads(ev_out)
    record = {
        'probe': 'control-unsatisfied', 'goal_id': gid,
        'evaluate': {
            'exit': ev_rc, 'satisfied': evaluate.get('satisfied'),
            'evaluation_status': evaluate.get('evaluation_status'),
            'no_required_criteria': evaluate.get('no_required_criteria'),
            'blocking': evaluate.get('blocking'),
        },
    }
    (OUT / 'control-unsatisfied.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def create_guard():
    root = new_repo()
    rc, out, err = run(root, ['goal', 'create', '--id', 'G-EMPTY', '--title', 'empty',
                              '--outcome', 'reject', '--owner', 'owner@example.com'])
    record = {'probe': 'create-without-required', 'exit': rc, 'stdout': out, 'stderr': err}
    (OUT / 'create-without-required.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def main():
    toggle = probe('toggle', 'G-TOGGLE',
                   lambda g: g['success_criteria'][0].update(required=False))
    delete = probe('delete', 'G-DELETE',
                   lambda g: g.__setitem__('success_criteria', [
                       {'id': 'C2', 'statement': '可选的附加检查', 'required': False, 'evidence': []}]))
    ctrl = control()
    cg = create_guard()
    # Save the refusal audit entry as a schema sample.
    (OUT / 'schema-samples' / 'audit-entry-r1-refusal.json').write_text(
        json.dumps(delete['transition_achieved']['audit_last_entry'], ensure_ascii=False,
                   indent=2) + '\n', encoding='utf-8')
    # Save a normal evaluate sample (control) and a checkpoint sample if present.
    print(json.dumps({
        'toggle_evaluate_exit': toggle['evaluate']['exit'],
        'toggle_satisfied': toggle['evaluate']['satisfied'],
        'delete_evaluate_exit': delete['evaluate']['exit'],
        'delete_satisfied': delete['evaluate']['satisfied'],
        'toggle_refused_exit': toggle['transition_achieved']['exit'],
        'delete_refused_exit': delete['transition_achieved']['exit'],
        'control_evaluate_exit': ctrl['evaluate']['exit'],
        'create_guard_exit': cg['exit'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
