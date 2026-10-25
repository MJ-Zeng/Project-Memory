#!/usr/bin/env sh
set -eu
# 在项目根目录执行，且已运行过 project-memory init。
if [ ! -d .project-memory/tooling/project_memory ]; then
  echo '缺少 .project-memory/tooling：请先在仓库中运行 project-memory init' >&2
  exit 1
fi
PYTHONPATH=".project-memory/tooling${PYTHONPATH:+:$PYTHONPATH}" exec "${PYTHON:-python3}" -m project_memory "$@"
