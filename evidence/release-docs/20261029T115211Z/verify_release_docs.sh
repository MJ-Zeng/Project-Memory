#!/usr/bin/env bash
# Reproduce the corrected README/OPERATIONS examples in a throwaway Git repo.
# Only local mode is exercised; --trusted (untrusted execution) is intentionally NOT run.
set -u

OUT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$OUT/../../.." && pwd)"
PY="C:/SoftWare/Anconda/python.exe"
CMD='"C:\SoftWare\Anconda\python.exe" -m unittest'

# Truncate the log instead of appending: tee -a can hash a half-written log.
exec 3>&1 4>&2
exec > "$OUT/verification.log" 2>&1

echo "# release-docs doc-fix verification"
echo "utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "repo_root=$REPO_ROOT"
"$PY" --version
git --version
echo

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "temp_repo=$WORK"

export PYTHONPATH="$REPO_ROOT"
cd "$WORK"
git init -q
git config user.email 'e2e@example.com'
git config user.name 'PM-02 E2E'
printf 'import unittest\n\nclass TestOk(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n' > test_ok.py
git add test_ok.py
git commit -qm 'init'
"$PY" -m project_memory init --repo . --install none > /dev/null
git add -A
git commit -qm 'project-memory init'
echo "temp_head=$(git rev-parse HEAD)"
echo

: > "$OUT/exit-codes.txt"
run_case() {
  local name="$1" outf="$2"; shift 2
  echo "----- $name"
  printf '$'; printf ' %q' "$@"; echo
  "$@" > "$OUT/$outf" 2> "$OUT/$outf.stderr"
  local rc=$?
  echo "exit=$rc"
  echo "$name exit=$rc" | tee -a "$OUT/exit-codes.txt"
  echo
  return 0
}

# M-1: old README example (no mode) is rejected.
run_case m1-old-no-mode-exit3 m1-old.json \
  "$PY" -m project_memory test-run --repo . --command "$CMD" --agent qoder

# M-1: corrected README example (local mode) runs.
run_case m1-new-local-mode m1-new.json \
  "$PY" -m project_memory test-run --repo . --command "$CMD" --agent qoder --allow-local-untrusted

# M-2: create a goal, then the old non-email value is rejected.
run_case m2-goal-create m2-goal-create.json \
  "$PY" -m project_memory goal create --repo . --id G-BAD \
  --title 'approved-by 格式验证' --outcome '文档示例可执行' --owner backend-team \
  --criterion '示例命令可执行'

run_case m2-old-human-owner-exit1 m2-old.json \
  "$PY" -m project_memory goal transition --repo . --id G-BAD --to approved \
  --approved-by 'human-owner' --reason '旧文档示例'

# M-2: corrected email value is accepted.
run_case m2-goal-create-auth m2-goal-create-auth.json \
  "$PY" -m project_memory goal create --repo . --id G-AUTH \
  --title '修复认证绕过' --outcome '未授权请求被拒绝' --owner backend-team \
  --criterion '无令牌请求返回 401'

run_case m2-new-email m2-new.json \
  "$PY" -m project_memory goal transition --repo . --id G-AUTH --to approved \
  --approved-by 'owner@example.com' --reason 'Grooming 通过'

# M-3: move G-AUTH to evaluating, then demote every criterion to optional.
run_case m3-to-active m3-active.json \
  "$PY" -m project_memory goal transition --repo . --id G-AUTH --to active
run_case m3-to-evaluating m3-evaluating.json \
  "$PY" -m project_memory goal transition --repo . --id G-AUTH --to evaluating

GOAL_JSON="$WORK/.project-memory/goals/G-AUTH.json"
"$PY" - "$GOAL_JSON" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding='utf-8') as fh:
    goal = json.load(fh)
for criterion in goal.get('success_criteria', []):
    criterion['required'] = False
with open(path, 'w', encoding='utf-8') as fh:
    json.dump(goal, fh, ensure_ascii=False, indent=2)
print('demoted criteria to required=False:', len(goal.get('success_criteria', [])))
PY
echo "exit=$?"
echo

run_case m3-evaluate-empty-required m3-evaluate.json \
  "$PY" -m project_memory goal evaluate --repo . --id G-AUTH

echo "M-3 structured fields:"
"$PY" - "$OUT/m3-evaluate.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as fh:
    data = json.load(fh)
keys = ('satisfied', 'evaluation_status', 'no_required_criteria',
        'status_problems', 'effective_status', 'status_trusted')
print(json.dumps({k: data.get(k) for k in keys}, ensure_ascii=False))
PY
echo

# M-3: achieved transition is still rejected on the vacuous required set.
run_case m3-transition-achieved-exit1 m3-transition.json \
  "$PY" -m project_memory goal transition --repo . --id G-AUTH --to achieved \
  --approved-by 'owner@example.com' --reason '空必达集合不应达成'
echo "m3-transition stderr: $(cat "$OUT/m3-transition.json.stderr")"
echo

echo "receipts:"
find "$WORK/.project-memory/receipts" -name 'EXE-*.json' -maxdepth 1 2>/dev/null | sed "s#$WORK#<temp>#"
echo

cd "$REPO_ROOT"
echo "===== pytest (full default) ====="
"$PY" -m pytest -q -p no:cacheprovider > "$OUT/pytest-default.log" 2>&1
echo "pytest exit=$?"
tail -5 "$OUT/pytest-default.log"
echo

echo "===== doc diff (working tree) ====="
git -C "$REPO_ROOT" diff --name-status
echo
echo "done"

# Stop writing the log before hashing it.
exec 1>&3 2>&4
echo "log_closed_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/verification.log"

# Python writes CRLF to redirected stdout on Windows; .gitattributes stores this
# directory as LF, so normalize before hashing or the manifest will not match a
# fresh checkout.
find "$OUT" -maxdepth 1 -type f ! -name sha256sums.txt -exec sed -i 's/\r$//' {} +

(
  cd "$OUT" || exit 1
  find . -maxdepth 1 -type f ! -name sha256sums.txt -printf '%P\0' \
    | LC_ALL=C sort -z \
    | xargs -0 -r sha256sum -b > sha256sums.txt
)

echo "===== self-check (sha256sum -c) ====="
( cd "$OUT" && sha256sum -c sha256sums.txt )
CHECK_RC=$?
echo "sha256sum -c exit=$CHECK_RC"
exit "$CHECK_RC"
