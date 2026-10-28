#!/bin/sh
# PM-03 independent reproduction of the four anchor-a B2 fixtures.
# Run from WSL as uid 1000 (not root): root would make the anchor writable.
set -u

REPO_WSL=/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-03
FIX=/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b2
OUT="$REPO_WSL/pilot/evidence/B2/review-e2e-20261028T213532Z"
ANCHOR=/etc/pm-rc3-review/anchor-a.json
PY="$REPO_WSL/.pilot/candidate"

uid=$(id -u)
if [ "$uid" != 1000 ]; then
    echo "FATAL: running as uid=$uid, fixtures require uid 1000" >&2
    exit 90
fi

for case in forged-untrusted forged-claimed-trusted genuine-trusted exception; do
    dst=/tmp/b2-$case
    rm -rf "$dst"
    cp -a "$FIX/$case/repo" "$dst"
    git -C "$dst" config core.autocrlf true
    git -C "$dst" config core.fileMode false
    head_before=$(git -C "$dst" rev-parse HEAD)

    cd "$dst" || exit 91
    PROJECT_MEMORY_TRUST_ANCHOR="$ANCHOR" PYTHONPATH="$PY" \
        python3 -m project_memory goal evidence \
            --repo . --id G-B2 --criterion C1 \
            --kind verification --ref "VER-B2-$case" \
            >"$OUT/$case.stdout" 2>"$OUT/$case.stderr"
    rc=$?
    cd / || exit 92
    head_after=$(git -C "$dst" rev-parse HEAD)
    printf '%s\n' "$rc" >"$OUT/$case.exit"
    printf '%s\n' "$head_before" >"$OUT/$case.head_before"
    printf '%s\n' "$head_after" >"$OUT/$case.head_after"
    printf '%s head_before=%s head_after=%s exit=%s\n' "$case" "$head_before" "$head_after" "$rc"
done
