"""Direct AC-7 observation: does the attack chain still reach `achieved`?

The kit probe only walks the transition chain when the PATH substitution
succeeded, so after the fix `probe-after.json` stops at the evidence step and
never prints `path_achieved_exit`.  This script imports the *unmodified* kit
module (it is read, never edited) to reuse its repo fixture and its bogus
record, and then attempts the whole chain anyway, so the exit codes of the
evaluate/transition steps are observed rather than merely absent.

Runs inside WSL as root; the CLI itself runs as uid 1000 against the root anchor.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

CODE = Path(sys.argv[1]).resolve()
WORK = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
KIT = Path(sys.argv[4] if len(sys.argv) > 4 else os.environ['B1_KIT'])

spec = importlib.util.spec_from_file_location('kit_probe', KIT)
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)

results = {}


def goal_status(repo: Path) -> dict:
    record = json.loads((repo / '.project-memory/goals/G-1.json').read_text(encoding='utf-8'))
    return {'status': record.get('status'),
            'evidence': [item.get('kind') for item in record.get('evidence', [])]}


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'home').mkdir(parents=True, exist_ok=True)
    os.chown(WORK, kit.AGENT_UID, kit.AGENT_GID)
    os.chown(WORK / 'home', kit.AGENT_UID, kit.AGENT_GID)
    if kit.FAKEBIN.exists():
        subprocess.run(['rm', '-rf', str(kit.FAKEBIN)], check=True)
    kit.FAKEBIN.mkdir(parents=True)
    fake = kit.FAKEBIN / 'openssl'
    fake.write_text('#!/bin/sh\necho "Verified OK"\nexit 0\n', encoding='utf-8')
    os.chmod(kit.FAKEBIN, 0o755)
    os.chmod(fake, 0o755)
    os.chown(kit.FAKEBIN, kit.AGENT_UID, kit.AGENT_GID)
    os.chown(fake, kit.AGENT_UID, kit.AGENT_GID)

    repo, base, r0 = kit.build_case('chain')
    kit.write_record(repo, kit.bogus_record(r0, 'VER-bogus'))
    tainted = kit.env_for(path_prefix=str(kit.FAKEBIN))
    tainted['PROJECT_MEMORY_OPENSSL'] = str(fake)

    proc, rec = kit.cli('chain_goal_evidence', 'goal', 'evidence', '--repo', '.',
                        '--id', 'G-1', '--criterion', 'C1', '--kind', 'verification',
                        '--ref', 'VER-bogus', repo=repo, env=tainted)
    results['goal_evidence_exit'] = rec['exit_code']
    results['goal_evidence_stderr_tail'] = rec['stderr'][-300:]

    proc, rec = kit.cli('chain_goal_evaluate', 'goal', 'evaluate', '--repo', '.',
                        '--id', 'G-1', repo=repo, env=tainted)
    results['goal_evaluate_exit'] = rec['exit_code']
    evaluate = json.loads(rec['stdout']) if rec['stdout'].strip().startswith('{') else {}
    results['goal_satisfied'] = evaluate.get('satisfied')

    for to, extra in (('approved', ['--approved-by', 'agent@example.invalid']),
                      ('active', []), ('evaluating', []),
                      ('achieved', ['--approved-by', 'agent@example.invalid'])):
        _, rec = kit.cli('chain_transition_' + to, 'goal', 'transition', '--repo', '.',
                         '--id', 'G-1', '--to', to, *extra, repo=repo, env=tainted)
        results['transition_' + to + '_exit'] = rec['exit_code']
        if to == 'achieved':
            results['achieved_exit'] = rec['exit_code']
            results['achieved_stderr_tail'] = rec['stderr'][-300:]

    results['goal_state_after_chain'] = goal_status(repo)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'results': results, 'steps': kit.steps},
                              ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
