#!/usr/bin/env bash
set +e
RUN="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02/evidence/B3/run-20261028T135956Z"
FIX="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b2"
SRC="/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02"
mkdir -p "$RUN/e2e"
printf '%-24s %-8s %-8s %-8s %-10s %-10s\n' case evidence evaluate satisfied rec_same verdict
for CASE in genuine-trusted exception forged-untrusted forged-claimed-trusted; do
  WORK="/tmp/b3-$CASE"
  rm -rf "$WORK"
  cp -a "$FIX/$CASE/repo" "$WORK" || { echo "$CASE copy failed"; continue; }
  git -C "$WORK" config core.autocrlf true
  git -C "$WORK" config core.fileMode false
  cd "$WORK" || continue
  V=".project-memory/verifications/325/VER-B2-$CASE.json"
  sha256sum "$V" > "$RUN/e2e/$CASE.before.sha256" 2>/dev/null
  PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json PYTHONPATH="$SRC" \
    python3 -m project_memory goal evidence --repo . --id G-B2 --criterion C1 \
    --kind verification --ref "VER-B2-$CASE" \
    > "$RUN/e2e/$CASE.evidence.out" 2> "$RUN/e2e/$CASE.evidence.err"
  EV=$?
  sha256sum "$V" > "$RUN/e2e/$CASE.after.sha256" 2>/dev/null
  if cmp -s "$RUN/e2e/$CASE.before.sha256" "$RUN/e2e/$CASE.after.sha256"; then SAME=yes; else SAME=NO; fi
  PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json PYTHONPATH="$SRC" \
    python3 -m project_memory goal evaluate --repo . --id G-B2 \
    > "$RUN/e2e/$CASE.evaluate.out" 2> "$RUN/e2e/$CASE.evaluate.err"
  VAL=$?
  SAT=$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1],encoding="utf-8"))["satisfied"]).lower())' "$RUN/e2e/$CASE.evaluate.out" 2>/dev/null)
  if [ "$EV" = "0" ] && [ "$SAT" = "true" ]; then VERDICT=ok
  elif [ "$EV" != "0" ] && [ "$SAT" = "false" ]; then VERDICT=rejected
  else VERDICT=CHECK; fi
  printf '%-24s %-8s %-8s %-8s %-10s %-10s\n' "$CASE" "$EV" "$VAL" "$SAT" "$SAME" "$VERDICT"
  echo "  stderr: $(tr '\n' ' ' < "$RUN/e2e/$CASE.evidence.err")" | head -c 300; echo
done
