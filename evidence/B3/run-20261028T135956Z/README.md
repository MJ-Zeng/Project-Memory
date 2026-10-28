# B3 evidence — run-20261028T135956Z

- 任务：B3（Issue #16）— 证据附件不得使已签名验证失效
- 基线：`832f2710bfde1cbc498ee6882a5e10b797db6a76`
- 代码提交：`19bba33`（`fix/b3-stable-criteria`）
- 证据提交：本目录所在提交（PR head；不含代码改动）
- 环境：见 `environment.txt`；测试 `pytest 9.1.1` / Windows Python 3.12.4；WSL Ubuntu 26.04 / Python 3.14.4
- 本包是开发侧证据，**不宣布 PASS / VERIFIED**；结论由 PM-03 与人类判定。

## 1. 结果摘要

| 项 | 结果 |
|---|---|
| 全量测试 | 213 passed / 2 skipped（基线 203/2；新增 10） |
| 新增 B3 测试 | 10 passed |
| 既有 B2 测试 | 13 passed |
| anchor-a legacy 正例 `genuine-trusted` | `goal evidence` exit 0；`goal evaluate` exit 0、`satisfied=true` |
| anchor-a 人类例外 `exception` | `goal evidence` exit 0；`goal evaluate` exit 0、`satisfied=true` |
| anchor-a 伪造 `forged-untrusted` | `goal evidence` exit 1（执行来源不可信 / 人类例外缺失） |
| anchor-a 伪造 `forged-claimed-trusted` | `goal evidence` exit 1（不信任布尔值） |
| anchor-a 追加第二证据 | evaluate exit 0、`satisfied=true`；记录字节不变 |
| anchor-a 改 criterion statement | evaluate exit 2、`satisfied=false`；reason 指明“判据定义已变化” |
| 验证记录字节 | 所有 case 在 `goal evidence` 前后 sha256 相同 |

复现命令见 `commands.jsonl`；原始输出在 `e2e/`；测试日志 `pytest.log`、`b3-pytest.log`、`b2-pytest.log`。

## 2. 新记录（稳定摘要）证据的边界

`new-stable-e2e.py` 用**临时测试锚**（`/tmp/b3-new-stable`，非 anchor-a）生成新格式记录，验证：

- 记录写 `goal_criteria_sha256` = 稳定定义摘要，`goal_criteria_legacy_sha256` = 旧全量摘要；
- `goal evidence` 前后记录字节相同。

但 CLI 在该测试锚下被 `anchor_is_protected` **正确拒绝**（`/tmp` 文件对当前进程可写），因此 `goal evidence` exit 1。这是 fail-closed 的预期行为，不是产品缺陷。

**缺少 `fixtures/b3/new-stable`（任务卡 §7 要求由 PM-01 用 anchor-a 签名）。** PM-02 不读 key-a、不自行签名，所以“新稳定摘要记录 + 真实 anchor-a + CLI evaluate satisfied”这一条 **NOT VERIFIED**；新记录逻辑路径由 `tests/test_security_b3.py`（测试期 RSA 密钥 + patch `load_anchor`）覆盖。请 PM-03/人类补 fixture 或接受该边界。

`new-stable-e2e.json` 保留失败输出，作为“测试锚不可写 → 拒绝”的证据。

## 3. 目录

```text
commands.jsonl             复现 + 测试 + E2E 命令与退出码
environment.txt            版本、基线、任务卡哈希、anchor-a 元数据
pytest.log                 全量 213 passed / 2 skipped
b3-pytest.log              新增 10 passed
b2-pytest.log              既有 B2 13 passed
b3-positive.json           新记录（测试锚）+ evidence-change（anchor-a）
b3-legacy.json             legacy 正例 + 例外（anchor-a）
b3-negative.json           改定义失效 + 两个伪造 case
b2-regression.json         B2 来源门禁 + 全量回归
e2e/                       每个 case 的 stdout/stderr 与记录哈希
repro.sh                   修复前复现脚本（在当前代码上会变为 satisfied）
e2e_anchor_a.sh            anchor-a 四 case 矩阵
e2e_b3_extra.sh            evidence-change / definition-change
new_stable_e2e.py          新记录 + 临时测试锚（明确标注非 anchor-a）
collect_evidence.py        汇总脚本
append_commands.py         commands.jsonl 汇总脚本
diffstat.txt               代码提交与工作树范围
sha256sums.txt             本包文件与 fixture 记录哈希
```

注意：`repro.sh` 是**修复前**的复现脚本；在 `19bba33` 上重跑会得到 `satisfied=true`。修复前的实际输出保存在本目录根部的 `repro-goal-*` 文件中。

## 4. 未做/环境限制

- 未读取 `/etc/pm-rc3-review/key-a.pem`；未生成任何 anchor-a 签名。
- 未修改任何 fixture；所有 E2E 都在 `/tmp` 副本上运行。
- 未运行真实 WSL `trusted_exec` 启动器（B2 残留范围，未改动）。
- 2 skipped 是既有 Windows 符号链接用例，未新增跳过。
- `skill/project-memory/references/data-contracts.md` 的 digest 语义未更新（不在任务卡允许路径）。
