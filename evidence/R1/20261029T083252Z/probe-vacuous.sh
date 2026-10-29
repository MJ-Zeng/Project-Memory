#!/usr/bin/env bash
# Reproduce the R1 vacuous-goal probe.
# Usage: bash probe-vacuous.sh <evidence-run-dir>
# Creates a disposable git repo in a temp dir, builds a Goal whose only
# criterion is optional, then records evaluate/show/transition/create exits.
set -u

OUT="${1:?usage: probe-vacuous.sh <evidence-run-dir>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="${PYTHON:-C:/SoftWare/Anconda/python.exe}"
PROBE="$(mktemp -d)"
trap 'rm -rf "$PROBE"' EXIT

cd "$PROBE" || exit 1
git init -q .
git config user.email owner@example.com
git config user.name owner

pm() { PYTHONPATH="$REPO" PYTHONIOENCODING=utf-8 "$PY" -m project_memory "$@"; }

capture() { # capture <name> <args...>  -> stdout to <name>.json, exit code to <name>.exit
  local name="$1"; shift
  pm "$@" > "$OUT/$name.json" 2> "$OUT/$name.err"
  local code=$?
  printf '%s' "$code" > "$OUT/$name.exit"
  return 0
}

capture create \
  goal create --id G-R1PROBE --title "vacuous probe" --outcome "fail closed" \
  --owner owner@example.com --criterion "模块通过测试"

# Simulate an existing goal that lost its required flag (legacy/hand-edited data):
# creation itself rejects an all-optional criteria set.
PYTHONIOENCODING=utf-8 "$PY" - "$PROBE/.project-memory/goals/G-R1PROBE.json" <<'EOF'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
record = json.loads(path.read_text(encoding='utf-8'))
record['success_criteria'][0]['required'] = False
path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('required flag flipped to false in', path)
EOF

capture transition-approved goal transition --id G-R1PROBE --to approved --approved-by human-lead@example.com
capture transition-active goal transition --id G-R1PROBE --to active
capture transition-evaluating goal transition --id G-R1PROBE --to evaluating
capture evaluate-vacuous goal evaluate --id G-R1PROBE
capture show-vacuous goal show --id G-R1PROBE

# Refusal: keep the CLI stderr, exit code and post-state in one JSON record.
pm goal transition --id G-R1PROBE --to achieved --approved-by human-lead@example.com \
  > "$OUT/transition-refused.stdout" 2> "$OUT/transition-refused.stderr"
REFUSED_EXIT=$?
printf '%s' "$REFUSED_EXIT" > "$OUT/transition-refused.exit"
PYTHONIOENCODING=utf-8 "$PY" - "$PROBE" "$OUT" <<'EOF'
import json, sys
from pathlib import Path
probe, out = Path(sys.argv[1]), Path(sys.argv[2])
goal = json.loads((probe / '.project-memory/goals/G-R1PROBE.json').read_text(encoding='utf-8'))
audit = probe / '.project-memory/audit/verification_attempts.jsonl'
entries = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
record = {
    'command': 'goal transition --to achieved --approved-by human-lead@example.com',
    'exit_code': int((out / 'transition-refused.exit').read_text(encoding='utf-8')),
    'stdout': (out / 'transition-refused.stdout').read_text(encoding='utf-8'),
    'stderr': (out / 'transition-refused.stderr').read_text(encoding='utf-8'),
    'goal_status_after': goal['status'],
    'checkpoint_request_exists': (probe / '.project-memory/audit/head.request.json').exists(),
    'audit_entry_count': len(entries),
    'audit_last_entry': entries[-1] if entries else None,
}
(out / 'transition-refused.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(out / 'schema-samples/audit-entry-r1-refusal.json').write_text(
    json.dumps(entries[-1], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
EOF
rm -f "$OUT/transition-refused.stdout" "$OUT/transition-refused.stderr" "$OUT/create.err" \
      "$OUT/transition-approved.err" "$OUT/transition-active.err" \
      "$OUT/transition-evaluating.err" "$OUT/evaluate-vacuous.err" "$OUT/show-vacuous.err"

# Create with no criteria at all (AC-4 stays enforced).
pm goal create --id G-R1NOR --title "no criteria" --outcome "must be rejected" \
  --owner owner@example.com > "$OUT/create-without-required.stdout" 2> "$OUT/create-without-required.stderr"
CREATE_EXIT=$?
printf '%s' "$CREATE_EXIT" > "$OUT/create-without-required.exit"
PYTHONIOENCODING=utf-8 "$PY" - "$OUT" <<'EOF'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
record = {
    'command': 'goal create without --criterion',
    'exit_code': int((out / 'create-without-required.exit').read_text(encoding='utf-8')),
    'stdout': (out / 'create-without-required.stdout').read_text(encoding='utf-8'),
    'stderr': (out / 'create-without-required.stderr').read_text(encoding='utf-8'),
}
(out / 'create-without-required.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
EOF
rm -f "$OUT/create-without-required.stdout" "$OUT/create-without-required.stderr"

echo "probe done: evaluate=$(cat "$OUT/evaluate-vacuous.exit") show=$(cat "$OUT/show-vacuous.exit") refused=$REFUSED_EXIT create-without-required=$CREATE_EXIT"
