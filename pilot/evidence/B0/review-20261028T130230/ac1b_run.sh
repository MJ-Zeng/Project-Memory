#!/usr/bin/env bash
# PM-03 AC-1(b): run the signed fixture's goal evidence in a fresh copy.
set -u
copy=/tmp/pm03-ac1b-run/repo-copy
out=/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-03/pilot/evidence/B0/review-20261028T130230
cd "$copy" || exit 90
export PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json
export PYTHONPATH=/mnt/c/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-03/.pilot/candidate
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
{
  echo "uid=$(id -u)"
  echo "user=$(id -un)"
  echo "python=$(python3 --version 2>&1)"
  echo "anchor=$(ls -l /etc/pm-rc3-review/anchor-a.json 2>&1)"
  echo "pythonpath=$PYTHONPATH"
  echo "copy=$copy"
  echo "head=$(git rev-parse HEAD)"
  echo "remote=$(git remote get-url origin)"
  echo "git_status=$(git status --porcelain --untracked-files=no)"
} > "$out/ac1b_environment.txt" 2>&1
git status --porcelain --untracked-files=no > "$out/ac1b_git_status_before.txt" 2>&1
python3 -m project_memory goal evidence --repo . --id G-B0 --criterion C1 \
  --kind verification --ref VER-B0-XP \
  > "$out/ac1b_goal_evidence.json" 2> "$out/ac1b_stderr.txt"
rc=$?
echo "$rc" > "$out/ac1b_exit_code.txt"
git status --porcelain --untracked-files=no > "$out/ac1b_git_status_after.txt" 2>&1
exit 0
