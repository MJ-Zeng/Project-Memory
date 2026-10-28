# B0 证据包 — `run-20261028T1010`

- 任务：**B0** 可移植的仓库身份，解除执行收据的绝对路径绑定
- Issue：<https://github.com/MJ-Zeng/Project-Memory/issues/3>
- 基线：`73be8e3ac4efc04c1811c122eb665344fe8ce4c3`
- 候选代码提交：`d872de11e389b67ee98acdb2ba80db7362dad464`（`fix/b0-repo-identity`）
- 任务卡 SHA-256：`81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0`
- 角色：PM-02 Developer（`pm02@pilot.invalid`）

> 本包只记录“运行的命令、观察到的退出码与输出”，**不**声明 PASS / VERIFIED。结论由 PM-03 与人类判定。

## 1. 结论摘要（观察）

| 证据 | 观察 |
|---|---|
| `pre_fix.json` | 基线代码（`73be8e3`）下，路径 A 的收据在 A 中 `valid=true`，整仓复制到 B 后 `valid=false`；`repo_id` 随路径改变。缺陷复现。 |
| `cross_path.json` | 候选代码下，同一 commit 在路径 B 中 `verify_receipt.valid=true`、`_verification_current=true`，A/B 身份相同，身份字段不含 B 的路径。 |
| `cross_repo.json` | 不同 remote（同根提交）与不同根提交（同 remote）均被拒绝（退出码 3）；`schema 1.0` 旧收据在原路径 `valid=true` 且 `legacy_path_bound=true`，复制到其他路径后被拒绝。 |
| `pytest.log` | `156 passed, 2 skipped`，退出码 0；跳过项是 Windows 上无法创建符号链接的两个平台测试（与基线相同）。 |

## 2. 环境

见 `environment.txt`：Windows 11、`C:\SoftWare\Anconda\python.exe` 3.12.4、pytest 9.1.1、git 2.56.0。证据在候选代码提交 `d872de1` 上生成；临时仓库位于 `%TEMP%`，不随本包分发。

## 3. 文件索引

| 文件 | 证明什么 | 不证明什么 |
|---|---|---|
| `pre_fix.json` | 基线行为：路径绑定导致跨路径失败 | 不证明候选实现 |
| `cross_path.json` | AC-1 正例：跨路径收据与验证记录仍有效 | 不包含需签名的 `goal evidence` 全链路 |
| `cross_repo.json` | AC-2/AC-4：不同仓库被拒绝，旧收据被标记且不跨路径 | 不证明攻击者无法复制整个仓库（按设计视为同一仓库） |
| `pytest.log` | AC-5 回归：既有 147 项（145 passed + 2 skipped）与新增 11 项全绿 | 不证明语义覆盖或安全验收 |
| `commands.jsonl` | 顶层命令、退出码、日志路径与日志 SHA-256 | 不包含 PM-03 的独立复现 |
| `logs/` | 每条命令的完整 stdout/stderr | 日志内容不代表签名或授权 |
| `diffstat.txt` | 候选相对基线的改动范围（打包时快照；`commands.jsonl` 在其后又追加了 3 条打包命令） | 不含本文件与 `sha256sums.txt` 的生成过程 |
| `scripts/` | 可重跑的驱动器与检查脚本 | 脚本本身不是证据，输出才是 |
| `sha256sums.txt` | 本目录各文件按字节的 SHA-256（文件均为 LF 换行） | 不覆盖自身 |

## 4. 复现

从候选提交重新生成（约 3 分钟，主要是全量 pytest）：

```powershell
C:\SoftWare\Anconda\python.exe pilot/evidence/B0/run-20261028T1010/scripts/run_evidence.py --run-id run-20261028T1010
# 写 README.md 后打包（diffstat + commands.jsonl 追加 + sha256sums.txt）
C:\SoftWare\Anconda\python.exe pilot/evidence/B0/run-20261028T1010/scripts/finalize.py --run-id run-20261028T1010
```

单个用例：

```powershell
python pilot/evidence/B0/run-20261028T1010/scripts/cross_path.py --code-root . --work $env:TEMP\b0-xp --out cross_path.json --log-dir logs
python pilot/evidence/B0/run-20261028T1010/scripts/cross_repo.py --code-root . --work $env:TEMP\b0-xr --out cross_repo.json --log-dir logs --checker pilot/evidence/B0/run-20261028T1010/scripts/check_receipt.py
```

## 5. NOT VERIFIED（本包不覆盖）

1. **`goal evidence` 全链路**：本构建没有签名者，`verify` 写入 `MANUAL_REVIEW_REQUIRED` 记录并退出 2；AC-1 的 `goal evidence exit 0` 需要 PM-03/人类用已签名 fixture 复测。跨路径部分（`verify_receipt` + `_verification_current`）已在本包覆盖。
2. **浅克隆（`--depth`）**：根提交会停在被截断的边界，跨路径身份可能不同；需 `git fetch --unshallow`。已写入 ADR 残余风险。
3. **真实远端**：测试使用合成的 remote URL（`github.com/pilot-org/...`），未执行网络 fetch；身份只依赖 URL 字符串与本地根提交。
4. **WSL / trusted 模式**：B0 不需要 `pilot/kit/b1/` 探针，本包未运行 trusted 执行或 WSL 探针。
5. **PM-03 独立复现（AC-10）**：不在本会话范围。
6. **跨机器可移植性**：A/B 在同一台机器、同一文件系统；跨 OS 的大小写/路径差异未测试（身份不读路径，但未运行）。

## 6. 范围

改动仅涉及 `project_memory/execution.py`、`tests/test_repo_identity.py`、`docs/decisions/ADR-0001-portable-repository-identity.md`、`pilot/rounds/B0/context-recovery-pm02.md` 与本证据目录。未修改 B1–B5 行为、任务卡、判据、探针、评测器或冻结候选。
