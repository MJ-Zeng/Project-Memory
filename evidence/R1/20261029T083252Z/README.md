# R1 运行证据 20261029T083252Z

本目录是 R1 发布门禁在 `fix/release-gates` 分支上的一次可复现运行记录。判定权属于 PM-03 与人类审批者；本目录只记录命令、退出码与原始输出，不下结论。

## 环境

见 [`environment.txt`](environment.txt)：Windows 10.0.26300 / Git Bash 5.3.15 / Python 3.12.4 / pytest 9.1.1 / git 2.56.0.windows.2 / OpenSSL 3.5.9（`/ucrt64/bin/openssl`）/ `core.autocrlf=true`。基准提交 `cf0da825a47e3f0f7949b1bd3e6b18d3f3af7e14`，任务卡 SHA-256 `5949420f…31f1`。

## 文件

| 文件 | 内容 |
|---|---|
| `environment.txt` | 环境、分支、基准提交、任务卡哈希、相关环境变量 |
| `commands.jsonl` | 本次运行的命令、退出码与观测结果（逐行 JSON） |
| `pytest-default.log` | 默认全量测试 |
| `pytest-require-openssl.log` | `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 全量测试 |
| `openssl-default-skip.log` | 模拟无 openssl、未开开关：跳过 |
| `openssl-required-fail.log` | 模拟无 openssl、开关开启：报错、非跳过 |
| `openssl-present-switch-off.log` | openssl 存在、未开开关：签名测试正常执行 |
| `openssl-present-switch-on.log` | openssl 存在、开关开启：签名测试正常执行 |
| `regression-b5b-b5a-b3-b4.log` | B5B/B5A/B3/B2/B4 定向回归 |
| `probe-vacuous.sh` | 空必达判据手工探针脚本（临时仓库，可重跑） |
| `evaluate-vacuous.json` / `.exit` | 唯一判据 `required=false` 时的 `goal evaluate` 输出与退出码 |
| `show-vacuous.json` / `.exit` | 同一 Goal 的 `goal show` 输出与退出码 |
| `transition-refused.json` / `.exit` | `goal transition --to achieved` 的 stderr、退出码、事后状态、审计链尾条目 |
| `create-without-required.json` / `.exit` | 无 `--criterion` 的 `goal create` 被拒绝 |
| `create.json` / `transition-*.json` / `.exit` | 探针中创建与 approved/active/evaluating 转换的原始 stdout |
| `schema-samples/` | 审计条目与 checkpoint 的真实输出样例、校验脚本与结果 |

## 复现

```bash
cd <repo>
# 全量（默认）
PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q
# 全量（要求签名测试，不允许跳过）
PROJECT_MEMORY_REQUIRE_OPENSSL=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q
# 模拟无 openssl：未开开关应跳过，开开关应报错
PATH="C:/Windows/System32" PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe \
  -m pytest -q tests/test_security_b2.py tests/test_security_b3.py tests/test_security_b4.py
PATH="C:/Windows/System32" PROJECT_MEMORY_REQUIRE_OPENSSL=1 PYTHONIOENCODING=utf-8 \
  C:/SoftWare/Anconda/python.exe -m pytest -q tests/test_security_b2.py tests/test_security_b3.py tests/test_security_b4.py
# 定向回归
PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q \
  tests/test_security_b5b.py tests/test_security_b5a.py tests/test_security_b3.py \
  tests/test_security_b2.py tests/test_security_b4.py
# 空必达探针（会覆盖本目录的探针产物；退出码打印在最后一行）
bash evidence/R1/20261029T083252Z/probe-vacuous.sh "$PWD/evidence/R1/20261029T083252Z"
# schema 对照
PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe \
  evidence/R1/20261029T083252Z/schema-samples/validate.py
```

## 观测结果

- 默认全量：`253 passed, 2 skipped`，退出码 0。
- 开关全量：`253 passed, 2 skipped`，退出码 0。本机装有 openssl，这一路不会触发缺失分支；缺失分支由下方 `PATH` 模拟覆盖。
- 无 openssl + 未开开关：`37 skipped`，退出码 0。
- 无 openssl + 开关开启：`37 errors`，退出码 1，错误消息同时包含 `openssl` 与 `PROJECT_MEMORY_REQUIRE_OPENSSL`。
- openssl 存在：b2/b3/b4 在开关关闭与开启两种设置下均为 `37 passed`，退出码 0。任务卡 AC-6 记的是「82 passed」；本仓库这三个文件实际收集 37 项（b2=13、b3=10、b4=14），82 与实测不一致，按实测记录。
- 定向回归：`57 passed`，退出码 0。
- 空必达探针：`evaluate` 退出 0 且 `satisfied=false`、`evaluation_status=insufficient_evidence`、`no_required_criteria=true`、`status_problems=['no_required_criteria']`；`show` 退出 0，`effective_status=evaluating` 且保留同一标记；`transition --to achieved` 退出 1，Goal 仍为 `evaluating`，未生成 `audit/head.request.json`，审计链新增一条 `outcome=rejected`、`reason=goal_achieved_unsatisfied`、`no_required_criteria=true` 的记录（`seq=4`）；无 `--criterion` 的 `goal create` 退出 1。
- schema 对照：5 条 B4 审计条目 + 1 条 R1 拒绝条目 + 2 条 checkpoint 全部命中 `audit-ledger.schema.json`，`0 problem(s)`，退出码 0。

## 边界与注意

- 探针在 `mktemp -d` 的一次性 git 仓库中运行，结束后删除；不涉及生产 anchor、私钥、网络或 `project-memory-mvp`。
- `schema-samples/` 中的 B4 链与 checkpoint 是从 `evidence/B4/20261029T031257Z/chain/` 原样复制的只读副本，本目录不修改 B4/B5B/B0–B4 的任何既有证据。
- 本目录所有文本文件已统一为 LF（`.gitattributes` 的 `evidence/R1/** text eol=lf`），`sha256sums.txt` 按 LF 字节计算。
- 空必达判据下 `goal evaluate` 退出 0 是 AC-1 的明确要求；普通“有必需判据但未满足”仍退出 2，由既有测试覆盖。
