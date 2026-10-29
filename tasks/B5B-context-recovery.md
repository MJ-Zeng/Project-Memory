# B5B 冷启动上下文恢复

- 任务：B5B — 默认 `test-run` 不得静默执行未隔离代码
- 恢复时间：2026-10-29
- 角色：PM-02 Developer（独立会话）
- 恢复耗时：约 12 分钟

## 1. 六项事实

1. **任务与基线一致**：Issue #23 / `tasks/B5B.md`；基线 `bb536ec1ff67a855e9207cc59de53851a0722f60`（PR #24 merge）；`tasks/B5B.md` SHA-256 = `c814858863ac0857251d7ed0ae84114a6a26ccf4ee018e372522a8ea4912ec58`，与派发值一致。工作树初始干净，位于 `dev/v1.0`。
2. **当前默认行为**：`project_memory/cli.py` 的 `test-run` 用 `mode = 'trusted' if args.trusted else 'local'`——无 flag 即 local；local 分支只向 stderr 打印一行警告后照常执行。这正是 B5B 要修的“默认静默执行未隔离代码”。
3. **执行语义**：`execution.py::run_command` 中 `local` 是普通子进程（`isolation.mode='none'`、`provenance.kind='local_untrusted'`、`trust='local_untrusted'`，仅快照 + `_local_env` 环境清理）；`trusted` 委托 `trusted_exec`，在写任何快照/日志前先 `wsl_available()`，不可用即 `PMError`（无 fallback）。
4. **trusted 可用性与模拟**：`trusted_exec.wsl_available()` 本机返回 `(True, 'ok')`；`PROJECT_MEMORY_DISABLE_WSL=1` 会使其返回 `(False, ...)`，可用于 AC-4“trusted 不可用 fail closed”的确定性模拟。
5. **测试基线与环境**：`python -m pytest tests/ -q` = **226 passed, 2 skipped**（约 118s）。注意 PATH 上的 `python` 是 WindowsApps 存根（exit 49），须用 `C:\SoftWare\Anconda\python.exe`（3.12.4）。WSL2 可用。
6. **受影响的既有调用点**：唯一依赖“默认 local”的 CLI 测试是 `tests/test_project_memory.py:1754`（`test-run` 未带模式）；`docs/ARCHITECTURE.zh-CN.md:183`、`docs/OPERATIONS.zh-CN.md:116` 明确写“默认 local”。库函数 `run_command(mode='local')` 被大量内部/测试调用（`tests/*`、`pilot/`、`evidence/B5A` 探针），须保留库默认以不破坏它们。

## 2. 必须询问的问题

- 无阻塞性疑问。`fixtures/b5b/` 在本 checkout 不存在；任务卡 §7 允许“PM-02 可自建测试夹具”，故自建 `fixtures/b5b/marker-command.py` 并在证据中标注，不视为越界。
- 历史证据脚本（`pilot/kit/b1/openssl_substitution.py`、`pilot/evidence/B0/*`、`evidence/B5A/*` 探针）仍调用 CLI `test-run` 且不带模式。它们是被冻结的历史运行产物，不重跑、不修改；仅在 ADR 中记录“重跑需显式加 flag”。既有 pytest 套件中只有上述 `test_project_memory.py:1754` 需要更新。

## 3. Contamination

- none。仅操作本独立 Clone（`pm-pilot-02`）与其分支；未读取主管/审查者 Clone、会话或终端历史；未使用 `project-memory-mvp` 研究分支；未写入其他工作树。
