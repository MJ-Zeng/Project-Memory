#!/usr/bin/env bash
set +e
RUN="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02/evidence/B3/run-20261028T135956Z"
FIX="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b2/genuine-trusted/repo"
SRC="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02"
mkdir -p "$RUN/e2e"

run_pm() {
  PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json PYTHONPATH="$SRC" \
    python3 -m project_memory "$@"
}

fresh() {
  rm -rf "$1"
  cp -a "$FIX" "$1" || exit 90
  git -C "$1" config core.autocrlf true
  git -C "$1" config core.fileMode false
  cd "$1" || exit 91
}

# --- AC-5 E2E: append a second evidence item (commit) after verification ---
fresh /tmp/b3-extra-evidence
V=.project-memory/verifications/325/VER-B2-genuine-trusted.json
sha256sum "$V" > "$RUN/e2e/evidence-change.before.sha256"
run_pm goal evidence --repo . --id G-B2 --criterion C1 --kind verification \
  --ref VER-B2-genuine-trusted > "$RUN/e2e/evidence-change.step1.out" 2> "$RUN/e2e/evidence-change.step1.err"
echo "evidence_change_step1_exit=$?"
HEAD=$(git rev-parse HEAD)
run_pm goal evidence --repo . --id G-B2 --criterion C1 --kind commit \
  --ref "$HEAD" > "$RUN/e2e/evidence-change.step2.out" 2> "$RUN/e2e/evidence-change.step2.err"
echo "evidence_change_step2_exit=$?"
sha256sum "$V" > "$RUN/e2e/evidence-change.after.sha256"
run_pm goal evaluate --repo . --id G-B2 > "$RUN/e2e/evidence-change.evaluate.out" 2> "$RUN/e2e/evidence-change.evaluate.err"
echo "evidence_change_evaluate_exit=$?"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); print("evidence_change_satisfied="+str(d["satisfied"]).lower()); print("evidence_outputs="+str([(e["kind"],e["ok"],e["satisfies"]) for e in d["criteria"][0]["evidence"]]))' "$RUN/e2e/evidence-change.evaluate.out"
cmp -s "$RUN/e2e/evidence-change.before.sha256" "$RUN/e2e/evidence-change.after.sha256" && echo "evidence_change_record_same=yes" || echo "evidence_change_record_same=NO"

# --- AC-4 E2E: change criterion statement after verification ---
fresh /tmp/b3-extra-definition
run_pm goal evidence --repo . --id G-B2 --criterion C1 --kind verification \
  --ref VER-B2-genuine-trusted > "$RUN/e2e/definition-change.step1.out" 2> "$RUN/e2e/definition-change.step1.err"
echo "definition_change_step1_exit=$?"
python3 - <<'PY'
import json
path = '.project-memory/goals/G-B2.json'
goal = json.load(open(path, encoding='utf-8'))
goal['success_criteria'][0]['statement'] = '被替换的标准'
open(path, 'w', encoding='utf-8').write(json.dumps(goal, ensure_ascii=False, indent=2))
PY
run_pm goal evaluate --repo . --id G-B2 > "$RUN/e2e/definition-change.evaluate.out" 2> "$RUN/e2e/definition-change.evaluate.err"
echo "definition_change_evaluate_exit=$?"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); print("definition_change_satisfied="+str(d["satisfied"]).lower()); print("definition_change_reason="+d["criteria"][0]["evidence"][0]["reason"])' "$RUN/e2e/definition-change.evaluate.out"
