#!/usr/bin/env bash
set -euo pipefail
PACKAGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$(mktemp -d)"
trap 'rm -rf "$DEMO"' EXIT

git -C "$DEMO" init -q
git -C "$DEMO" config user.name "Demo"
git -C "$DEMO" config user.email "demo@example.invalid"
printf '# 演示仓库\n' > "$DEMO/README.md"
git -C "$DEMO" add README.md
git -C "$DEMO" commit -qm '演示基线提交'

export PYTHONPATH="$PACKAGE_ROOT"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m project_memory init --repo "$DEMO" --install both > "$DEMO/init-report.json"
"$PYTHON" -m project_memory decision --repo "$DEMO" --title '基于角色的授权' --topic auth \
  --issue 325 --owner tech-leads --rationale '保留旧角色兼容' > "$DEMO/decision.json"
"$PYTHON" -m project_memory start --repo "$DEMO" --issue-file "$PACKAGE_ROOT/examples/issue-325.json" > "$DEMO/context.json"
"$PYTHON" -m project_memory handoff --repo "$DEMO" --task 325 --agent codex --run-id demo-325 \
  --completed '单元测试草稿已写' --remaining '安全审查' --evidence 'PR #342' > "$DEMO/handoff.json"
"$PYTHON" -m project_memory finish --repo "$DEMO" --issue-file "$PACKAGE_ROOT/examples/issue-325.json" \
  --pr-file "$PACKAGE_ROOT/examples/pr-342.json" --test-evidence '示例 CI 地址' \
  --docs-impact updated --reviewed-by '审查示例' > "$DEMO/completion.json"
"$PYTHON" -m project_memory audit --repo "$DEMO" --fail-on high > "$DEMO/audit.json"
"$PYTHON" -m project_memory graph --repo "$DEMO" --output "$DEMO/graph.json" >/dev/null
"$PYTHON" -m project_memory search --repo "$DEMO" '授权' > "$DEMO/search.json"
"$PYTHON" - "$DEMO" <<'PY'
import json,sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
p=Path(sys.argv[1])
for key in ['init-report','decision','context','handoff','completion','audit','graph','search']:
    o=json.loads((p/(key+'.json')).read_text(encoding='utf-8'))
    print(key,':',o.get('kind'),o.get('recommendation',''), 'count=',len(o.get('findings',o.get('nodes',o.get('results',[])))))
print('说明：所有结果都来自离线快照。CI 与人工审批未做独立核验。')
PY
