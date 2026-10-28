#!/usr/bin/env bash
set +e
RUN="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02/evidence/B3/run-20261028T135956Z"
FIX="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b2/genuine-trusted/repo"
SRC="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02"
rm -rf /tmp/b3-legacy
cp -a "$FIX" /tmp/b3-legacy || exit 90
git -C /tmp/b3-legacy config core.autocrlf true
git -C /tmp/b3-legacy config core.fileMode false
cd /tmp/b3-legacy || exit 91
V=".project-memory/verifications/325/VER-B2-genuine-trusted.json"
sha256sum "$V" > "$RUN/verification-before.sha256"

PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json PYTHONPATH="$SRC" \
  python3 -m project_memory goal evidence --repo . --id G-B2 --criterion C1 \
  --kind verification --ref VER-B2-genuine-trusted \
  > "$RUN/repro-goal-evidence.json" 2> "$RUN/repro-goal-evidence.err"
EVIDENCE_EXIT=$?
sha256sum "$V" > "$RUN/verification-after.sha256"

PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json PYTHONPATH="$SRC" \
  python3 -m project_memory goal evaluate --repo . --id G-B2 \
  > "$RUN/repro-goal-evaluate.json" 2> "$RUN/repro-goal-evaluate.err"
EVALUATE_EXIT=$?

echo "evidence_exit=$EVIDENCE_EXIT"
echo "evaluate_exit=$EVALUATE_EXIT"
echo "--- verification byte hash before/after ---"
cat "$RUN/verification-before.sha256" "$RUN/verification-after.sha256"
echo "--- evidence stderr ---"
cat "$RUN/repro-goal-evidence.err"
echo "--- evaluate stdout (head) ---"
head -c 1200 "$RUN/repro-goal-evaluate.json"
echo
echo "--- evaluate stderr ---"
cat "$RUN/repro-goal-evaluate.err"
