#!/bin/bash
# B5A console-script matrix (Windows venvs; fixtures read-only).
set -u
REPO="C:/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02"
FIX="C:/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b5a"
OUT="$REPO/evidence/B5A/run-20261028T154334Z"
BASE_SRC="/tmp/b5a-base-gb"
BASE_VENV="/tmp/b5a-win-base-venv"
CAND_VENV="/tmp/b5a-win-venv"
mkdir -p "$OUT/baseline" "$OUT/candidate"

# baseline console script (ddd9dba) in its own venv
if [ ! -x "$BASE_VENV/Scripts/project-memory.exe" ]; then
  "C:/SoftWare/Anconda/python.exe" -m venv --system-site-packages "$BASE_VENV" >/dev/null
  "$BASE_VENV/Scripts/python.exe" -m pip install --no-deps --no-build-isolation --quiet "$BASE_SRC" >/dev/null 2>&1
fi
# candidate console script, reinstalled from the committed branch
"$CAND_VENV/Scripts/python.exe" -m pip install --no-deps --no-build-isolation --quiet --force-reinstall "$REPO" >/dev/null 2>&1

run_case() {  # dir name cwd env-pythonpath exe args...
  local dir=$1 name=$2 cwd=$3 pp=$4 exe=$5
  shift 5
  ( cd "$cwd" && PYTHONPATH="$pp" "$exe" "$@" ) >"$OUT/$dir/$name.out" 2>"$OUT/$dir/$name.err"
  echo $? >"$OUT/$dir/$name.exit"
}

run_case baseline shadow-console /tmp "$FIX/shadow" "$BASE_VENV/Scripts/project-memory.exe" --help
run_case candidate shadow-console /tmp "$FIX/shadow" "$CAND_VENV/Scripts/project-memory.exe" --help
rm -rf /tmp/b5a-cwd-win && cp -a "$FIX/cwd-shadow" /tmp/b5a-cwd-win
run_case candidate shadow-console-cwd /tmp/b5a-cwd-win "" "$CAND_VENV/Scripts/project-memory.exe" --help
run_case candidate normal-console /tmp "" "$CAND_VENV/Scripts/project-memory.exe" --help

echo "console matrix done"
