# B5B — 默认 `test-run` 不得静默执行未隔离代码

- 任务 ID：`B5B`
- 状态：`draft`（派发前冻结）
- 优先级：P0 / security
- 来源：RC3 B5（默认 `test-run` 无 OS 隔离）；B5A 完成后的同一执行隔离主题
- 基线：`dev/v1.0` 的 B5B 任务卡合并提交；精确 SHA 见 Issue
- 候选分支：`fix/b5b-test-run-isolation`
- Goal：`G-B5B`
- 依赖：B5A 已合并（`4ad3a3bd`）

## 1. 问题

`project_memory` 的 `test-run` 默认 `mode=local`：

- `run_command(..., mode='local')` 是普通子进程（`isolation.mode=none`），只有快照 + 环境清理，**没有 OS 隔离**；
- CLI 只打印一行 warning，然后照常执行；
- Agent 可以一条命令在宿主上跑任意代码；
- 收据诚实标 `local_untrusted`，但**默认路径**就是“执行不可信代码”。

`--trusted`（WSL2 namespace）存在，但默认不启用；WSL 不可用时也不该静默 fallback。

B5A 修的是“CLI 被同名包顶替”，B5B 修的是“默认执行没有隔离”。两者不是同一问题。

## 2. 目标

默认 `test-run` **不得静默执行未隔离代码**：

- 无显式选择时，拒绝执行（非零、无收据、无命令副作用）；
- 显式 `--trusted` 走 WSL2 namespace；不可用则 fail closed，**不 fallback 到 local**；
- 显式 `--allow-local-untrusted` 才允许本地执行，收据标 `local_untrusted`，保留 warning；
- 不把 local 标成 trusted，不把 warning 当隔离。

## 3. 范围

允许修改：

- `project_memory/cli.py`（`test-run` 参数与默认行为）
- `project_memory/execution.py`（模式/收据/错误；如需要）
- `tests/`、`docs/decisions/`、`docs/` 运行文档
- `evidence/B5B/`

不允许：

- 修改 B0–B5A 任务卡/判据/冻结候选；
- 删除/跳过既有测试；
- 放宽 authority/签名/来源门禁；
- 把 B4（审计防篡改）夹带进来；
- 仅改 warning/文档，默认仍执行。

## 4. 设计选项（PM-02 选一个并写 ADR）

1. **默认拒绝 + 显式二选一**
   - `test-run` 无 `--trusted`/`--allow-local-untrusted` → exit 3，不执行；
   - `--trusted` → 受保护执行；不可用 → exit 3；
   - `--allow-local-untrusted` → local，收据 `local_untrusted`。
2. **默认 trusted + fail closed**
   - 默认走 `--trusted`；WSL 不可用 → exit 3；
   - 显式 `--allow-local-untrusted` 才 fallback 到 local。
3. 1/2 的组合，但必须满足“默认不静默 local”。

ADR 要说明：为什么 warning 不够、Agent 默认行为、WSL 依赖、Windows/Linux 差异、旧脚本迁移。

## 5. 验收标准

| AC | 判据 | 方法 | 通过条件 |
|---|---|---|---|
| AC-1 | 无 flag 默认不执行 | `test-run --command ...`（无模式） | exit 3；命令未执行；无收据；无 marker |
| AC-2 | 显式 local 可执行 | `--allow-local-untrusted` | 执行；收据 `isolation.mode=none`/`local_untrusted`；warning |
| AC-3 | trusted 可用 | `--trusted` + WSL 可用 | 执行；收据 `mode=trusted`/attestation；不标 local |
| AC-4 | trusted 不可用 fail closed | 模拟 WSL 不可用 | exit 3；不 fallback 到 local；无执行 |
| AC-5 | 不收据撒谎 | 各模式收据 | `isolation.mode`/`provenance.trusted` 与实际一致 |
| AC-6 | 无静默 fallback | 代码/日志 | 任何路径都不在 trusted 失败后跑 local |
| AC-7 | 回归 | 既有 226 passed / 2 skipped + 新增 | 全绿；无删除/跳过 |
| AC-8 | B5A 不回归 | 包装器/环境清理 | 仍通过 |
| AC-9 | ADR/文档 | 模式语义、迁移、残余风险 | 与实现一致 |
| AC-10 | 证据 | 命令/退出/收据/marker/日志/哈希 | 可复现 |
| AC-11 | 独立复核 | PM-03/独立审查者 | 负例“默认执行即 FAIL” |

## 6. 防作弊判据

以下“修复”判 **FAIL**：

1. 只加 warning，默认仍执行；
2. 默认 local 但把收据标 trusted；
3. trusted 失败后静默 fallback local；
4. 删除 `--trusted` 或让它永远不可用；
5. 只改文档；
6. 删除/跳过既有测试；
7. 放宽 B5A 的入口/环境清理。

## 7. Fixtures

- `fixtures/b5b/marker-command`：写宿主 marker 的命令；
- 默认：marker 不得出现；
- `--allow-local-untrusted`：marker 出现（预期）；
- `--trusted`：若 WSL 可用，marker 在沙箱内，宿主 marker 不出现；
- 由 PM-01 生成/维护；PM-02 可自建测试夹具。

## 8. 证据包

```
evidence/B5B/<run-id>/
  README.md
  environment.txt
  commands.jsonl
  default-refused.json
  local-explicit.json
  trusted.json
  trusted-unavailable.json
  receipts/              # 收据样本（无敏感数据）
  pytest.log
  diffstat.txt
  sha256sums.txt
```

## 9. 判定语义

| 结论 | 条件 |
|---|---|
| **PASS** | AC-1..AC-11 全部满足；默认拒绝、显式 local/trusted 正确、无 fallback、226+ 测试 |
| **FAIL** | 默认仍执行；trusted 静默 fallback；收据撒谎；删测/放宽门禁 |
| **BLOCKED** | 环境/WSL/权限不可用 |
| **NOT VERIFIED** | 有 AC 未运行；整体不得记 PASS |

## 10. 不在范围

- B4 审计防篡改；
- Release/部署；
- 人类身份/审批；
- 重新设计 `trusted_exec`（只消费现有能力）。

## 11. 阅读顺序

`pilot/PILOT_CLOSEOUT.md` → `tasks/B5A.md` → 本任务卡 → `execution.py::run_command`、`cli.py::test-run`、`trusted_exec`。
