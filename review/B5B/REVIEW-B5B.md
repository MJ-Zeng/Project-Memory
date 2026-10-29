# B5B 独立复核报告 — 默认 `test-run` 拒绝未隔离执行

- 审查者：PM-03 Independent Reviewer（独立会话）
- 日期：2026-10-29
- 任务：B5B（Issue #23）— 默认 `test-run` 不得静默执行未隔离代码
- 基线：`bb536ec1ff67a855e9207cc59de53851a0722f60`
- 候选：`89a14af60a0d4fa30ded850af610ee80ad7e9915`
- PR head：`78b839489e7224bf500cee5f9f1009c51929d65a`（= 候选 + 证据/Handoff 提交）
- PR：https://github.com/MJ-Zeng/Project-Memory/pull/25
- 任务卡 SHA-256：`c814858863ac0857251d7ed0ae84114a6a26ccf4ee018e372522a8ea4912ec58`（实测一致）
- 复核分支：`review/b5b-89a14af`
- 本报告是程序性独立复核，不是安全认证，也不是 v1.0 GO；合并由人类决定。

## 1. 判定

**PASS（B5B 范围内）**。

默认 `test-run` 在 `run_command` 之前拒绝（exit 3、stdout 空、无 marker、`.project-memory` 完全未创建）；双 flag 拒绝；显式 local 与 trusted 的收据与实际隔离级别一致；trusted 不可用 fail closed、无 fallback、无收据；候选测试 233 passed / 2 skipped，B5A/B2 无回归。

不构成 v1.0 GO：B3/B4/发布工程、库入口边界、attestation 来源可信等仍按原结论未完成。

## 2. 恢复事实（接手时确认）

1. 修复前 `cli.py` 为 `mode = 'trusted' if args.trusted else 'local'`：无 flag 即在宿主普通子进程执行，仅一行 stderr warning。
2. 候选采用任务卡选项 1：默认拒绝 + 显式二选一；双 flag 视为歧义同样 exit 3。
3. 候选只改 `project_memory/cli.py`（+11 行）与测试/文档/夹具；`project_memory/execution.py` 未改，库默认 `mode='local'` 保留，ADR §5 明确安全边界在 CLI。
4. trusted 走 `trusted_exec` WSL2 namespace；不可用时在写快照/收据之前抛 `PMError`，CLI 转 `status=BLOCKED` 并 exit 3，无 local fallback。
5. 基线 `bb536ec`、候选 `89a14af`、PR head `78b8394` 均可解析；候选是基线后代；任务卡哈希匹配。
6. 基线 226 passed / 2 skipped；候选 233 / 2（新增 7）；`pytest` 全仓根目录收集存在**基线已有一致**的同名探针冲突（见 F-2）。

接手分钟数：约 7 分钟（到能复述上述 6 项事实）。
必须询问的问题：无阻断性问题。唯一需要人类确认的边界是“库 `run_command(mode='local')` 继续作为内部原语、安全边界只在 CLI”是否被接受（ADR §5 已声明，本复核按该声明记录，不作为 FAIL）。
Contamination：见 §10。

## 3. AC 逐条

| AC | 判据 | 独立复核结果 | 证据 |
|---|---|---|---|
| AC-1 | 无 flag 不执行 | **PASS**：exit 3；stdout 为空；host marker 不出现；`.project-memory` 未创建（receipts/snapshots 均为 0） | `default-refused.*` |
| AC-2 | 显式 local 可执行且诚实标注 | **PASS**：exit 0；marker 写入；`isolation.mode=none`、`os_isolation=false`、`provenance.kind=local_untrusted`、`trust=local_untrusted`；stderr warning | `local-explicit.*`、`receipts/local-explicit/` |
| AC-3 | trusted 可用 | **PASS**：exit 0；沙箱内 `/tmp/b5b-sandbox-marker` 写入成功；宿主 marker 不出现；`mode=wsl2-user-mount-pid-net-namespace`、`os_isolation=true`、`trust=isolated_local_attestation`、有 attestation | `trusted.*`、`receipts/trusted/` |
| AC-4 | trusted 不可用 fail closed | **PASS**：`PROJECT_MEMORY_DISABLE_WSL=1` → exit 3；`status=BLOCKED`；`receipt=null`；marker 不出现；收据数 before=2 after=2 | `trusted-unavailable.*` |
| AC-5 | 收据不撒谎 | **PASS**：local/trusted 两套字段互不混淆，见 §5 | 两目录 receipt |
| AC-6 | 无静默 fallback | **PASS**：行为上无可达回退路径；`execution.py`/`trusted_exec.py` 仅在 docstring 提到“no fallback”，无 local 分支；CLI 仅对 trusted 的 `PMError` 做 BLOCKED 转换 | `trusted-unavailable.*` + 静态 diff |
| AC-7 | 回归全绿、无删测 | **PASS**：`tests/` 233 passed / 2 skipped；基线 226/2；测试 diff 仅新增与一处调用补 flag | `pytest.log` |
| AC-8 | B5A 不回归 | **PASS**：`test_security_b5a.py` + B5B 包装器回归 + B2 共 33 passed | 命令 `pytest-b5a-b2-b5b` |
| AC-9 | ADR/文档与实现一致 | **PASS**：ADR-0006 §3/§4/§5 与实现一致；运维/架构文档改为“必须显式选择” | `docs/` diff |
| AC-10 | 证据可复现 | **PASS**：命令、退出码、标记、收据、日志、哈希齐备 | 本 run 目录 |
| AC-11 | 独立复核负例 | **PASS**：默认执行即 FAIL 的负例未触发；默认路径实测拒绝 | 本报告 |

## 4. 场景矩阵

| 场景 | 退出码 | 宿主 marker | 新收据/快照 | 收据隔离字段 | 结论 |
|---|---|---|---|---|---|
| 默认（无 flag） | 3 | 无 | 无（目录未创建） | — | PASS |
| 双 flag | 3 | 无 | 无 | — | PASS |
| `--allow-local-untrusted` | 0 | **有**（预期） | 1 收据 + 1 快照 | `none` / `local_untrusted` | PASS |
| `--trusted`（WSL 可用） | 0（inner 0） | 无 | 1 收据 + attestation | `wsl2-...` / `os_isolation=true` | PASS |
| `--trusted` + `DISABLE_WSL=1` | 3 | 无 | 无 | `receipt=null`, `status=BLOCKED` | PASS |
| trusted 内写宿主路径 | 0（inner **1**） | 无 | 1 收据（inner 失败） | `wsl2-...`；日志 `marker-write-failed` | PASS |

trusted 宿主尝试原始日志（节选）：

```text
$ python3 marker-command.py /mnt/c/.../host-marker-trusted
[cwd=/opt/root (wsl2 namespace)]
--- stderr ---
marker-write-failed: [Errno 2] No such file or directory: '/mnt/c/.../host-marker-trusted'
[exit_code=1]
```

说明 `/mnt` 在 namespace 内被 tmpfs 遮蔽；外层 CLI exit 0 只表示“执行并记录了 inner 失败”，不是宿主写入成功。

## 5. 收据字段对照

| 字段 | 显式 local | trusted |
|---|---|---|
| `executor.mode` / 结果 `mode` | `local` | `trusted` |
| `isolation.mode` | `none` | `wsl2-user-mount-pid-net-namespace` |
| `isolation.os_isolation` | `false` | `true` |
| `isolation.sandbox` | `plain-child-process` | `wsl2-user-mount-pid-net-namespace` |
| `execution_provenance.kind` | `local_untrusted` | `trusted_launcher` |
| `execution_provenance.trusted` | `false` | `false`（attestation 在仓库内、无外部签名，沿用 B2 结论） |
| `trust` | `local_untrusted` | `isolated_local_attestation` |
| `attestation_path` | 无 | 有 |

结论：不存在把 local 标成 trusted，或把 warning 当隔离的路径。

## 6. 回归

- `pytest tests`（候选）：**233 passed, 2 skipped**，124.92s。
- `pytest tests`（基线）：**226 passed, 2 skipped**，112.93s。
- B5A + B2 + B5B 定向：**33 passed**。
- 全仓根目录 `pytest`：候选与基线**同样** exit 2，收集冲突来自 `evidence/B5A/run-20261028T154334Z` 与 `run-20261029T001414Z` 下同名 `test_run_env_probe.py`（F-2，既有问题）。因此 AC-7 以 `tests/` 套件比较，口径与开发一致。

## 7. 新发现

| ID | 严重度 | 发现 | 影响 |
|---|---|---|---|
| F-1 | LOW（证据准确性） | Handoff 与 PR 证据摘要声称 trusted 不可用输出 `fallback_to_local=false`；实际 CLI 的 `BLOCKED` payload 无该字段。该布尔来自开发自建的证据摘要，不是产品输出。 | 行为已由 marker/收据数独立验证，不影响 AC-4/AC-6；但“字段存在”的表述不准确，建议证据摘要标注“derived”。 |
| F-2 | LOW（仓库卫生，既有） | 全仓 `pytest` 因两个 B5A 证据探针同名而收集失败；基线同样失败，非 B5B 引入。 | 任务卡 §4.7 的全仓命令在基线上也不可用；建议后续用 `pytest tests` 作为回归口径，或为探针加唯一文件名。 |
| F-3 | INFO | 复核说明提到的 `fixtures/b5b/README.md` 在候选与 PR 中不存在（仅有 `marker-command.py`，文件自身有 docstring）。 | 不影响 AC；夹具契约缺一份说明。 |
| F-4 | INFO（边界） | 库 `run_command(mode='local')` 仍默认 local；程序化调用方绕过 CLI 即可本地执行。ADR §5 已声明安全边界在 CLI。 | 不是受支持入口的绕过；但边界靠约定，需人类确认接受。 |
| F-5 | INFO（既有） | trusted 的 attestation 记录宿主快照路径、位于仓库内且无外部签名。 | 只证明“声明了隔离”，不证明来源可信（与 B2 一致）。 |
| F-6 | INFO | `--allow-local-untrusted` 让 local 路径更显眼，存在被习惯性滥用的流程风险。 | ADR §7.4 已注明，属审查/流程控制。 |

无 FAIL 级新发现；未发现删除/跳过测试、放宽 authority/签名/来源门禁、trusted 静默 fallback、收据撒谎。

## 8. 残余风险 / NOT VERIFIED

- **NOT VERIFIED**：PR 描述与评论——仓库私有，无 gh/token，网页返回 404；本复核仅依据 commit、分支、任务卡、代码与自建证据。
- **NOT VERIFIED**：真实无 WSL 的 Linux/CI 主机行为；仅用 `PROJECT_MEMORY_DISABLE_WSL=1` 确定性模拟。
- **NOT VERIFIED**：自定义额外挂载点的遮蔽；沿用 `trusted_exec` 既有 canary 范围。
- 残余风险：trusted 启动器/`wsl.exe`/发行版工具被替换；WSL 内核缺陷；attestation 非来源证明；显式 local 滥用。
- 本 PASS 不覆盖 B4、Release、人类身份/审批，不构成 v1.0 GO。

## 9. 与开发自报的差异

| 开发自报 | 复核观察 |
|---|---|
| AC-1..AC-10 观察与证据 | 独立复现一致（退出码、marker、收据字段、测试数）。 |
| `fallback_to_local=false`（trusted 不可用） | CLI payload 无此字段；行为无 fallback（F-1）。 |
| `fixtures/b5b/marker-command` 由 PM-02 自建 | 存在且可用；但 `fixtures/b5b/README.md` 不存在（F-3）。 |
| 233 passed / 2 skipped | 一致（`tests/`）；全仓根目录收集失败为既有问题（F-2），开发未报告。 |
| 未改 `execution.py`、库默认 local | 一致，ADR §5 有说明。 |
| contamination: none | 本复核未发现候选触碰其他工作树/B5A 文件的迹象；diff 仅 8 个文件。 |

## 10. 污染与偏差

- 未读取开发/主管会话、终端历史或未提交文件；未使用 `project-memory-mvp` 分支。
- 复核使用 `.pilot/b5b-base`、`.pilot/b5b-candidate` 与 `.pilot/b5b-review` 三个 worktree；动态命令在仓库外的临时 git 仓库执行，候选代码仅经 `PYTHONPATH` 导入。
- 未重跑 `evidence/B5A/*`、`pilot/kit/b1/*` 等冻结历史探针。
- 自述偏差：首次显式 local 复现把 MSYS 风格 `/c/...` 路径传给 Windows Python，导致该次命令 exit 2、marker 未写入；已删除该临时仓库的 `.project-memory` 后用 Windows 绝对路径重跑。未在宿主产生预期外文件（已检查 `C:\c` 不存在）。
- WSL 启动横幅为 UTF-16 乱码并混入 trusted 日志；开发已列为既有显示瑕疵，不影响隔离结论。

## 11. 接手耗时

- 冷启动到复述 6 项事实：约 7 分钟。
- 全流程（含 trusted 复现与两次全量 pytest）：约 25 分钟。
