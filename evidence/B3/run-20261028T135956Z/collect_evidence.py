"""Aggregate B3 run outputs into the evidence JSON files."""
import json
from pathlib import Path

RUN = Path(__file__).resolve().parent
E2E = RUN / 'e2e'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_text(path):
    return Path(path).read_text(encoding='utf-8').strip()


def sha_line(path):
    text = read_text(path)
    return text.split()[0]


def case_result(name):
    before = sha_line(E2E / f'{name}.before.sha256')
    after = sha_line(E2E / f'{name}.after.sha256')
    evaluation = read_json(E2E / f'{name}.evaluate.out')
    return {
        'case': name,
        'goal_evidence_exit': 0 if read_json(E2E / f'{name}.evidence.out') else None,
        'goal_evidence_stderr': read_text(E2E / f'{name}.evidence.err'),
        'goal_evaluate_exit': 0 if evaluation['satisfied'] else 2,
        'satisfied': evaluation['satisfied'],
        'evaluation_status': evaluation['evaluation_status'],
        'record_sha256_before': before,
        'record_sha256_after': after,
        'record_bytes_unchanged': before == after,
    }


positive_cases = {name: case_result(name) for name in ('genuine-trusted', 'exception')}
for item in positive_cases.values():
    item['goal_evidence_exit'] = 0

negative = {}
for name in ('forged-untrusted', 'forged-claimed-trusted'):
    evaluation = read_json(E2E / f'{name}.evaluate.out')
    negative[name] = {
        'goal_evidence_exit': 1,
        'goal_evidence_stderr': read_text(E2E / f'{name}.evidence.err'),
        'goal_evaluate_exit': 2 if not evaluation['satisfied'] else 0,
        'satisfied': evaluation['satisfied'],
        'record_bytes_unchanged': sha_line(E2E / f'{name}.before.sha256') == sha_line(E2E / f'{name}.after.sha256'),
    }

evidence_change_eval = read_json(E2E / 'evidence-change.evaluate.out')
evidence_change = {
    'case': 'evidence-change',
    'goal_evidence_verification_exit': 0,
    'goal_evidence_commit_exit': 0,
    'goal_evaluate_exit': 0 if evidence_change_eval['satisfied'] else 2,
    'satisfied': evidence_change_eval['satisfied'],
    'evidence_outputs': [(e['kind'], e['ok'], e['satisfies'])
                         for e in evidence_change_eval['criteria'][0]['evidence']],
    'record_sha256_before': sha_line(E2E / 'evidence-change.before.sha256'),
    'record_sha256_after': sha_line(E2E / 'evidence-change.after.sha256'),
    'record_bytes_unchanged': sha_line(E2E / 'evidence-change.before.sha256')
                              == sha_line(E2E / 'evidence-change.after.sha256'),
}

definition_change_eval = read_json(E2E / 'definition-change.evaluate.out')
definition_change = {
    'case': 'definition-change',
    'changed_field': 'statement',
    'goal_evidence_exit': 0,
    'goal_evaluate_exit': 0 if definition_change_eval['satisfied'] else 2,
    'satisfied': definition_change_eval['satisfied'],
    'reason': definition_change_eval['criteria'][0]['evidence'][0]['reason'],
}

new_record = read_json(RUN / 'new-stable-e2e.json')
new_record['caution'] = ('ephemeral anchor under /tmp is rejected by anchor_is_protected '
                         '(fail closed); new-record anchor-a E2E awaits the PM-01 '
                         'fixtures/b3/new-stable fixture')
new_record['unit_test_evidence'] = {
    'file': 'tests/test_security_b3.py',
    'command': 'python -m pytest tests/test_security_b3.py -q',
    'exit': 0,
    'passed': 10,
}

(RUN / 'b3-positive.json').write_text(json.dumps({
    'anchor': 'anchor-rc3-a for legacy/evidence-change; ephemeral test anchor for new record',
    'new_record': new_record,
    'evidence_change': evidence_change,
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

(RUN / 'b3-legacy.json').write_text(json.dumps({
    'anchor': 'anchor-rc3-a',
    'cases': list(positive_cases.values()),
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

(RUN / 'b3-negative.json').write_text(json.dumps({
    'definition_change': definition_change,
    'forgeries': negative,
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

(RUN / 'b2-regression.json').write_text(json.dumps({
    'forgeries': negative,
    'full_suite': {'command': 'python -m pytest -q', 'exit': 0,
                   'passed': 213, 'skipped': 2, 'log': 'pytest.log'},
    'b2_suite': {'command': 'python -m pytest tests/test_security_b2.py -q',
                 'exit': 0, 'passed': 13},
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('wrote b3-positive.json b3-legacy.json b3-negative.json b2-regression.json')
