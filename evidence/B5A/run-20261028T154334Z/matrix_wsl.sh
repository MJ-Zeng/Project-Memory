#!/bin/bash
# B5A WSL matrix: baseline checkout vs candidate branch, shadow fixtures (read-only).
set -u
REPO=/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02
FIX=/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b5a
OUT=/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02/evidence/B5A/run-20261028T154334Z
BASE_SRC=/mnt/c/Users/ZMJ/AppData/Local/Temp/b5a-base-gb
CWD_SH=/tmp/b5a-cwd
mkdir -p "$OUT/baseline" "$OUT/candidate"
rm -rf "$CWD_SH" && cp -a "$FIX/cwd-shadow" "$CWD_SH"

run_case() {  # dir name cwd env-pythonpath cmd...
  local dir=$1 name=$2 cwd=$3 pp=$4
  shift 4
  ( cd "$cwd" && env PYTHONPATH="$pp" "$@" ) \
      >"$OUT/$dir/$name.out" 2>"$OUT/$dir/$name.err"
  echo $? >"$OUT/$dir/$name.exit"
}

# baseline (ddd9dba checkout)
run_case baseline shadow-pythonpath /tmp "$FIX/shadow" python3 -m project_memory --help
run_case baseline shadow-cwd "$CWD_SH" "" python3 -m project_memory --help
run_case baseline normal "$BASE_SRC" . python3 -m project_memory --help

# candidate (fix/b5a-module-shadowing checkout)
run_case candidate shadow-pythonpath-launcher /tmp "$FIX/shadow" python3 "$REPO/_project_memory_launcher.py" --help
run_case candidate shadow-cwd-launcher "$CWD_SH" "" python3 "$REPO/_project_memory_launcher.py" --help
run_case candidate shadow-pythonpath-guard "$REPO" "$FIX/shadow" python3 -m project_memory --help
run_case candidate shadow-pythonpath-bare /tmp "$FIX/shadow" python3 -m project_memory --help
run_case candidate normal-bare "$REPO" . python3 -m project_memory --help

# interpreter-level isolation with an explicit trusted root (runpy)
CODE="import sys; sys.path.insert(0, sys.argv[1]); sys.argv = ['project-memory'] + sys.argv[2:]; import runpy; runpy.run_module('project_memory', run_name='__main__')"
run_case candidate isolated-runpy "$CWD_SH" "$FIX/shadow" python3 -I -P -c "$CODE" "$REPO" --help

echo "matrix done"
