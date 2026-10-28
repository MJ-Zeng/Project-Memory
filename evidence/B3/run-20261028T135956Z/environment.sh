#!/usr/bin/env bash
set +e
RUN="C:/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02/evidence/B3/run-20261028T135956Z"
cd "C:/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02" || exit 1
{
  echo "collected_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host_os=Windows 10.0.26300 x64 (Git Bash)"
  echo "repo=git@github.com:MJ-Zeng/Project-Memory.git"
  echo "baseline_832f271=$(git rev-parse 832f271)"
  echo "branch=$(git rev-parse --abbrev-ref HEAD)"
  echo "head=$(git rev-parse HEAD)"
  echo "windows_python=$(C:/SoftWare/Anconda/python.exe --version 2>&1)"
  echo "pytest=$(C:/SoftWare/Anconda/python.exe -m pytest --version 2>&1 | tr '\n' ' ')"
  echo "git=$(git --version)"
  echo "task_card_sha256=$(sha256sum tasks/B3.md | cut -d' ' -f1)"
  echo "--- WSL ---"
  wsl.exe -d Ubuntu -- bash -lc 'echo "wsl_distro=$(lsb_release -ds 2>/dev/null || echo Ubuntu)"; echo "wsl_python=$(python3 --version 2>&1)"; echo "wsl_git=$(git --version)"' 2>&1 | tr -d '\000'
  wsl.exe -d Ubuntu -- bash -lc 'python3 - <<PY
import json, hashlib
p = "/etc/pm-rc3-review/anchor-a.json"
raw = open(p, "rb").read()
d = json.loads(raw)
print("anchor_a_path=" + p)
print("anchor_a_sha256=" + hashlib.sha256(raw).hexdigest())
print("anchor_a_id=" + str(d.get("anchor_id")))
print("anchor_a_issuer=" + str(d.get("issuer")))
print("anchor_a_algorithm=" + str(d.get("algorithm")))
PY' 2>&1 | tr -d '\000'
  echo "key_a_read=no (never opened; only public anchor-a.json metadata)"
} > "$RUN/environment.txt"
cat "$RUN/environment.txt"
