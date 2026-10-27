# B1 验证工具包

## 内容

- `openssl_substitution.py`：RC3 独立复核使用的原始 B1 攻击探针。
- SHA-256：`827ad0c29d50cd15ce345485d24e5a75edf069522c89b048236c08ba9e617c73`
- 源：`reviews/independent-rc3-0d08a1a/probes/openssl_substitution.py`

**不要修改本探针。** PM-03 必须从基线工作树（`.pilot/base`）读取它，而不是候选树里的副本。

## 前置条件

- Windows + WSL（Ubuntu），探针以 root 启动。
- `/etc/pm-rc3-review/` 存在：
  - `anchor-a.json`、`pub-a.pem`（验证用）
  - `key-a.pem`、`key-b.pem`（仅人类/外部签名者）
- 探针内部以 uid 1000 执行 CLI；需要 WSL 中有可用的 `python3` 和 `git`。
- 被测代码路径（`CODE`）必须可由 uid 1000 读取。
- 工作目录（`WORK`）与输出（`OUT`）必须可写。

## 运行

在 **PM-03 的 Clone** 中，从基线工作树取探针：

```bash
wsl.exe -u root -e python3 \
  /mnt/c/<...>/pm-pilot-03/.pilot/base/pilot/kit/b1/openssl_substitution.py \
  /mnt/c/<...>/pm-pilot-03/.pilot/candidate \
  /mnt/c/<...>/pm-pilot-03/pilot/evidence/B1/review-<run>/work \
  /mnt/c/<...>/pm-pilot-03/pilot/evidence/B1/review-<run>/probe-after.json
```

第一个参数是**被测代码**，第二个是临时工作目录，第三个是输出 JSON。

## 基线（修复前，`0d08a1a`）

```text
control_real_openssl_exit = 1        control_rejected = true
path_substitution_exit   = 0        path_substitution_accepted = true
path_evaluate_exit       = 0
path_achieved_exit       = 0        path_goal_status = achieved
env_openssl_exit         = 0        env_openssl_accepted = true
env_true_exit            = 0        env_true_accepted = true
agent_owned_anchor_exit  = 1        agent_owned_anchor_rejected = true
```

## 修复后期望

```text
control_rejected = true
path_substitution_accepted = false
env_openssl_accepted = false
env_true_accepted = false
path_achieved_exit != 0
path_goal_status != achieved
agent_owned_anchor_rejected = true
```

任何一项不符：记 FAIL，保存 JSON 与日志。

## 安全边界

- 探针内部会调用默认 `test-run`（无 OS 隔离），执行的命令是探针内置的 `python3 tests/check.py`；**不要**把它改成任意命令。
- 不要用 `--trusted` 跑 B1：trusted 模式会遮蔽 `/mnt`，导致 Windows 路径不可见；trusted 模式留给 B5/沙箱专项。
- 不要读取 `key-a.pem`；探针不需要私钥。
- 输出中不要包含 token、私钥或其他项目数据。

## 证据

`probe-after.json` 保留完整 `results` 与 `steps`；另存 stderr/stdout 日志与 `sha256sums.txt`。
