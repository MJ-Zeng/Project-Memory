# B0.1 整改证据包 — `run-20261028T1142`

- 任务：**B0.1**（B0 审查后整改，F-1 / F-2 / F-3 / AC-1(b) 复测）
- Issue：<https://github.com/MJ-Zeng/Project-Memory/issues/3>
- PR：<https://github.com/MJ-Zeng/Project-Memory/pull/5>
- 审查报告：`origin/review/b0-14cc8fc:pilot/review/B0/REVIEW.md`
- 已审候选（本轮基线）：`14cc8fcba367dc36db0706041a21f22e10e3264e`
- 原始 B0 基线：`73be8e3ac4efc04c1811c122eb665344fe8ce4c3`
- 代码提交（本包在其上生成）：`baeb2b9cafa4caa45e2faf679306c0bc59addfbb`
- 任务卡 SHA-256：`81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0`
- 角色：PM-02 Developer（`pm02@pilot.invalid`）

> 本包只记录“运行的命令、观察到的退出码与输出”，**不**声明 PASS / VERIFIED。结论由 PM-03 与人类判定。

## 1. 观察摘要

| 场景 | 观察 |
|---|---|
| F-2 跨路径（A 的绝对路径 mapping） | 整仓复制到 B 后 `verify` 通过仓库身份检查：`ok=true`、`MANUAL_REVIEW_REQUIRED`、`mapping_status=review_required`；不再报“不是当前仓库” |
| F-2 跨路径（身份 id / 规范化 remote） | 在 B 中用稳定身份声明同样通过 |
| F-2 跨仓库（不同根提交 + 不同 remote） | 拒绝，错误为“target_repository … 不是当前仓库” |
| F-2 同名目录（`elsewhere/path-a`，不同历史） | 拒绝；裸目录名 `path-a` 也被拒绝 |
| Legacy 1.0 收据 | 原路径 `valid=true`、`legacy_path_bound=true`、`portable=false`；复制到其他路径 `valid=false`，问题指向 legacy 路径绑定 |
| F-3 remote 归一化 | `ssh://git@github.com:22/...`、`git@github.com:...`、`https://github.com/...` 均为 `github.com/pilot-org/repo-a`；`:2222` 保持 `github.com:2222/pilot-org/repo-a` |
| AC-1(b) 签名记录 | 用临时测试密钥签一条 schema 1.1 记录：A、B 两处签名校验均通过，`payload_sha256` 相同（**签名层**，不是信任锚授权） |
| AC-1(b) 临时 anchor | `chmod 444` 后只读位生效（`writable_while_0444=false`），但 `authority.load_anchor` 仍拒绝：所有者是当前用户，不能作为独立信任根 |
| 回归 | `164 passed, 2 skipped`，退出码 0 |

## 2. 结论：AC-1(b) 仍为 NOT VERIFIED

AC-1(b) 要求 `goal evidence` 在路径 A 与 B 均 `exit 0`。该路径需要验证记录为 `VERIFIED`，而 `verify` 只有在记录被**受保护信任锚**签名后才会写 `VERIFIED`。本环境：

1. 当前 shell 未提权（`net session` 失败）；
2. 临时 anchor 由测试进程创建，`Get-Acl` 所有者是当前用户 `ZMJ`；
3. `authority.anchor_is_protected` 明确拒绝“所有者是当前用户”的 anchor（`remediation.json` → `AC1b_anchor_protection`）。

把 anchor 所有者改成其他主体需要管理员权限/SeRestorePrivilege，本轮不执行；也不使用生产私钥。因此 `goal evidence exit 0` **未运行**，记 `NOT VERIFIED`，等待人类提供的已签名 fixture 补测。签名本身的跨路径可验证性已作为独立观察记录。

## 3. 文件索引

| 文件 | 证明什么 | 不证明什么 |
|---|---|---|
| `remediation.json` | F-2 正/负例、legacy、F-3、签名层与 anchor 保护的逐项观察 | 不证明 `goal evidence` exit 0；不证明安全验收 |
| `commands.jsonl` | 证据运行期间的命令、退出码、日志路径与日志 SHA-256 | 不含探索性调试命令（见 §5） |
| `logs/` | 每条命令的完整 stdout/stderr | 日志内容不代表签名或授权 |
| `environment.txt` | 运行环境、任务卡哈希、代码提交 | 不含本轮证据提交自身 |
| `diffstat.txt` | 相对已审候选与原始 B0 基线的改动范围 | 打包时的快照 |
| `scripts/` | 可重跑的驱动器与记录器 | 脚本本身不是证据，输出才是 |
| `sha256sums.txt` | 本目录各文件的 SHA-256（不覆盖自身） | 不覆盖 `commands.jsonl` 之外的新增提交 |

## 4. 复现

```powershell
C:\SoftWare\Anconda\python.exe pilot/evidence/B0/run-20261028T1142/scripts/remediation_probe.py `
  --code-root . --work "$env:TEMP\b01-probe" --out pilot/evidence/B0/run-20261028T1142/remediation.json
C:\SoftWare\Anconda\python.exe -m pytest -q -p no:cacheprovider
```

单个场景的断言也在 `tests/test_repo_identity.py` 中（新增 8 项），可直接用 pytest 复跑。

## 5. 偏离与透明性

- `commands.jsonl` 只记录生成本包的 5 条命令；开发期间的探索性命令（包括一次在“同一副本上连续 verify 两次”导致的测试失败，已改为每个 mapping 用独立副本后重跑）没有归档。
- 未删除或跳过任何测试；`2 skipped` 是既有的 Windows 符号链接用例（`tests/test_security_rc3.py:291,304`），与基线一致。
- 临时测试密钥只存在于 `%TEMP%`，未写入仓库；未读取、未使用生产私钥或 `/etc/pm-rc3-review/key-a.pem`。

## 6. NOT VERIFIED（本包不覆盖）

1. **AC-1(b) `goal evidence` exit 0**：受保护 anchor 的所有权门槛无法在未提权环境满足，见 §2。
2. **浅克隆（`--depth`）**：根提交会被截断；需 `git fetch --unshallow`（ADR §5.5）。
3. **真实远端 fetch**：使用合成 remote URL，未执行网络 fetch。
4. **映射写绝对路径且对方检出已删除**：B 无法解析旧路径身份，会失败关闭（ADR §5.7）；需要长期可移植时写稳定身份或规范化 remote。
