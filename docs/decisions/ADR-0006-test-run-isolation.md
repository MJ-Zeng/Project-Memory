---
id: "ADR-0006"
status: "proposed"
owner: "MJ-Zeng"
related_issues: [23]
---

# ADR-0006：默认 `test-run` 不得静默执行未隔离代码（B5B）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-29
- 任务：B5B（Issue #23）
- 基线：`bb536ec1ff67a855e9207cc59de53851a0722f60`
- 影响范围：`project_memory/cli.py`（`test-run` 参数与默认行为）、`tests/test_security_b5b.py`（新增）、`tests/test_project_memory.py`（一处调用补 flag）、`docs/OPERATIONS.zh-CN.md`、`docs/ARCHITECTURE.zh-CN.md`、`fixtures/b5b/`、`evidence/B5B/`、本文档
- 不涉及：B5A 的原生包装器/环境清理、B4 审计防篡改、`authority`/签名信任模型、Goal/判据语义、`trusted_exec` 的具体隔离实现、WSL_EXE、Release

## 1. 背景：当前默认到底做了什么

`test-run` 只有两种模式，且**二者不会互相静默替换**（`execution.py`）：

| 模式 | 机制 | 收据 `isolation.mode` | `execution_provenance.kind` | `trust` |
|---|---|---|---|---|
| `local`（修复前的默认） | 普通子进程；不可变快照 + 剥离 `PYTHONPATH`/敏感名 + `PYTHONSAFEPATH`/`PYTHONNOUSERSITE` | `none` | `local_untrusted` | `local_untrusted` |
| `trusted` | `trusted_exec`：WSL2 user/mount/PID/net namespace，屏蔽宿主盘符/home/`/tmp` 等，`env -i` allowlist，沙箱内写 attestation | `wsl2-user-mount-pid-net-namespace` | `trusted_launcher` | `isolated_local_attestation` |

**修复前的实际隔离级别**：`mode=local` 对应 `isolation.mode=none`、`os_isolation=false`、`sandbox=plain-child-process`。快照与环境清理只是**降低**了路径劫持与凭据泄漏，**不是**操作系统隔离：子进程仍可读写宿主文件系统、联网、读取非敏感环境变量、启动并持久化任意进程。

**修复前的默认路径**：`cli.py` 里 `mode = 'trusted' if args.trusted else 'local'`。也就是说，Agent 只要运行 `test-run --command ...`，就会在宿主上执行任意命令，只得到一行 stderr 警告，且命令照常执行、收据照常生成。这正是 RC3 B5 的“默认执行未隔离代码”。

## 2. 为什么 warning 不够

1. **默认值即行为**：Agent 的默认调用（不带 flag）就是执行，警告不改变执行这一事实；日志里的警告不会阻止副作用。
2. **警告可被忽略/被覆盖**：Agent 常只读 stdout/JSON 结果、忽略 stderr；后续自动化也可能吞掉 stderr。
3. **与收据语义冲突**：收据诚实标 `local_untrusted`，但“默认路径”就是执行不可信代码——诚实标注不能替代“默认不执行”。
4. **trusted 不可用时的静默回退风险**：若默认走 trusted 但实现里允许回退 local，则“隔离失败→仍然执行”，比默认 local 更危险。
5. **任务卡防作弊判据**：只加 warning、默认仍执行判 **FAIL**。

结论：**默认必须不执行；执行必须是显式的人类/Agent 选择。**

## 3. 决策：默认拒绝 + 显式二选一（任务卡选项 1）

`test-run` 必须显式指定**且只能指定一种**执行模式：

- 无 `--trusted` 且无 `--allow-local-untrusted` → **拒绝**：stderr 说明原因，**exit 3**；不执行命令、不建快照、不写收据、不产生任何命令副作用（marker）。
- 同时给出两者 → **拒绝**（歧义）：stderr 说明，**exit 3**；不执行。
- `--trusted` → 走 WSL2 namespace。启动前 `wsl_available()` 预检；不可用 → **exit 3**（`status=BLOCKED`），**绝不 fallback 到 local**；不执行、不写收据。
- `--allow-local-untrusted` → 显式允许 local；保留原有 warning；收据 `isolation.mode=none`、`local_untrusted`。

这样“默认不静默 local”同时满足：默认拒绝（AC-1）、显式 local（AC-2）、trusted 可用（AC-3）、trusted 不可用 fail closed 且无回退（AC-4/AC-6）。

### 3.1 为什么选“默认拒绝”而不是“默认 trusted”

- **可预测、可审计**：默认拒绝的失败是可见的（exit 3 + 明确消息），不会在没有 WSL 的 Linux CI/容器里把每个 `test-run` 都变成 BLOCKED 的意外。
- **不与 trusted 的强假设耦合**：默认 trusted 意味着“没有 WSL 就不能跑任何执行”，把可用性完全押在一个宿主前提上；默认拒绝让调用方显式决定。
- **两种选择语义对称**：拒绝不是偏向 local，而是要求调用方表态；`--trusted` 与 `--allow-local-untrusted` 的地位对等。

### 3.2 `--trusted` 的 WSL2 前提与 fail closed

- 前提：可用的 WSL2 发行版 + `unshare --user --map-root-user --mount --pid --net` 能建立 namespace（`trusted_exec.wsl_available()` 已探测 `unshare`/`timeout`/`base64`/`sha256sum`/`stat`/`awk`/`python3` 与 namespace 建立）。
- 不可用（无 WSL、发行版缺工具、namespace 预检失败、`PROJECT_MEMORY_DISABLE_WSL=1`）→ `run_command` 在**写任何快照/日志/收据之前**抛 `PMError`；CLI 输出 `status=BLOCKED` 并 **exit 3**。
- **绝不 fallback local**：代码路径中 trusted 失败即终止，没有任何“失败后改跑 local”的分支（`execution.py` 与 `trusted_exec.py` 均如此）。测试用 `PROJECT_MEMORY_DISABLE_WSL=1` 确定性模拟不可用。

## 4. 显式 local 的责任边界

- 调用方显式传 `--allow-local-untrusted` 即表示：**理解并接受**命令在宿主上以普通子进程执行，没有 OS 隔离。
- 收据仍诚实记录 `isolation.mode=none`、`os_isolation=false`、`sandbox=plain-child-process`、`execution_provenance.kind=local_untrusted`、`trust=local_untrusted`；**不得**标成 trusted。
- 保留 stderr warning，作为运行时提醒（但安全保证来自“必须显式选择”，不是 warning）。
- **Agent 默认行为**：Agent 应按任务需要选择；对不可信代码应优先 `--trusted`，只有在明确接受宿主风险时才对 `--allow-local-untrusted`。

## 5. 库函数边界

`execution.run_command(..., mode='local')` 的**库默认保持 `local`**，因为它是内部/测试原语，被大量测试与证据探针直接调用；本轮不改变库默认，只让 **CLI 默认安全**。理由：

- 库调用方是受信内部代码（测试、探针、`coordination` 路径），不是 Agent 的默认入口；
- 改库默认会要求同步全部调用方（含冻结的历史证据探针），扩大改动面且触碰历史工件；
- 安全边界在 CLI：Agent 通过 `project-memory test-run` 触达执行，CLI 现在强制显式选择。

收据/异常语义不变：local 失败照常抛 `PMError`（CLI 由 `main` 转 exit 1）；trusted 使用侧的 `PMError` 由 `test-run` 捕获为 BLOCKED/exit 3。

## 6. 旧脚本/测试迁移

| 位置 | 现状 | 处理 |
|---|---|---|
| `tests/test_project_memory.py::test_cli_goal_run_verify_reconcile_end_to_end` | CLI `test-run` 不带模式 | 补 `--allow-local-untrusted`（本轮更新的唯一既有测试调用） |
| `tests/test_security_*.py`、`tests/test_repo_identity.py` 等 | 直接调库 `run_command(...)`，默认 local | 不改（库默认不变） |
| `evidence/B5A/*/test_run_env_probe.py` | 直接调库 `run_command(...)` | 不改（历史证据探针） |
| `pilot/kit/b1/openssl_substitution.py`、`pilot/evidence/B0/*` | 历史证据脚本，CLI `test-run` 不带模式 | 不改（冻结的历史运行产物，不重跑）；若重跑需显式加 `--allow-local-untrusted` |
| 运维文档示例 | 已用 `--trusted` | 更新说明文字：`test-run` 现在必须显式选择模式 |

## 7. 残余风险

1. **trusted 启动器被替换**：`trusted_exec` 的脚本、`wsl.exe`、发行版内的 `unshare/mount` 若被攻击者控制，隔离事实不可信——等价于整进程替换；本 ADR 不改变这一边界。
2. **WSL 内核/发行版缺陷**：namespace、tmpfs mask、`/proc` 挂载的正确性依赖 WSL2 内核与用户态；未知内核漏洞不在防护范围。
3. **宿主文件系统挂载**：trusted 屏蔽 `/mnt`、`/home`、`/root`、`/tmp`、`/var`、`/etc/ssh` 等，但若宿主额外挂载点未被覆盖，仍可能泄漏；`trusted_exec` 的 canary 检查覆盖已列明路径，不保证覆盖所有自定义挂载。
4. **Agent 误用**：Agent 可能习惯性加 `--allow-local-untrusted` 以“让命令跑起来”，使默认拒绝形同虚设；这是**流程/审查**问题，需在 Handoff/复核中检查是否滥用显式 local。
5. **attestation 非来源证明**：trusted 收据的 attestation 位于仓库内且无外部签名，只证明“曾这样声明隔离”，不证明来源可信（与 B2 结论一致）。
6. **拒绝的 JSON 形态**：默认为 stderr 文本 + exit 3，不写结构化结果文件；机器调用方须以退出码判定。若后续需要机器可读的 REFUSED 结果，属于新需求。

## 8. 与任务卡 AC 的对应

| AC | 本 ADR 对应 |
|---|---|
| AC-1 | §3 默认拒绝：exit 3、不执行、无收据、无 marker |
| AC-2 | §3/§4 `--allow-local-untrusted`：执行、`isolation.mode=none`/`local_untrusted`、保留 warning |
| AC-3 | §3.2 `--trusted` + WSL 可用：隔离执行、收据 trusted、不标 local |
| AC-4 | §3.2 trusted 不可用：exit 3、不 fallback、不执行 |
| AC-5 | §4 收据字段与实际一致（local≠trusted） |
| AC-6 | §3.2 代码无 local fallback 分支 |
| AC-7 | §6 仅更新一处既有 CLI 测试调用，不删除/跳过测试 |
| AC-8 | 不触碰 B5A 包装器/`_local_env` |
| AC-9 | 本文档 + 运维/架构文档 |
