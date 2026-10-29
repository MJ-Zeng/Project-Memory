"""Reproducible B4 evidence probe.

This script exercises the audit ledger and derived Goal status end to end and
writes machine-readable evidence.  It uses a *test-time* RSA key and an
in-process anchor stub; it never reads the production anchor private key and
never claims a production anchor-a result.

Usage:
    python probe.py <output-dir>
"""
import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from project_memory import authority, execution, trusted_exec  # noqa: E402
from project_memory.common import PMError, git_sha, sha256_file  # noqa: E402
from project_memory.coordination import (  # noqa: E402
    _audit_attempt, add_goal_evidence, attach_audit_checkpoint, audit_head,
    audit_migrate, audit_verify, create_goal, evaluate_goal, finish_run,
    goal_show, load_goal, start_run, transition_goal, verify_run)
from project_memory.execution import run_command  # noqa: E402

CRITERION = '模块通过测试'
GOAL = 'G-B4'
COMMANDS = []
ORIGINAL_LOAD_ANCHOR = authority.load_anchor


def record(cmd, code, note=''):
    COMMANDS.append({'cmd': cmd if isinstance(cmd, list) else [cmd],
                     'exit': code, 'note': note})


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args],
                            capture_output=True, text=True, encoding='utf-8')
    record(['git', '-C', str(repo), *args], result.returncode)
    return result


def new_repo(prefix):
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'b4@example.invalid')
    git(repo, 'config', 'user.name', 'B4')
    (repo / 'README.md').write_text('hello\n', encoding='utf-8')
    (repo / 'tests').mkdir()
    (repo / 'tests/test_auth.py').write_text('def test_ok():\n    assert True\n',
                                             encoding='utf-8')
    git(repo, 'add', 'README.md', 'tests/test_auth.py')
    git(repo, 'commit', '-qm', 'base')
    return repo


def make_anchor(work):
    openssl = shutil.which('openssl')
    if not openssl:
        raise SystemExit('openssl not available; cannot produce signed evidence')
    key = work / 'test-key.pem'
    public = work / 'test-key.pub.pem'
    subprocess.run([openssl, 'genpkey', '-algorithm', 'RSA',
                    '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(key)],
                   check=True, capture_output=True)
    subprocess.run([openssl, 'pkey', '-in', str(key), '-pubout', '-out', str(public)],
                   check=True, capture_output=True)
    other = work / 'other-key.pem'
    subprocess.run([openssl, 'genpkey', '-algorithm', 'RSA',
                    '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(other)],
                   check=True, capture_output=True)
    anchor = {'schema_version': '1.0', 'kind': 'project_memory_trust_anchor',
              'anchor_id': 'b4-evidence-anchor', 'issuer': 'b4-evidence-signer',
              'algorithm': 'rsa-sha256',
              'public_key_pem': public.read_text(encoding='utf-8')}
    return openssl, key, other, anchor


def use_anchor(anchor):
    authority.load_anchor = lambda repo: (dict(anchor), 'ok')


def disable_anchor():
    authority.load_anchor = lambda repo: (None, 'evidence: anchor disabled')


def restore_anchor():
    authority.load_anchor = ORIGINAL_LOAD_ANCHOR


def sign_bytes(openssl, key, payload, work, name):
    payload_file = work / f'{name}.payload'
    signature_file = work / f'{name}.sig'
    payload_file.write_bytes(payload)
    subprocess.run([openssl, 'dgst', '-sha256', '-sign', str(key),
                    '-out', str(signature_file), str(payload_file)],
                   check=True, capture_output=True)
    return signature_file


def sign_record(openssl, key, record, payload_builder, work, name):
    payload = payload_builder(record)
    signature = sign_bytes(openssl, key, payload, work, name)
    record['authority'] = {
        'status': 'trusted', 'anchor_id': 'b4-evidence-anchor',
        'issuer': 'b4-evidence-signer', 'algorithm': 'rsa-sha256',
        'signed_payload_sha256': hashlib.sha256(payload).hexdigest(),
        'signature_b64': base64.b64encode(signature.read_bytes()).decode('ascii'),
    }
    return record


def rewrite_receipt(repo, out):
    path = repo / out['path']
    out['receipt']['content_sha256'] = execution._canonical_receipt_digest(out['receipt'])
    path.write_text(json.dumps(out['receipt'], ensure_ascii=False, indent=2),
                    encoding='utf-8')


def attach_attestation(repo, out, openssl, key, work):
    ref = '.project-memory/attestations/ATT-1.json'
    out['receipt']['execution_attestation_path'] = ref
    rewrite_receipt(repo, out)
    receipt = out['receipt']
    item = {
        'schema_version': '1.0', 'kind': 'execution_attestation',
        'attestation_id': 'ATT-1', 'receipt_id': receipt['receipt_id'],
        'receipt_sha256': receipt['content_sha256'], 'commit_sha': receipt['commit_sha'],
        'tree_sha': receipt['tree_sha'], 'snapshot_id': receipt['snapshot_id'],
        'snapshot_sha256': receipt['snapshot_sha256'],
        'command_sha256': hashlib.sha256(receipt['command'].encode('utf-8')).hexdigest(),
        'launcher': 'project_memory.trusted_exec', 'launcher_mode': trusted_exec.MODE,
        'isolation': {'mode': trusted_exec.MODE, 'uid': 0, 'pid_ns_levels': 1,
                      'env_count': 5, 'network': 'isolated'},
        'created_at': '2026-01-01T00:00:00Z'}
    sign_record(openssl, key, item, authority.execution_record_payload, work, 'ATT-1')
    path = repo / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
    return out


def criterion_mapping(repo, out, base):
    receipt = out['receipt']
    return {'criteria': [{
        'criterion_id': 'C1', 'goal_id': GOAL, 'task_id': 'B4',
        'criterion_description': CRITERION, 'target_repository': str(repo),
        'target_commit_sha': base, 'evidence_id': 'EV-1', 'evidence_source': 'test',
        'evidence_command': receipt['command'], 'evidence_log': out['log'],
        'evidence_exit_code': receipt['exit_code'], 'evidence_receipt': out['path'],
        'execution_status': 'passed', 'coverage_claim': '覆盖对应标准',
        'coverage_review_status': 'confirmed',
        'independent_verifier': 'verifier-agent', 'verification_result': 'pass'}]}


def build_verified_goal(repo, base, openssl, key, work):
    create_goal(repo, GOAL, 'B4 evidence', '', 'audit integrity', 'owner@example.com',
                [CRITERION])
    out = run_command(repo, [sys.executable, '-c',
                             "import sys; print('1 passed'); sys.exit(0)"],
                      base, executed_by='evidence-harness')
    record(['run_command(local, explicit library call)', str(repo)], 0,
           'evidence-harness local execution; B5B CLI default untouched')
    attach_attestation(repo, out, openssl, key, work)
    start_run(repo, GOAL, 'B4', 'run-target', 'dev-agent', 'qodercn', 'auto',
              base_sha=base, role='executor')
    finish_run(repo, 'B4', 'run-target', ['implemented'], ['verify'], head_sha=base,
               tests=[{'command': out['receipt']['command'], 'exit_code': 0,
                       'log': out['log']}])
    start_run(repo, GOAL, 'B4', 'run-verifier', 'verifier-agent', 'qodercn',
              'verifier-model', base_sha=base, role='verifier')
    result = verify_run(repo, 'run-target', 'run-verifier', 'acceptance', 'pass',
                        'locally_observed', test_receipt=out['path'],
                        criterion_evidence=criterion_mapping(repo, out, base))
    record(['verify_run', 'acceptance'], 0)
    verification = json.loads(json.dumps(result['verification']))
    verification['status'] = 'VERIFIED'
    verification['verified'] = True
    verification['mapping_status'] = 'complete'
    for entry in verification.get('criterion_evidence', []):
        entry['evidence_matched'] = True
    verification.pop('authority', None)
    sign_record(openssl, key, verification, authority.verification_payload, work,
                verification['verification_id'])
    path = repo / '.project-memory/verifications' / str(verification['task']) \
        / f"{verification['verification_id']}.json"
    path.write_text(json.dumps(verification, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    add_goal_evidence(repo, GOAL, 'C1', 'verification', verification['verification_id'])
    return out


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')


def error_text(exc):
    return f'{type(exc).__name__}: {exc}'


def scenario_goal_status_edit(outdir):
    repo = new_repo('b4-evidence-goal-')
    create_goal(repo, 'G-EDIT', 'edit', '', 'outcome', 'owner@example.com', ['c1'])
    path = repo / '.project-memory/goals/G-EDIT.json'
    goal = json.loads(path.read_text(encoding='utf-8'))
    goal['status'] = 'achieved'
    path.write_text(json.dumps(goal, ensure_ascii=False, indent=2), encoding='utf-8')
    shown = goal_show(repo, 'G-EDIT')
    evaluation = evaluate_goal(repo, 'G-EDIT')
    write_json(outdir / 'goal-status-edit.json', {
        'scenario': 'hand edited status=achieved with no evidence/checkpoint',
        'goal_show': {'raw_status': shown['raw_status'],
                      'effective_status': shown['effective_status'],
                      'status_trusted': shown['status_trusted'],
                      'status_problems': shown['status_problems'],
                      'status_authority': shown['status_authority']},
        'evaluate': {'satisfied': evaluation['satisfied'],
                     'recorded_status': evaluation['recorded_status'],
                     'recorded_status_consistent': evaluation['recorded_status_consistent'],
                     'effective_status': evaluation['effective_status'],
                     'status_trusted': evaluation['status_trusted'],
                     'status_problems': evaluation['status_problems'],
                     'recommendation': evaluation['recommendation']},
    })
    return repo


def snapshot_audit(repo):
    root = repo / '.project-memory/audit'
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            files[str(path.relative_to(root)).replace('\\', '/')] = path.read_bytes()
    return files


def restore_audit(repo, files):
    root = repo / '.project-memory/audit'
    if root.exists():
        shutil.rmtree(root)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def scenario_chain_tamper(outdir):
    repo = new_repo('b4-evidence-chain-')
    create_goal(repo, GOAL, 'chain', '', 'outcome', 'owner@example.com', ['c1'])
    for index in range(3):
        _audit_attempt(repo, outcome='recorded', reason='evidence', n=index)
    path = repo / '.project-memory/audit/verification_attempts.jsonl'
    baseline = audit_verify(repo)
    original = snapshot_audit(repo)
    entries = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    write_json(outdir / 'chain' / 'baseline-entries.json', entries)
    write_json(outdir / 'chain' / 'baseline-verify.json', baseline)

    # delete a middle row
    path.write_text(''.join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
                            for entry in [entries[0], entries[2]]), encoding='utf-8')
    report = audit_verify(repo)
    write_json(outdir / 'tamper-delete.json', {
        'scenario': 'removed middle audit entry', 'verify': report,
        'detected': not report['valid']})
    restore_audit(repo, original)

    # rewrite a field, then rewrite and rehash only that row
    edited = json.loads(json.dumps(entries))
    edited[1]['outcome'] = 'verified'
    path.write_text(''.join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
                            for entry in edited), encoding='utf-8')
    first = audit_verify(repo)
    edited[1].pop('entry_hash', None)
    edited[1]['entry_hash'] = authority.canonical_digest(edited[1])
    path.write_text(''.join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
                            for entry in edited), encoding='utf-8')
    second = audit_verify(repo)
    write_json(outdir / 'tamper-rewrite.json', {
        'scenario': 'rewrote one audit field, then rehashed that row only',
        'without_rehash': first, 'with_rehash': second,
        'detected': (not first['valid']) and (not second['valid'])})
    restore_audit(repo, original)

    # missing and empty audit
    shutil.rmtree(repo / '.project-memory/audit')
    missing = audit_verify(repo)
    write_json(outdir / 'tamper-missing.json', {
        'scenario': 'deleted audit directory', 'verify': missing,
        'detected': not missing['valid']})
    restore_audit(repo, original)
    path.write_text('', encoding='utf-8')
    empty = audit_verify(repo)
    write_json(outdir / 'tamper-empty.json', {
        'scenario': 'truncated audit file', 'verify': empty,
        'detected': not empty['valid']})
    restore_audit(repo, original)
    return repo


def scenario_legit(outdir, openssl, key, other, anchor):
    use_anchor(anchor)
    repo = new_repo('b4-evidence-legit-')
    base = git_sha(repo)
    work = Path(tempfile.mkdtemp(prefix='b4-evidence-sign-'))
    build_verified_goal(repo, base, openssl, key, work)
    for target in ('approved', 'active', 'evaluating'):
        transition_goal(repo, GOAL, target, approved_by='lead@example.com')
    transition_goal(repo, GOAL, 'achieved', approved_by='lead@example.com')
    request = repo / '.project-memory/audit/head.request.json'
    request_bytes = request.read_bytes()
    write_json(outdir / 'chain' / 'head.request.json', json.loads(request_bytes))

    agent_attempts = []
    try:
        attach_audit_checkpoint(repo, repo / 'no-such.sig')
    except PMError as exc:
        agent_attempts.append({'case': 'missing signature file',
                               'rejected': True, 'error': error_text(exc)})
    wrong_signature = sign_bytes(openssl, other, request_bytes, work, 'wrong-key')
    try:
        attach_audit_checkpoint(repo, wrong_signature)
    except PMError as exc:
        agent_attempts.append({'case': 'signed by untrusted key',
                               'rejected': True, 'error': error_text(exc)})
    disable_anchor()
    good_signature = sign_bytes(openssl, key, request_bytes, work, 'anchor-key')
    try:
        attach_audit_checkpoint(repo, good_signature)
    except PMError as exc:
        agent_attempts.append({'case': 'no protected anchor configured',
                               'rejected': True, 'error': error_text(exc)})
    restore_anchor()
    use_anchor(anchor)
    attached = attach_audit_checkpoint(repo, good_signature)
    report = audit_verify(repo)
    shown = goal_show(repo, GOAL)
    evaluation = evaluate_goal(repo, GOAL)
    audit_root = repo / '.project-memory/audit'
    chain_dir = outdir / 'chain'
    chain_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audit_root / 'verification_attempts.jsonl',
                 chain_dir / 'verification_attempts.jsonl')
    shutil.copy2(audit_root / 'head.json', chain_dir / 'head.json')
    write_json(outdir / 'legitimate.json', {
        'scenario': 'legit transition + audit chain + externally signed checkpoint '
                    '(test RSA key; in-process anchor stub)',
        'checkpoint_request_sha256': hashlib.sha256(request_bytes).hexdigest(),
        'attach': {'trusted': attached['trusted'],
                   'chain_head': attached['chain_head'],
                   'chain_length': attached['chain_length']},
        'agent_checkpoint_attempts': agent_attempts,
        'audit_verify': report,
        'goal_show': {'effective_status': shown['effective_status'],
                      'status_trusted': shown['status_trusted'],
                      'status_problems': shown['status_problems'],
                      'status_authority': shown['status_authority']},
        'evaluate': {'satisfied': evaluation['satisfied'],
                     'effective_status': evaluation['effective_status'],
                     'status_trusted': evaluation['status_trusted'],
                     'recommendation': evaluation['recommendation']},
        'chain_head': report['head'],
        'checkpoint_chain_head': report['checkpoint']['chain_head'],
    })

    # rebuild a self-consistent chain without re-signing the checkpoint
    audit_files = snapshot_audit(repo)
    path = audit_root / 'verification_attempts.jsonl'
    rebuilt = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    rebuilt[0]['outcome'] = 'rebuilt'
    previous = '0' * 64
    for index, entry in enumerate(rebuilt, 1):
        entry.pop('entry_hash', None)
        entry['seq'] = index
        entry['prev_hash'] = previous
        entry['entry_hash'] = authority.canonical_digest(entry)
        previous = entry['entry_hash']
    path.write_text(''.join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
                            for entry in rebuilt), encoding='utf-8')
    rebuilt_report = audit_verify(repo)
    rebuilt_eval = evaluate_goal(repo, GOAL)
    write_json(outdir / 'tamper-rebuild.json', {
        'scenario': 'rebuilt an internally consistent chain without a new checkpoint',
        'verify': rebuilt_report,
        'evaluate': {'satisfied': rebuilt_eval['satisfied'],
                     'effective_status': rebuilt_eval['effective_status'],
                     'status_trusted': rebuilt_eval['status_trusted'],
                     'status_problems': rebuilt_eval['status_problems']},
        'detected': not rebuilt_report['valid'] and (
            rebuilt_eval['status_trusted'] is False)})
    restore_audit(repo, audit_files)
    return repo


def scenario_migration(outdir):
    repo = new_repo('b4-evidence-migrate-')
    create_goal(repo, GOAL, 'migrate', '', 'outcome', 'owner@example.com', ['c1'])
    path = repo / '.project-memory/audit/verification_attempts.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = [
        {'schema_version': '1.2', 'kind': 'verification_attempt',
         'timestamp': '2026-01-01T00:00:00Z', 'outcome': 'recorded', 'n': 0},
        {'schema_version': '1.2', 'kind': 'verification_attempt',
         'timestamp': '2026-01-01T00:00:01Z', 'outcome': 'rejected', 'n': 1},
    ]
    path.write_text(''.join(json.dumps(entry, ensure_ascii=False) + '\n'
                            for entry in legacy), encoding='utf-8')
    before = audit_verify(repo)
    migrated = audit_migrate(repo)
    after = audit_verify(repo)
    write_json(outdir / 'migration.json', {
        'scenario': 'legacy unchained audit lines migrated',
        'before': before, 'migration': migrated, 'after': after})
    return repo


def scenario_cli(outdir, repo):
    """CLI exit semantics on the chain-only repo."""
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    results = []
    for label, args in (
            ('verify_valid_unanchored', ['audit', 'verify', '--repo', str(repo)]),
            ('head_valid_unanchored', ['audit', 'head', '--repo', str(repo)])):
        result = subprocess.run([sys.executable, '-m', 'project_memory', *args],
                                capture_output=True, text=True, encoding='utf-8',
                                env=env, cwd=str(REPO))
        record(['python', '-m', 'project_memory', *args], result.returncode, label)
        results.append({'case': label, 'exit': result.returncode,
                        'stdout': result.stdout[:2000], 'stderr': result.stderr[:2000]})
    audit_dir = repo / '.project-memory/audit'
    saved = snapshot_audit(repo)
    shutil.rmtree(audit_dir)
    result = subprocess.run([sys.executable, '-m', 'project_memory', 'audit', 'verify',
                             '--repo', str(repo)], capture_output=True, text=True,
                            encoding='utf-8', env=env, cwd=str(REPO))
    record(['python', '-m', 'project_memory', 'audit', 'verify', '--repo', str(repo),
            '(audit missing)'], result.returncode, 'verify_invalid')
    results.append({'case': 'verify_missing', 'exit': result.returncode,
                    'stdout': result.stdout[:2000], 'stderr': result.stderr[:2000]})
    restore_audit(repo, saved)
    write_json(outdir / 'cli.json', {'scenario': 'CLI exit semantics', 'results': results})


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: probe.py <output-dir>')
    outdir = Path(sys.argv[1]).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / 'chain').mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='b4-evidence-keys-'))
    openssl, key, other, anchor = make_anchor(work)
    use_anchor(anchor)
    try:
        cli_repo = scenario_chain_tamper(outdir)
        scenario_cli(outdir, cli_repo)
        scenario_goal_status_edit(outdir)
        scenario_legit(outdir, openssl, key, other, anchor)
        scenario_migration(outdir)
    finally:
        restore_anchor()

    environment = {
        'python': sys.version,
        'executable': sys.executable,
        'platform': platform.platform(),
        'openssl': subprocess.run([openssl, 'version'], capture_output=True, text=True,
                                  encoding='utf-8').stdout.strip(),
        'repo_head': subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'],
                                    capture_output=True, text=True,
                                    encoding='utf-8').stdout.strip(),
        'anchor': 'test-time RSA key + in-process load_anchor stub',
        'production_anchor_used': False,
    }
    write_json(outdir / 'environment.json', environment)
    (outdir / 'commands.jsonl').write_text(
        ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in COMMANDS),
        encoding='utf-8')
    print(json.dumps({'output': str(outdir), 'commands': len(COMMANDS)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
