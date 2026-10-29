# B5B 证据包 — 默认 `test-run` 不得静默执行未隔离代码

- Run ID：`run-20261029T015035Z`
- 任务：B5B（Issue #23）
- 基线：`bb536ec1ff67a855e9207cc59de53851a0722f60`
- 候选代码提交：`89a14af60a0d4fa30ded850af610ee80ad7e9915`（`fix/b5b-test-run-isolation`）
- 环境：Windows 11 10.0.26300；Python 3.12.4（`C:/SoftWare/Anconda/python.exe`）；WSL2 `Ubuntu`（Running，version 2），`trusted_exec.wsl_available() == (True, 'ok')`
- 角色：PM-02 Developer。本证据包不做 PASS/VERIFIED 判定。

## 1. 场景结果

| 场景 | 命令模式 | exit | marker/宿主 | 收据 |
|---|---|---|---|---|
| `default-refused` | 无 flag | **3** | 无 | 无（未建快照/收据） |
| `both-flags-refused` | `--trusted` + `--allow-local-untrusted` | **3** | 无 | 无 |
| `local-explicit` | `--allow-local-untrusted` | 0 | 宿主 marker 出现 | `isolation.mode=none`、`local_untrusted` |
| `trusted` | `--trusted`（沙箱写 `/tmp`） | 0 | 宿主 marker 不出现；沙箱内 `marker-written`（inner exit 0） | `isolation.mode=wsl2-user-mount-pid-net-namespace`、`trust=isolated_local_attestation` |
| `trusted-host-attempt` | `--trusted`（目标宿主路径） | 0（inner exit 1） | 宿主 marker 不出现；日志 `marker-write-failed`（`/mnt` 被屏蔽） | 同上，attestation 有效 |
| `trusted-unavailable` | `--trusted` + `PROJECT_MEMORY_DISABLE_WSL=1` | **3** | 无 | 无；`status=BLOCKED`，`fallback_to_local=false` |

修复前基线（`baseline-default-prefix`，代码 `bb536ec`）：无 flag 时 exit 0、**宿主 marker 出现**、收据 `isolation.mode=none`/`local_untrusted`，仅打印 warning——复现了 B5B 的问题。

## 2. 与 AC 的对应

| AC | 证据 |
|---|---|
| AC-1 默认不执行 | `default-refused.{out,err,exit}`、`default-refused.json`；marker 无、receipts/snapshots=0 |
| AC-2 显式 local | `local-explicit.*`、`receipts/local-explicit/`；marker 出现、`isolation.mode=none`、warning |
| AC-3 trusted 可用 | `trusted.*`、`receipts/trusted/{receipt.json,run.log,attestation.json}`；`mode=trusted`、`os_isolation=true` |
| AC-4 trusted 不可用 | `trusted-unavailable.*`；exit 3、`BLOCKED`、无 fallback、marker 无 |
| AC-5 收据不撒谎 | `local-explicit.json` vs `trusted.json`：`isolation.mode`/`provenance`/`trust` 与模式一致 |
| AC-6 无静默 fallback | `trusted-unavailable.json`（`fallback_to_local=false`）+ 代码路径（trusted 失败即 `PMError`） |
| AC-7 回归 | `pytest.log`：233 passed, 2 skipped（226 既有 + 7 新增；2 skip 为既有 Windows symlink） |
| AC-8 B5A 不回归 | `pytest.log` 中 `B5AWrapperRegression::test_wrapper_ignores_pythonpath_shadow_package` 与 `B5BTest::test_local_child_ignores_host_pythonpath` 通过；既有 `test_security_b5a.py` 全通过 |
| AC-9 ADR/文档 | `docs/decisions/ADR-0006-test-run-isolation.md`、`docs/OPERATIONS.zh-CN.md`、`docs/ARCHITECTURE.zh-CN.md` |
| AC-10 证据 | 本目录（命令/退出/收据/marker/日志/哈希） |

## 3. 目录

```
run-20261029T015035Z/
├── README.md
├── environment.txt
├── commands.jsonl
├── baseline-default.{out,err,exit}          # 修复前默认 local（执行）
├── default-executed-BASELINE.json           # 修复前完整 test-run 结果
├── default-refused.{out,err,exit,json}
├── both-flags.{out,err,exit}
├── local-explicit.{out,err,exit,json}
├── trusted.{out,err,exit,json}
├── trusted-host-attempt.{out,err,exit,json}
├── trusted-unavailable.{out,err,exit,json}
├── receipts/
│   ├── baseline-local/{receipt.json,run.log}
│   ├── local-explicit/{receipt.json,run.log}
│   ├── trusted/{receipt.json,run.log,attestation.json}
│   └── trusted-host-attempt/{receipt.json,run.log,attestation.json}
├── pytest.log
├── diffstat.txt
└── sha256sums.txt
```

## 4. 披露与限制

1. **基线收据绑定 `bb536ec`**：`receipts/baseline-local/` 是修复前代码在基线提交上执行所得，仅用于对照“默认会执行”。候选场景收据绑定 `89a14af`。
2. **沙箱内 marker 不可从宿主观测**：`trusted` 场景把 marker 写入 `/tmp/b5b-sandbox-marker`（沙箱 tmpfs）；宿主无法也不应看到它，故以“inner exit 0 + 日志 `marker-written`”证明沙箱内可写，以“宿主 marker 不存在”证明未逃逸。
3. **trusted 日志含 WSL NAT 横幅乱码**：`run.log` 的 stderr 保留了 WSL 的 UTF-16 localhost/NAT 提示（mojibake）。`trusted_exec.clean_stderr` 按前缀过滤，对该乱码形态未命中；不影响隔离结论，属于既有显示瑕疵，未在本轮修。
4. **`/mnt` 屏蔽证据**：`trusted-host-attempt` 的 inner exit=1、日志 `No such file or directory: /mnt/c/...`，说明 namespace 内 `/mnt` 为空的 tmpfs，宿主盘符不可达。
5. **未在本机验证**：Linux 原生（非 WSL）路径、无 WSL 的 CI 环境、真实攻击者控制的 WSL 内核。相关残余风险见 ADR-0006 §7。
6. **run 产物**：所有 `test-run` 会在 `.project-memory/{logs,receipts,snapshots,attest}` 产生可再生成文件；证据提交前已复制样本并清理，未提交这些运行产物。
