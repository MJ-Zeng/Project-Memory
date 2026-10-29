# B5B 隔离探针 fixture

`marker-command.py` 是 B5B 的标记命令：把字符串 `marker` 写入 `argv[1]` 指定的路径。它不依赖第三方库，宿主解释器和 WSL 沙箱解释器都能运行：

```bash
python fixtures/b5b/marker-command.py /tmp/b5b-marker
# marker-written: /tmp/b5b-marker
```

- 写入成功：stdout 输出 `marker-written: <path>`，退出 0。
- 写入失败：stderr 输出 `marker-write-failed: ...`，退出 1。
- 缺少参数：stderr 输出用法，退出 2。

## 宿主 marker 的含义

“宿主 marker”指用宿主路径（例如 Windows 临时目录下的文件）作为参数。默认拒绝的用例必须证明**宿主 marker 不出现**，即命令根本没有在宿主文件系统上执行；`--trusted` 用例还要证明沙箱内的 `/tmp` 可写、而 `/mnt` 下的宿主路径不可写。

## 已验证的用例（B5B 证据包）

| 用例 | 命令模式 | 期望 | 实测 |
|---|---|---|---|
| 默认拒绝 | 不传模式 flag | exit 3，无 marker、无收据/快照 | exit 3；`marker_present=false` |
| 双 flag 拒绝 | `--trusted --allow-local-untrusted` | exit 3，不执行 | exit 3；无副作用 |
| 显式 local | `--allow-local-untrusted` | exit 0；宿主 marker 出现；收据标明 `local_untrusted` | 与期望一致 |
| trusted（沙箱路径） | `--trusted`，写 `/tmp/...` | exit 0；沙箱内 `marker-written`；宿主 marker 不出现 | inner exit 0；`isolation.mode=wsl2-user-mount-pid-net-namespace` |
| trusted（宿主路径） | `--trusted`，写 `/mnt/c/...` | 宿主 marker 不出现；日志 `marker-write-failed` | inner exit 1；`/mnt` 在命名空间内不可达 |
| trusted 不可用 | `--trusted` + `PROJECT_MEMORY_DISABLE_WSL=1` | exit 3；`BLOCKED`；不回退 local | 与期望一致；`fallback_to_local=false` |

以上行为由 `evidence/B5B/run-20261029T015035Z/` 的 `commands.jsonl`、各场景 `*.json/*.exit` 和 `receipts/` 记录。

## 依赖

`--trusted` 用例依赖 WSL2（B5B 环境为 Ubuntu、WSL version 2）。没有可用的 WSL2 时，`--trusted` 直接失败并返回 `BLOCKED`，不会静默回退到本地执行。`--allow-local-untrusted` 不需要 WSL2。

精确命令、环境与收据字段以 `evidence/B5B/` 为准；本 README 只复述已验证行为。
