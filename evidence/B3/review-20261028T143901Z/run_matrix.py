"""B3 independent reproduction matrix (PM-03 reviewer).

Runs in WSL as uid 1000. Reads fixtures read-only; every case is copied to
/tmp. Never reads key-a.pem.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path('/mnt/c/Documents/02_Research/Code/project-memory-verification-lab')
FIX = ROOT / 'fixtures'
WS = ROOT / 'import-workspace/pm-pilot-03'
CAND = WS / '.pilot/b3-candidate'
BASE = WS / '.pilot/b3-base'
OUT = WS / 'evidence/B3/review-20261028T143901Z'
WORK = Path('/tmp/b3-review-20261028T143901Z')
ANCHOR = '/etc/pm-rc3-review/anchor-a.json'


def env_for(code: Path):
    env = dict(os.environ)
    env.update({
        'PROJECT_MEMORY_TRUST_ANCHOR': ANCHOR,
        'PYTHONPATH': str(code),
        'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONIOENCODING': 'utf-8',
    })
    return env


def copy_case(src: Path, name: str) -> Path:
    dst = WORK / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)
    subprocess.run(['git', '-C', str(dst), 'config', 'core.autocrlf', 'true'], check=True)
    subprocess.run(['git', '-C', str(dst), 'config', 'core.fileMode', 'false'], check=True)
    return dst


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_path(repo: Path, ref: str) -> Path:
    hits = list((repo / '.project-memory/verifications').rglob(ref + '.json'))
    if len(hits) != 1:
        raise SystemExit(f'record lookup for {ref} returned {hits}')
    return hits[0]


def cli(repo: Path, *args, code: Path = CAND):
    proc = subprocess.run([sys.executable, '-m', 'project_memory', *args],
                          cwd=str(repo), env=env_for(code),
                          capture_output=True, text=True, encoding='utf-8')
    return {
        'command': 'python3 -m project_memory ' + ' '.join(args),
        'cwd': str(repo),
        'pythonpath': str(code),
        'exit': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
    }


def evaluate(repo: Path, goal: str, code: Path = CAND):
    out = cli(repo, 'goal', 'evaluate', '--repo', '.', '--id', goal, code=code)
    try:
        parsed = json.loads(out['stdout'])
        out['satisfied'] = parsed.get('satisfied')
        out['evaluation_status'] = parsed.get('evaluation_status')
        out['recommendation'] = parsed.get('recommendation')
        out['blocking'] = parsed.get('blocking')
    except json.JSONDecodeError:
        out['satisfied'] = None
    return out


def py_probe(repo: Path, code: Path, snippet: str):
    proc = subprocess.run([sys.executable, '-c', snippet], cwd=str(repo),
                          env=env_for(code), capture_output=True, text=True,
                          encoding='utf-8')
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = None
    return {'exit': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr,
            'payload': payload}


PROBE = r'''
import glob, json, sys
from project_memory.coordination import _verification_current
from project_memory.authority import verification_authority
ref = sys.argv[1] if len(sys.argv) > 1 else None
paths = glob.glob('.project-memory/verifications/*/*.json')
records = [p for p in paths if ref and ref in p]
assert len(records) == 1, records
record = json.load(open(records[0], encoding='utf-8'))
print(json.dumps({
    'record': records[0],
    'current': _verification_current(__import__('pathlib').Path('.'), record),
    'authority_trusted': verification_authority(__import__('pathlib').Path('.'), record)['trusted'],
    'goal_criteria_sha256': record.get('goal_criteria_sha256'),
    'goal_criteria_legacy_sha256': record.get('goal_criteria_legacy_sha256'),
}, ensure_ascii=False))
'''


def probe(repo: Path, ref: str, code: Path = CAND):
    proc = subprocess.run([sys.executable, '-c', PROBE, ref], cwd=str(repo),
                          env=env_for(code), capture_output=True, text=True,
                          encoding='utf-8')
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = None
    return {'exit': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr,
            'payload': payload}


def edit_goal(repo: Path, goal: str, mutate_src: str):
    path = repo / '.project-memory/goals' / f'{goal}.json'
    goal_obj = json.loads(path.read_text(encoding='utf-8'))
    exec(mutate_src, {'goal': goal_obj})
    path.write_text(json.dumps(goal_obj, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    meta = {
        'candidate': subprocess.run(['git', '-C', str(CAND), 'rev-parse', 'HEAD'],
                                    capture_output=True, text=True).stdout.strip(),
        'base': subprocess.run(['git', '-C', str(BASE), 'rev-parse', 'HEAD'],
                               capture_output=True, text=True).stdout.strip(),
        'anchor': ANCHOR,
        'uid': os.getuid(),
        'python': sys.version.split()[0],
    }

    # ---------------------------------------------------------------- 4.1 new
    repo = copy_case(FIX / 'b2/new-stable/repo', 'new-stable')
    rec = record_path(repo, 'VER-B3-new-stable')
    before = sha(rec)
    evaluate_before = evaluate(repo, 'G-B3')
    evidence = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B3',
                   '--criterion', 'C1', '--kind', 'verification',
                   '--ref', 'VER-B3-new-stable')
    after = sha(rec)
    ev = evaluate(repo, 'G-B3')
    p = probe(repo, 'VER-B3-new-stable')
    results['new_record'] = {
        'evaluate_before_evidence': evaluate_before,
        'record_path': str(rec.relative_to(repo)),
        'record_sha_before': before,
        'record_sha_after': after,
        'record_bytes_unchanged': before == after,
        'evidence': evidence,
        'evaluate': ev,
        'probe_after': p,
    }

    # ------------------------------------------------- 4.1 definition change
    repo = copy_case(FIX / 'b2/definition-change/repo', 'definition-change')
    rec = record_path(repo, 'VER-B3-definition-change')
    cfg_before = sha(rec)
    evidence = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B3',
                   '--criterion', 'C1', '--kind', 'verification',
                   '--ref', 'VER-B3-definition-change')
    cfg_after = sha(rec)
    ev = evaluate(repo, 'G-B3')
    p = probe(repo, 'VER-B3-definition-change')
    results['definition_change_fixture'] = {
        'record_sha_before': cfg_before,
        'record_sha_after': cfg_after,
        'evidence': evidence,
        'evaluate': ev,
        'probe_after': p,
    }

    # ------------------------------------------------------------ 4.2 legacy
    repo = copy_case(FIX / 'b2/genuine-trusted/repo', 'legacy')
    rec = record_path(repo, 'VER-B2-genuine-trusted')
    before = sha(rec)
    evaluate_before = evaluate(repo, 'G-B2')
    evidence = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                   '--criterion', 'C1', '--kind', 'verification',
                   '--ref', 'VER-B2-genuine-trusted')
    after = sha(rec)
    ev = evaluate(repo, 'G-B2')
    p = probe(repo, 'VER-B2-genuine-trusted')
    results['legacy_b2'] = {
        'evaluate_before_evidence': evaluate_before,
        'record_sha_before': before,
        'record_sha_after': after,
        'record_bytes_unchanged': before == after,
        'evidence': evidence,
        'evaluate': ev,
        'probe_after': p,
    }

    # baseline (pre-B3) on a fresh legacy copy, for contrast
    repo = copy_case(FIX / 'b2/genuine-trusted/repo', 'legacy-baseline')
    evidence = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                   '--criterion', 'C1', '--kind', 'verification',
                   '--ref', 'VER-B2-genuine-trusted', code=BASE)
    ev = evaluate(repo, 'G-B2', code=BASE)
    results['legacy_b2_baseline'] = {'evidence': evidence, 'evaluate': ev}

    # ----------------------------------------------------------- 4.3 negative
    negative = {}

    def fresh_new(name):
        repo = copy_case(FIX / 'b2/new-stable/repo', name)
        cmd = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B3',
                  '--criterion', 'C1', '--kind', 'verification',
                  '--ref', 'VER-B3-new-stable')
        return repo, cmd

    repo, cmd = fresh_new('neg-statement')
    edit_goal(repo, 'G-B3', "goal['success_criteria'][0]['statement'] = 'changed after signing'")
    negative['statement_change'] = {
        'evidence_seed': cmd, 'probe': probe(repo, 'VER-B3-new-stable'),
        'evaluate': evaluate(repo, 'G-B3')}

    repo, cmd = fresh_new('neg-id')
    edit_goal(repo, 'G-B3', "goal['success_criteria'][0]['id'] = 'C2'")
    negative['id_change'] = {
        'evidence_seed': cmd, 'probe': probe(repo, 'VER-B3-new-stable'),
        'evaluate': evaluate(repo, 'G-B3')}

    repo, cmd = fresh_new('neg-required')
    edit_goal(repo, 'G-B3', "goal['success_criteria'][0]['required'] = False")
    negative['required_change'] = {
        'evidence_seed': cmd, 'probe': probe(repo, 'VER-B3-new-stable'),
        'evaluate': evaluate(repo, 'G-B3'),
        'note': 'single required criterion flipped off; direct digest probe is the AC-4 signal'}

    # baseline parity for the required flip (pre-existing evaluator behavior)
    repo = copy_case(FIX / 'b2/genuine-trusted/repo', 'neg-required-baseline')
    base_seed = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                    '--criterion', 'C1', '--kind', 'verification',
                    '--ref', 'VER-B2-genuine-trusted', code=BASE)
    edit_goal(repo, 'G-B2', "goal['success_criteria'][0]['required'] = False")
    negative['required_change_baseline_parity'] = {
        'evidence_seed': base_seed, 'probe': probe(repo, 'VER-B2-genuine-trusted', code=BASE),
        'evaluate': evaluate(repo, 'G-B2', code=BASE)}

    repo, cmd = fresh_new('neg-evidence-note')
    edit_goal(repo, 'G-B3',
              "goal['success_criteria'][0]['evidence'][0]['note'] = 'edited evidence note'")
    negative['evidence_note_change'] = {
        'evidence_seed': cmd, 'probe': probe(repo, 'VER-B3-new-stable'),
        'evaluate': evaluate(repo, 'G-B3')}

    repo, cmd = fresh_new('neg-evidence-append')
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    second = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B3',
                 '--criterion', 'C1', '--kind', 'commit', '--ref', head)
    negative['evidence_append_second'] = {
        'evidence_seed': cmd, 'second_evidence': second,
        'probe': probe(repo, 'VER-B3-new-stable'),
        'evaluate': evaluate(repo, 'G-B3')}

    # legacy must not accept arbitrary old records after a definition change
    repo = copy_case(FIX / 'b2/genuine-trusted/repo', 'neg-legacy-definition')
    edit_goal(repo, 'G-B2', "goal['success_criteria'][0]['statement'] = 'changed after signing'")
    negative['legacy_definition_change'] = {
        'probe': probe(repo, 'VER-B2-genuine-trusted'),
        'evidence': cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                        '--criterion', 'C1', '--kind', 'verification',
                        '--ref', 'VER-B2-genuine-trusted'),
        'evaluate': evaluate(repo, 'G-B2')}

    results['negative'] = negative

    # ------------------------------------------------- B2 gate regression E2E
    b2 = {}
    for case, ref in (('forged-untrusted', 'VER-B2-forged-untrusted'),
                      ('forged-claimed-trusted', 'VER-B2-forged-claimed-trusted')):
        repo = copy_case(FIX / f'b2/{case}/repo', case)
        b2[case] = {
            'evidence': cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                            '--criterion', 'C1', '--kind', 'verification', '--ref', ref),
            'evaluate': evaluate(repo, 'G-B2')}

    repo = copy_case(FIX / 'b2/exception/repo', 'exception')
    b2['exception_positive'] = {
        'evidence': cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                        '--criterion', 'C1', '--kind', 'verification',
                        '--ref', 'VER-B2-exception')}
    results['b2_forged'] = b2

    # binding negatives: tamper receipt / tamper record
    repo = copy_case(FIX / 'b2/genuine-trusted/repo', 'tamper-receipt')
    receipts = sorted((repo / '.project-memory/receipts').rglob('*.json'))
    target = json.loads(receipts[0].read_text(encoding='utf-8'))
    target['exit_code'] = 9
    receipts[0].write_text(json.dumps(target, ensure_ascii=False, indent=2), encoding='utf-8')
    tamper_receipt = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                         '--criterion', 'C1', '--kind', 'verification',
                         '--ref', 'VER-B2-genuine-trusted')

    repo = copy_case(FIX / 'b2/genuine-trusted/repo', 'tamper-record')
    rec = record_path(repo, 'VER-B2-genuine-trusted')
    record = json.loads(rec.read_text(encoding='utf-8'))
    record['checks']['tests']['command'] = record['checks']['tests']['command'] + ' # edited'
    rec.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    tamper_record = cli(repo, 'goal', 'evidence', '--repo', '.', '--id', 'G-B2',
                        '--criterion', 'C1', '--kind', 'verification',
                        '--ref', 'VER-B2-genuine-trusted')
    results['binding_tamper'] = {'tamper_receipt': tamper_receipt,
                                 'tamper_record': tamper_record}

    results['meta'] = meta
    (OUT / 'matrix.json').write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                     encoding='utf-8')
    print(json.dumps({'written': str(OUT / 'matrix.json')}))


if __name__ == '__main__':
    main()
